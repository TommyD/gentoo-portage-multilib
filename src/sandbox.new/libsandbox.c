/*	
**	Path sandbox for the gentoo linux portage package system, initially
**	based on the ROCK Linux Wrapper for getting a list of created files
**
**  to integrate with bash, bash should have been built like this
**
**  ./configure --prefix=<prefix> --host=<host> --without-gnu-malloc
**
**  it's very important that the --enable-static-link option is NOT specified
**	
**	Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
**	Distributed under the terms of the GNU General Public License, v2 or later 
**	Author : Geert Bevin <gbevin@uwyn.com>
**
**  Post Bevin leaving Gentoo ranks:
**  --------------------------------
**    Ripped out all the wrappers, and implemented those of InstallWatch.
**    Losts of cleanups and bugfixes.  Implement a execve that forces $LIBSANDBOX
**    in $LD_PRELOAD.  Reformat the whole thing to look  somewhat like the reworked
**    sandbox.c from Brad House <brad@mainstreetsoftworks.com>.
**
**    Martin Schlemmer <azarah@gentoo.org> (18 Aug 2002)
**
**  Partly Copyright (C) 1998-9 Pancrazio `Ezio' de Mauro <p@demauro.net>,
**  as some of the InstallWatch code was used.
**
**
**  $Header$
*/

/* Uncomment below to enable wrapping of mknod().
 * This is broken currently. */
/* #define WRAP_MKNOD */

/* Uncomment below to enable the use of strtok_r().
 * This is broken currently. */
/* #define REENTRANT_STRTOK */


#define open   xxx_open
#define open64 xxx_open64

/* Wrapping mknod, do not have any effect, and
 * wrapping __xmknod causes calls to it to segfault
 */
#ifdef WRAP_MKNOD
# define __xmknod xxx___xmknod
#endif

#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/param.h>
#include <unistd.h>
#include <utime.h>

#ifdef WRAP_MKNOD
# undef __xmknod
#endif

#undef open
#undef open64

#include "localdecls.h"
#include "sandbox.h"

#define PIDS_FILE	"/tmp/sandboxpids.tmp"

#define FUNCTION_SANDBOX_SAFE(func, path) \
        ((0 == is_sandbox_on()) || (1 == before_syscall(func, path)))

#define FUNCTION_SANDBOX_SAFE_INT(func, path, flags) \
        ((0 == is_sandbox_on()) || (1 == before_syscall_open_int(func, path, flags)))

#define FUNCTION_SANDBOX_SAFE_CHAR(func, path, mode) \
        ((0 == is_sandbox_on()) || (1 == before_syscall_open_char(func, path, mode)))


/* Macro to check if a wrapper is defined, if not
 * then try to resolve it again. */
#define check_dlsym(name) \
{ \
  int old_errno=errno; \
  if (!true_ ## name) true_ ## name=get_dlsym(#name); \
  errno=old_errno; \
}

static char sandbox_lib[255];

typedef struct {
  int show_access_violation;
  char** deny_prefixes;
  int num_deny_prefixes;
  char** read_prefixes;
  int num_read_prefixes;
  char** write_prefixes;
  int num_write_prefixes;
  char** predict_prefixes;
  int num_predict_prefixes;
  char** write_denied_prefixes;
  int num_write_denied_prefixes;
} sbcontext_t;

/* glibc modified realpath() functions */
char *erealpath (const char *name, char *resolved);

static void *get_dlsym(const char *);
static void canonicalize(const char *, char *);
static int check_access(sbcontext_t *, const char *, const char *);
static int check_syscall(sbcontext_t *, const char *, const char *);
static int before_syscall(const char *, const char *);
static int before_syscall_open_int(const char *, const char *, int);
static int before_syscall_open_char(const char *, const char *, const char *);
static void clean_env_entries(char ***, int *);
static void init_context(sbcontext_t *);
static void init_env_entries(char ***, int *, char *, int);
static char* filter_path(const char*);
static int is_sandbox_on();
static int is_sandbox_pid();

/* Wrapped functions */

extern int chmod(const char *, mode_t);
static int(*true_chmod)(const char *, mode_t);
extern int chown(const char *, uid_t, gid_t);
static int(*true_chown)(const char *, uid_t, gid_t);
extern int creat(const char *, mode_t);
static int(*true_creat)(const char *, mode_t);
extern FILE *fopen(const char *,const char*);
static FILE *(*true_fopen)(const char *,const char*);
extern int lchown(const char *, uid_t, gid_t);
static int(*true_lchown)(const char *, uid_t, gid_t);
extern int link(const char *, const char *);
static int(*true_link)(const char *, const char *);
extern int mkdir(const char *, mode_t);
static int(*true_mkdir)(const char *, mode_t);
#ifdef WRAP_MKNOD
extern int __xmknod(const char *, mode_t, dev_t);
static int(*true___xmknod)(const char *, mode_t, dev_t);
#endif
extern int open(const char *, int, ...);
static int(*true_open)(const char *, int, ...);
extern int rename(const char *, const char *);
static int(*true_rename)(const char *, const char *);
extern int rmdir(const char *);
static int(*true_rmdir)(const char *);
extern int symlink(const char *, const char *);
static int(*true_symlink)(const char *, const char *);
extern int truncate(const char *, TRUNCATE_T);
static int(*true_truncate)(const char *, TRUNCATE_T);
extern int unlink(const char *);
static int(*true_unlink)(const char *);

#if (GLIBC_MINOR >= 1)

extern int creat64(const char *, __mode_t);
static int(*true_creat64)(const char *, __mode_t);
extern FILE *fopen64(const char *,const char *);
static FILE *(*true_fopen64)(const char *,const char *);
extern int open64(const char *, int, ...);
static int(*true_open64)(const char *, int, ...);
extern int truncate64(const char *, __off64_t);
static int(*true_truncate64)(const char *, __off64_t);

#endif

extern int execve(const char *filename, char *const argv [], char *const envp[]);
static int (*true_execve)(const char *, char *const [], char *const []);

/*
 * Initialize the shabang
 */

void _init(void)
{
  void *libc_handle;
  char *tmp_string = NULL;

#ifdef BROKEN_RTLD_NEXT
//  printf ("RTLD_LAZY");
  libc_handle = dlopen(LIBC_VERSION, RTLD_LAZY);
#else
//  printf ("RTLD_NEXT");
  libc_handle = RTLD_NEXT;
#endif

  true_chmod = dlsym(libc_handle, "chmod");
  true_chown = dlsym(libc_handle, "chown");
  true_creat = dlsym(libc_handle, "creat");
  true_fopen = dlsym(libc_handle, "fopen");
  true_lchown = dlsym(libc_handle, "lchown");
  true_link = dlsym(libc_handle, "link");
  true_mkdir = dlsym(libc_handle, "mkdir");
#ifdef WRAP_MKNOD
  true___xmknod = dlsym(libc_handle, "__xmknod");
#endif
  true_open = dlsym(libc_handle, "open");
  true_rename = dlsym(libc_handle, "rename");
  true_rmdir = dlsym(libc_handle, "rmdir");
  true_symlink = dlsym(libc_handle, "symlink");
  true_truncate = dlsym(libc_handle, "truncate");
  true_unlink = dlsym(libc_handle, "unlink");

#if (GLIBC_MINOR >= 1)
  true_creat64 = dlsym(libc_handle, "creat64");
  true_fopen64 = dlsym(libc_handle, "fopen64");
  true_open64 = dlsym(libc_handle, "open64");
  true_truncate64 = dlsym(libc_handle, "truncate64");
#endif

  true_execve = dlsym(libc_handle, "execve");

  /* Get the path and name to this library */
  tmp_string = get_sandbox_lib("/");
  strncpy(sandbox_lib, tmp_string, 254);
  
  if (tmp_string) free(tmp_string);
  tmp_string = NULL;
}

static void canonicalize(const char *path, char *resolved_path)
{
  if(!erealpath(path, resolved_path) && (path[0] != '/')) {
    /* The path could not be canonicalized, append it
     * to the current working directory if it was not
     * an absolute path
     */
    getcwd(resolved_path, MAXPATHLEN - 2);
    strcat(resolved_path, "/");
    strncat(resolved_path, path, MAXPATHLEN - 1);
	erealpath(resolved_path, resolved_path);
  }
}

static void *get_dlsym(const char *symname)
{
  void *libc_handle = NULL;
  void *symaddr = NULL;

#ifdef BROKEN_RTLD_NEXT
  libc_handle = dlopen(LIBC_VERSION, RTLD_LAZY);
  if (!libc_handle) {
    printf("libsandbox.so: Can't dlopen libc: %s\n", dlerror());
    abort();
  }
#else
  libc_handle = RTLD_NEXT;
#endif

  symaddr = dlsym(libc_handle, symname);
  if (!symaddr) {
    printf("libsandbox.so: Can't resolve %s: %s\n", symname, dlerror());
    abort();
  }

  return symaddr;
}

/*
 * Wrapper Functions
 */

int chmod(const char *path, mode_t mode)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(path, canonic);

  if FUNCTION_SANDBOX_SAFE("chmod", canonic) {
    check_dlsym(chmod);
    result = true_chmod(path, mode);
  }
	
  return result;
}

int chown(const char *path, uid_t owner, gid_t group)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(path, canonic);

  if FUNCTION_SANDBOX_SAFE("chown", canonic) {
    check_dlsym(chown);
    result = true_chown(path, owner, group);
  }
	
  return result;
}

int creat(const char *pathname, mode_t mode)
{
/* Is it a system call? */
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("creat", canonic) {
    check_dlsym(open);
    result = true_open(pathname, O_CREAT | O_WRONLY | O_TRUNC, mode);
  }

  return result;
}

FILE *fopen(const char *pathname, const char *mode)
{
  FILE *result = NULL;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE_CHAR("fopen", canonic, mode) {
    check_dlsym(fopen);
    result = true_fopen(pathname,mode);
  }
	
  return result;
}

int lchown(const char *path, uid_t owner, gid_t group)
{
/* Linux specific? */
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(path, canonic);

  if FUNCTION_SANDBOX_SAFE("lchown", canonic) {
    check_dlsym(chown);
    result = true_chown(path, owner, group);
  }
	
  return result;
}

int link(const char *oldpath, const char *newpath)
{
  int result = -1;
  char old_canonic[MAXPATHLEN], new_canonic[MAXPATHLEN];

  canonicalize(oldpath, old_canonic);
  canonicalize(newpath, new_canonic);

  if FUNCTION_SANDBOX_SAFE("link", new_canonic) {
    check_dlsym(link);
    result = true_link(oldpath, newpath);
  }
	
  return result;
}

int mkdir(const char *pathname, mode_t mode)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("mkdir", canonic) {
    check_dlsym(mkdir);
    result = true_mkdir(pathname, mode);
  }
	
  return result;
}

#ifdef WRAP_MKNOD

int __xmknod(const char *pathname, mode_t mode, dev_t dev)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("__xmknod", canonic) {
    check_dlsym(__xmknod);
    result = true___xmknod(pathname, mode, dev);
  }

  return result;
}

#endif

int open(const char *pathname, int flags, ...)
{
/* Eventually, there is a third parameter: it's mode_t mode */
  va_list ap;
  mode_t mode = 0;
  int result = -1;
  char canonic[MAXPATHLEN];

  if (flags & O_CREAT) {
    va_start(ap, flags);
    mode = va_arg(ap, mode_t);
    va_end(ap);
  }

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE_INT("open", canonic, flags) {
    /* We need to resolve open() realtime in some cases,
	 * else we get a segfault when running /bin/ps, etc
	 * in a sandbox */
    check_dlsym(open);
    result=true_open(pathname, flags, mode);
  }

  return result;
}

int rename(const char *oldpath, const char *newpath)
{
  int result = -1;
  char old_canonic[MAXPATHLEN], new_canonic[MAXPATHLEN];

  canonicalize(oldpath, old_canonic);
  canonicalize(newpath, new_canonic);

  if FUNCTION_SANDBOX_SAFE("rename", new_canonic) {
    check_dlsym(rename);
    result = true_rename(oldpath, newpath);
  }
	
  return result;
}

int rmdir(const char *pathname)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("rmdir", canonic) {
    check_dlsym(rmdir);
    result = true_rmdir(pathname);
  }
	
  return result;
}

int symlink(const char *oldpath, const char *newpath)
{
  int result = -1;
  char old_canonic[MAXPATHLEN], new_canonic[MAXPATHLEN];

  canonicalize(oldpath, old_canonic);
  canonicalize(newpath, new_canonic);

  if FUNCTION_SANDBOX_SAFE("symlink", new_canonic) {
    check_dlsym(symlink);
    result = true_symlink(oldpath, newpath);
  }
	
  return result;
}

int truncate(const char *path, TRUNCATE_T length)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(path, canonic);

  if FUNCTION_SANDBOX_SAFE("truncate", canonic) {
    check_dlsym(truncate);
    result = true_truncate(path, length);
  }
	
  return result;
}

int unlink(const char *pathname)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("unlink", canonic) {
    check_dlsym(unlink);
    result = true_unlink(pathname);
  }
	
  return result;
}

#if (GLIBC_MINOR >= 1)

int creat64(const char *pathname, __mode_t mode)
{
/* Is it a system call? */
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE("creat64", canonic) {
    check_dlsym(open64);
    result = true_open64(pathname, O_CREAT | O_WRONLY | O_TRUNC, mode);
  }
	
  return result;
}

FILE *fopen64(const char *pathname, const char *mode)
{
  FILE *result = NULL;
  char canonic[MAXPATHLEN];

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE_CHAR("fopen64", canonic, mode) {
    check_dlsym(fopen64);
    result = true_fopen(pathname,mode);
  }
	
  return result;
}

int open64(const char *pathname, int flags, ...)
{
/* Eventually, there is a third parameter: it's mode_t mode */
  va_list ap;
  mode_t mode = 0;
  int result = -1;
  char canonic[MAXPATHLEN];

  if (flags & O_CREAT) {
    va_start(ap, flags);
    mode = va_arg(ap, mode_t);
    va_end(ap);
  }

  canonicalize(pathname, canonic);

  if FUNCTION_SANDBOX_SAFE_INT("open64", canonic, flags) {
    check_dlsym(open64);
    result=true_open64(pathname, flags, mode);
  }

  return result;
}

int truncate64(const char *path, __off64_t length)
{
  int result = -1;
  char canonic[MAXPATHLEN];

  canonicalize(path, canonic);

  if FUNCTION_SANDBOX_SAFE("truncate64", canonic) {
    check_dlsym(truncate64);
    result = true_truncate64(path, length);
  }
	
  return result;
}

#endif /* GLIBC_MINOR >= 1 */

/*
 * Exec Wrappers
 */

int execve(const char *filename, char *const argv [], char *const envp[])
{
  int result = -1;
  int count = 0, old_errno = 0;
  char canonic[MAXPATHLEN];
  char *old_envp = NULL;
  char *new_envp = NULL;

  canonicalize(filename, canonic);

  if FUNCTION_SANDBOX_SAFE("execve", canonic) {
    old_errno = errno;

    while (envp[count] != NULL) {
      if (strstr(envp[count], "LD_PRELOAD=") == envp[count]) {
        if (NULL != strstr(envp[count], sandbox_lib)) {
          break;
        } else {
          const int max_envp_len=strlen(envp[count]) + strlen(sandbox_lib) + 1;
          
          /* Backup envp[count], and set it to our own one which
           * contains sandbox_lib */
          old_envp = envp[count];
          new_envp = (char *)malloc((max_envp_len + 1) * sizeof(char));
          strncpy(new_envp, old_envp, max_envp_len);

          /* LD_PRELOAD already have variables other than sandbox_lib,
           * thus we have to add sandbox_lib via a white space. */
          if (0 != strcmp(envp[count], "LD_PRELOAD=")) {
            strncpy(new_envp + strlen(old_envp), ":",
                    max_envp_len - strlen(new_envp));
            strncpy(new_envp + strlen(old_envp) + 1, sandbox_lib,
                    max_envp_len - strlen(new_envp));
          } else {
            strncpy(new_envp + strlen(old_envp), sandbox_lib,
                    max_envp_len - strlen(new_envp));
          }

          /* Valid string? */
          new_envp[max_envp_len] = '\0';

          /* envp[count] = new_envp;
           *
           * Get rid of the "read-only" warnings */
          memcpy((void *)&envp[count], &new_envp, sizeof(new_envp));

          break;
        }
      }
      count++;
    }

    errno = old_errno;
    check_dlsym(execve);
    result = true_execve(filename, argv, envp);
    old_errno = errno;

    if (old_envp) {
      /* Restore envp[count] again.
       * 
       * envp[count] = old_envp; */
      memcpy((void *)&envp[count], &old_envp, sizeof(old_envp));
      old_envp = NULL;
    }
    if (new_envp) {
      free(new_envp);
      new_envp = NULL;
    }
    errno = old_errno;
  }

  return result;
}

/*
 * Internal Functions
 */

#if (GLIBC_MINOR == 1)

/* This hack is needed for glibc 2.1.1 (and others?)
 * (not really needed, but good example) */
extern int fclose(FILE *);
static int (*true_fclose)(FILE *) = NULL;
int fclose(FILE *file)
{
  int result = - 1;

  check_dlsym(fclose);
  result = true_fclose(file);

  return result;
}

#endif /* GLIBC_MINOR == 1 */

static void init_context(sbcontext_t* context)
{
  context->show_access_violation = 1;
  context->deny_prefixes = NULL;
  context->num_deny_prefixes = 0;
  context->read_prefixes = NULL;
  context->num_read_prefixes = 0;
  context->write_prefixes = NULL;
  context->num_write_prefixes = 0;
  context->predict_prefixes = NULL;
  context->num_predict_prefixes = 0;
  context->write_denied_prefixes = NULL;
  context->num_write_denied_prefixes = 0;
}

static int is_sandbox_pid()
{
  int result = 0;
  FILE* pids_stream = NULL;
  int pids_file = -1;
  int current_pid = 0;
  int tmp_pid = 0;

  check_dlsym(fopen);
  pids_stream = true_fopen(PIDS_FILE, "r");

  if (NULL == pids_stream) {
    perror(">>> pids file fopen");
  }
  else
  {
    pids_file = fileno(pids_stream);

    if (pids_file < 0) {
      perror(">>> pids file fileno");
    } else {
      current_pid = getpid();

      while (EOF != fscanf(pids_stream, "%d\n", &tmp_pid)) {
        if (tmp_pid == current_pid) {
          result = 1;
          break;
        }
      }
    }
    if (EOF == fclose(pids_stream)) {
      perror(">>> pids file fclose");
    }
    pids_stream = NULL;
    pids_file = -1;
  }

  return result;
}

static void clean_env_entries(char*** prefixes_array, int* prefixes_num)
{
  int i = 0;
  
  if (NULL != *prefixes_array) {
    for (i = 0; i < *prefixes_num; i++) {
      if (NULL != (*prefixes_array)[i]) {
        free((*prefixes_array)[i]);
        (*prefixes_array)[i] = NULL;
      }
    }
    if (*prefixes_array) free(*prefixes_array);
    *prefixes_array = NULL;
    *prefixes_num = 0;
  }
}

static void init_env_entries(char*** prefixes_array, int* prefixes_num, char* env, int warn)
{
  char* prefixes_env = getenv(env);

  if (NULL == prefixes_env) {
    fprintf(stderr,
            "Sandbox error : the %s environmental variable should be defined.\n",
            env);
  } else {
    char* buffer = NULL;
#ifdef REENTRANT_STRTOK
    char** strtok_buf = NULL;
#endif
    int prefixes_env_length = strlen(prefixes_env);
    int i = 0;
    int num_delimiters = 0;
    char* token = NULL;
    char* prefix = NULL;

    for (i = 0; i < prefixes_env_length; i++) {
      if (':' == prefixes_env[i]) {
        num_delimiters++;
      }
    }

    if (num_delimiters > 0) {
      buffer = (char *)malloc((prefixes_env_length + 1) * sizeof(char));
#ifdef REENTRANT_STRTOK
      *strtok_buf = (char *)malloc((prefixes_env_length + 1) * sizeof(char));
#endif
      *prefixes_array = (char **)malloc((num_delimiters + 1) * sizeof(char *));

      strncpy(buffer, prefixes_env, prefixes_env_length + 1);
#ifdef REENTRANT_STRTOK
      token = strtok_r(buffer, ":", strtok_buf);
#else
      token = strtok(buffer, ":");
#endif

      while ((NULL != token) && (strlen(token) > 0)) {
        prefix = (char *)malloc((strlen(token) + 1) * sizeof(char));
        strncpy(prefix, token, strlen(token) + 1);
        (*prefixes_array)[(*prefixes_num)++] = filter_path(prefix);
        
        if (prefix) free(prefix);
        prefix = NULL;
#ifdef REENTRANT_STRTOK
        token = strtok_r(NULL, ":", strtok_buf);
#else
        token = strtok(NULL, ":");
#endif
      }
      
      if (buffer) free(buffer);
      buffer = NULL;
#ifdef REENTRANT_STRTOK
      if (strtok_buf) free(strtok_buf);
      strtok_buf = NULL;
#endif
    }
    else if (prefixes_env_length > 0) {
      (*prefixes_array) = (char **)malloc(sizeof(char *));
			
      prefix = (char *)malloc((prefixes_env_length + 1) * sizeof(char));
      strncpy(prefix, prefixes_env, prefixes_env_length + 1);
      (*prefixes_array)[(*prefixes_num)++] = filter_path(prefix);
      
      if (prefix) free(prefix);
      prefix = NULL;
    }
  }
}

static char* filter_path(const char* path)
{
  char* filtered_path = (char *)malloc(MAXPATHLEN * sizeof(char));

  canonicalize(path, filtered_path);

  return filtered_path;
}

static int check_access(sbcontext_t* sbcontext, const char* func, const char* path)
{
  int result = -1;
  int i = 0;
  char* filtered_path = filter_path(path);

  if ('/' != filtered_path[0]) {
    return 0;
  }

  if ((0 == strcmp(filtered_path, "/etc/ld.so.preload")) && (is_sandbox_pid())) {
    result = 1;
  }
	
  if (-1 == result) {
    if (NULL != sbcontext->deny_prefixes) {
      for (i = 0; i < sbcontext->num_deny_prefixes; i++) {
        if (0 == strncmp(filtered_path,
                         sbcontext->deny_prefixes[i],
                         strlen(sbcontext->deny_prefixes[i]))) {
          result = 0;
          break;
        }
      }
    }

    if (-1 == result) {
      if ((NULL != sbcontext->read_prefixes) &&
          ((0 == strcmp(func, "open_rd")) ||
           (0 == strcmp(func, "popen")) ||
           (0 == strcmp(func, "opendir")) ||
           (0 == strcmp(func, "system")) ||
           (0 == strcmp(func, "execl")) ||
           (0 == strcmp(func, "execlp")) ||
           (0 == strcmp(func, "execle")) ||
           (0 == strcmp(func, "execv")) ||
           (0 == strcmp(func, "execvp")) ||
           (0 == strcmp(func, "execve"))
          )
         ) {
        for (i = 0; i < sbcontext->num_read_prefixes; i++) {
          if (0 == strncmp(filtered_path,
                           sbcontext->read_prefixes[i],
                           strlen(sbcontext->read_prefixes[i]))) {
            result = 1;
            break;
          }
        }
      }
      else if ((NULL != sbcontext->write_prefixes) &&
               ((0 == strcmp(func, "open_wr")) ||
                (0 == strcmp(func, "creat")) ||
                (0 == strcmp(func, "creat64")) ||
                (0 == strcmp(func, "mkdir")) ||
                (0 == strcmp(func, "mknod")) ||
                (0 == strcmp(func, "mkfifo")) ||
                (0 == strcmp(func, "link")) ||
                (0 == strcmp(func, "symlink")) ||
                (0 == strcmp(func, "rename")) ||
                (0 == strcmp(func, "utime")) ||
                (0 == strcmp(func, "utimes")) ||
                (0 == strcmp(func, "unlink")) ||
                (0 == strcmp(func, "rmdir")) ||
                (0 == strcmp(func, "chown")) ||
                (0 == strcmp(func, "lchown")) ||
                (0 == strcmp(func, "chmod")) ||
                (0 == strcmp(func, "truncate")) ||
                (0 == strcmp(func, "ftruncate")) ||
                (0 == strcmp(func, "truncate64")) ||
                (0 == strcmp(func, "ftruncate64"))
               )
              ) {
        struct stat tmp_stat;

        for (i = 0; i < sbcontext->num_write_denied_prefixes; i++) {
          if (0 == strncmp(filtered_path,
                           sbcontext->write_denied_prefixes[i],
                           strlen(sbcontext->write_denied_prefixes[i]))) {
            result = 0;
            break;
          }
        }

        if (-1 == result) {
          for (i = 0; i < sbcontext->num_write_prefixes; i++) {
            if (0 == strncmp(filtered_path,
                             sbcontext->write_prefixes[i],
                             strlen(sbcontext->write_prefixes[i]))) {
              result = 1;
              break;
            }
          }

          if (-1 == result) {
            /* hack to prevent mkdir of existing dirs to show errors */
            if (strcmp(func, "mkdir") == 0) {
              if (0 == stat(filtered_path, &tmp_stat)) {
                sbcontext->show_access_violation = 0;
                result = 0;
              }
            }

            if (-1 == result) {
              for (i = 0; i < sbcontext->num_predict_prefixes; i++) {
                if (0 == strncmp(filtered_path,
                                 sbcontext->predict_prefixes[i],
                                 strlen(sbcontext->predict_prefixes[i]))) {
                  sbcontext->show_access_violation = 0;
                  result = 0;
                  break;
                }
              }
            }
          }
        }
      }
    }
  }
	
  if (-1 == result) {
    result = 0;
  }

  if (filtered_path) free(filtered_path);
  filtered_path = NULL;

  return result;
}

static int check_syscall(sbcontext_t* sbcontext, const char* func, const char* file)
{
  int result = 1;
  struct stat log_stat;
  char* log_path = NULL;
  char* absolute_path = NULL;
  char* tmp_buffer = NULL;
  int log_file = 0;
  struct stat debug_log_stat;
  char* debug_log_env = NULL;
  char* debug_log_path = NULL;
  int debug_log_file = 0;
  char buffer[512];

  if ('/' == file[0]) {
    absolute_path = (char *)malloc((strlen(file) + 1) * sizeof(char));
    sprintf(absolute_path, "%s", file);
  } else {
    tmp_buffer = get_current_dir_name();
    absolute_path = (char *)malloc((strlen(tmp_buffer) + 1 + strlen(file) + 1) * sizeof(char));
    sprintf(absolute_path,"%s/%s", tmp_buffer, file);
    
    if (tmp_buffer) free(tmp_buffer);
    tmp_buffer = NULL;
  }
  
  log_path = getenv("SANDBOX_LOG");
  debug_log_env = getenv("SANDBOX_DEBUG");
  debug_log_path = getenv("SANDBOX_DEBUG_LOG");
	
  if (((NULL == log_path) ||
       (0 != strcmp(absolute_path, log_path))) &&
      ((NULL == debug_log_env) ||
       (NULL == debug_log_path) ||
       (0 != strcmp(absolute_path, debug_log_path))) &&
      (0 == check_access(sbcontext, func, absolute_path))
     ) {
    if (1 == sbcontext->show_access_violation) {
      fprintf(stderr, "\e[31;01mACCESS DENIED\033[0m  %s:%*s%s\n",
              func, (int)(10 - strlen(func)), "", absolute_path);
			
      if (NULL != log_path) {
        sprintf(buffer, "%s:%*s%s\n", func, (int)(10 - strlen(func)), "", absolute_path);
		
        if ((0 == lstat(log_path, &log_stat)) &&
            (0 == S_ISREG(log_stat.st_mode))
           ) {
          fprintf(stderr,
                  "\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n",
                  log_path);
        } else {
          log_file = true_open(log_path,
                               O_APPEND | O_WRONLY | O_CREAT,
                               S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
          if(log_file >= 0) {
            write(log_file, buffer, strlen(buffer));
            close(log_file);
          }
        }
      }
    }

    result = 0;
  }
  else if (NULL != debug_log_env) {
    if (NULL != debug_log_path) {
      if (0 != strcmp(absolute_path, debug_log_path)) {
        sprintf(buffer, "%s:%*s%s\n", func, (int)(10 - strlen(func)), "", absolute_path);
        
        if ((0 == lstat(debug_log_path, &debug_log_stat)) &&
            (0 == S_ISREG(debug_log_stat.st_mode))
           ) {
          fprintf(stderr,
                  "\e[31;01mSECURITY BREACH\033[0m  %s already exists and is not a regular file.\n",
                  log_path);
        } else {
          debug_log_file = true_open(debug_log_path,
                                     O_APPEND | O_WRONLY | O_CREAT,
                                     S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
          if(debug_log_file >= 0) {
            write(debug_log_file, buffer, strlen(buffer));
            close(debug_log_file);
          }
        }
      }
    } else {
      fprintf(stderr, "\e[32;01mACCESS ALLOWED\033[0m %s:%*s%s\n",
              func, (int)(10 - strlen(func)), "", absolute_path);
    }
  }

  if (absolute_path) free(absolute_path);
  absolute_path = NULL;

  return result;
}

static int is_sandbox_on()
{
  /* $SANDBOX_ACTIVE is an env variable that should ONLY
   * be used internal by sandbox.c and libsanbox.c.  External
   * sources should NEVER set it, else the sandbox is enabled
   * in some cases when run in parallel with another sandbox,
   * but not even in the sandbox shell.
   *
   * Azarah (3 Aug 2002)
   */
  if ((NULL != getenv("SANDBOX_ON")) &&
      (0 == strcmp(getenv("SANDBOX_ON"), "1")) &&
      (NULL != getenv("SANDBOX_ACTIVE")) &&
      (0 == strcmp(getenv("SANDBOX_ACTIVE"), "armedandready"))
     ) {
    return 1;
  } else {
    return 0;
  }
}

static int before_syscall(const char* func, const char* file)
{
  int result = 1;
  sbcontext_t sbcontext;

  init_context(&sbcontext);

  init_env_entries(&(sbcontext.deny_prefixes),
                   &(sbcontext.num_deny_prefixes),
                   "SANDBOX_DENY", 1);
  init_env_entries(&(sbcontext.read_prefixes),
                   &(sbcontext.num_read_prefixes),
                   "SANDBOX_READ", 1);
  init_env_entries(&(sbcontext.write_prefixes),
                   &(sbcontext.num_write_prefixes),
                   "SANDBOX_WRITE", 1);
  init_env_entries(&(sbcontext.predict_prefixes),
                   &(sbcontext.num_predict_prefixes),
                   "SANDBOX_PREDICT", 1);

  result = check_syscall(&sbcontext, func, file);

  clean_env_entries(&(sbcontext.deny_prefixes),
                    &(sbcontext.num_deny_prefixes));
  clean_env_entries(&(sbcontext.read_prefixes),
                    &(sbcontext.num_read_prefixes));
  clean_env_entries(&(sbcontext.write_prefixes),
                    &(sbcontext.num_write_prefixes));
  clean_env_entries(&(sbcontext.predict_prefixes),
                    &(sbcontext.num_predict_prefixes));
	
  if (0 == result) {
    errno = EACCES;
  }

  return result;
}

static int before_syscall_open_int(const char* func, const char* file, int flags)
{
  if ((flags & O_WRONLY) || (flags & O_RDWR)) {
    return before_syscall("open_wr", file);
  } else {
    return before_syscall("open_rd", file);
  }
}

static int before_syscall_open_char(const char* func, const char* file, const char* mode)
{
  if ((strcmp(mode, "r") == 0) || (strcmp(mode, "rb") == 0)) {
    return before_syscall("open_rd", file);
  } else {
    return before_syscall("open_wr", file);
  }
}


// vim:expandtab noai:cindent ai
