/* $Header$ */

#define _GNU_SOURCE
#define _REENTRANT

#define open xxx_open
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#undef open

extern FILE* fopen(const char*, const char*);
FILE* (*orig_fopen)(const char*, const char*) = 0;
FILE* fopen(const char* a1, const char* a2)
{
	int old_errno = errno;
	if (!orig_fopen)
	{
		orig_fopen = dlsym(RTLD_NEXT, "fopen");
	}
	errno = old_errno;
	return orig_fopen(a1, a2);
}

