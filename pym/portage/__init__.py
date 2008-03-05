# portage.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


VERSION="$Rev$"[6:-2] + "-svn"

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

try:
	import sys
	import copy
	import errno
	import os
	import re
	import shutil
	import time
	try:
		import cPickle
	except ImportError:
		import pickle as cPickle

	import stat
	import commands
	from time import sleep
	from random import shuffle
	import UserDict
	from itertools import chain, izip
except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. These are internal modules for\n")
	sys.stderr.write("!!! python and failure here indicates that you have a problem with python\n")
	sys.stderr.write("!!! itself and thus portage is not able to continue processing.\n\n")

	sys.stderr.write("!!! You might consider starting python with verbose flags to see what has\n")
	sys.stderr.write("!!! gone wrong. Here is the information we got for this exception:\n")
	sys.stderr.write("    "+str(e)+"\n\n");
	raise

bsd_chflags = None
if os.uname()[0] in ["FreeBSD"]:
	def bsd_chflags():
		pass
	def _chflags(path, flags, opts=""):
		cmd = "chflags %s %o '%s'" % (opts, flags, path)
		status, output = commands.getstatusoutput(cmd)
		if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
			return
		# Try to generate an ENOENT error if appropriate.
		if "h" in opts:
			os.lstat(path)
		else:
			os.stat(path)
		# Make sure the binary exists.
		if not portage.process.find_binary("chflags"):
			raise portage.exception.CommandNotFound("chflags")
		# Now we're not sure exactly why it failed or what
		# the real errno was, so just report EPERM.
		e = OSError(errno.EPERM, output)
		e.errno = errno.EPERM
		e.filename = path
		e.message = output
		raise e
	def _lchflags(path, flags):
		return _chflags(path, flags, opts="-h")
	bsd_chflags.chflags = _chflags
	bsd_chflags.lchflags = _lchflags

try:
	from portage.cache.cache_errors import CacheError
	import portage.cvstree
	import portage.xpak
	import portage.getbinpkg
	import portage.dep
	from portage.dep import dep_getcpv, dep_getkey, get_operator, \
		isjustname, isspecific, isvalidatom, \
		match_from_list, match_to_list, best_match_to_list

	# XXX: This needs to get cleaned up.
	import portage.output
	from portage.output import bold, colorize, green, red, yellow

	import portage.const
	from portage.const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
		USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
		PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
		EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
		MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
		DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
		INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
		INCREMENTALS, EAPI, MISC_SH_BINARY, REPO_NAME_LOC, REPO_NAME_FILE

	from portage.data import ostype, lchown, userland, secpass, uid, wheelgid, \
	                         portage_uid, portage_gid, userpriv_groups
	from portage.manifest import Manifest

	import portage.util
	from portage.util import atomic_ofstream, apply_secpass_permissions, apply_recursive_permissions, \
		dump_traceback, getconfig, grabdict, grabdict_package, grabfile, grabfile_package, \
		map_dictlist_vals, new_protect_filename, normalize_path, \
		pickle_read, pickle_write, stack_dictlist, stack_dicts, stack_lists, \
		unique_array, varexpand, writedict, writemsg, writemsg_stdout, write_atomic
	import portage.exception
	import portage.gpg
	import portage.locks
	import portage.process
	from portage.process import atexit_register, run_exitfuncs
	from portage.locks import unlockfile,unlockdir,lockfile,lockdir
	import portage.checksum
	from portage.checksum import perform_md5,perform_checksum,prelink_capable
	import portage.eclass_cache
	from portage.localization import _
	from portage.update import dep_transform, fixdbentries, grab_updates, \
		parse_updates, update_config_files, update_dbentries

	# Need these functions directly in portage namespace to not break every external tool in existence
	from portage.versions import best, catpkgsplit, catsplit, pkgcmp, \
		pkgsplit, vercmp, ververify

	# endversion and endversion_keys are for backward compatibility only.
	from portage.versions import endversion_keys
	from portage.versions import suffix_value as endversion

except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the\n")
	sys.stderr.write("!!! portage tree under '/usr/portage/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise


try:
	import portage.selinux as selinux
except OSError, e:
	writemsg("!!! SELinux not loaded: %s\n" % str(e), noiselevel=-1)
	del e
except ImportError:
	pass

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================


def load_mod(name):
	modname = ".".join(name.split(".")[:-1])
	mod = __import__(modname)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def best_from_dict(key, top_dict, key_order, EmptyOnError=1, FullCopy=1, AllowEmpty=1):
	for x in key_order:
		if top_dict.has_key(x) and top_dict[x].has_key(key):
			if FullCopy:
				return copy.deepcopy(top_dict[x][key])
			else:
				return top_dict[x][key]
	if EmptyOnError:
		return ""
	else:
		raise KeyError, "Key not found in list; '%s'" % key

def getcwd():
	"this fixes situations where the current directory doesn't exist"
	try:
		return os.getcwd()
	except OSError: #dir doesn't exist
		os.chdir("/")
		return "/"
getcwd()

def abssymlink(symlink):
	"This reads symlinks, resolving the relative symlinks, and returning the absolute."
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)

dircache = {}
cacheHit=0
cacheMiss=0
cacheStale=0
def cacheddir(my_original_path, ignorecvs, ignorelist, EmptyOnError, followSymlinks=True):
	global cacheHit,cacheMiss,cacheStale
	mypath = normalize_path(my_original_path)
	if dircache.has_key(mypath):
		cacheHit += 1
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cacheMiss += 1
		cached_mtime, list, ftype = -1, [], []
	try:
		pathstat = os.stat(mypath)
		if stat.S_ISDIR(pathstat[stat.ST_MODE]):
			mtime = pathstat[stat.ST_MTIME]
		else:
			raise portage.exception.DirectoryNotFound(mypath)
	except EnvironmentError, e:
		if e.errno == portage.exception.PermissionDenied.errno:
			raise portage.exception.PermissionDenied(mypath)
		del e
		if EmptyOnError:
			return [], []
		return None, None
	except portage.exception.PortageException:
		if EmptyOnError:
			return [], []
		return None, None
	# Python retuns mtime in seconds, so if it was changed in the last few seconds, it could be invalid
	if mtime != cached_mtime or time.time() - mtime < 4:
		if dircache.has_key(mypath):
			cacheStale += 1
		try:
			list = os.listdir(mypath)
		except EnvironmentError, e:
			if e.errno != errno.EACCES:
				raise
			del e
			raise portage.exception.PermissionDenied(mypath)
		ftype = []
		for x in list:
			try:
				if followSymlinks:
					pathstat = os.stat(mypath+"/"+x)
				else:
					pathstat = os.lstat(mypath+"/"+x)

				if stat.S_ISREG(pathstat[stat.ST_MODE]):
					ftype.append(0)
				elif stat.S_ISDIR(pathstat[stat.ST_MODE]):
					ftype.append(1)
				elif stat.S_ISLNK(pathstat[stat.ST_MODE]):
					ftype.append(2)
				else:
					ftype.append(3)
			except (IOError, OSError):
				ftype.append(3)
		dircache[mypath] = mtime, list, ftype

	ret_list = []
	ret_ftype = []
	for x in range(0, len(list)):
		if(ignorecvs and (len(list[x]) > 2) and (list[x][:2]!=".#")):
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])
		elif (list[x] not in ignorelist):
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])

	writemsg("cacheddirStats: H:%d/M:%d/S:%d\n" % (cacheHit, cacheMiss, cacheStale),10)
	return ret_list, ret_ftype

def listdir(mypath, recursive=False, filesonly=False, ignorecvs=False, ignorelist=[], followSymlinks=True,
	EmptyOnError=False, dirsonly=False):
	"""
	Portage-specific implementation of os.listdir

	@param mypath: Path whose contents you wish to list
	@type mypath: String
	@param recursive: Recursively scan directories contained within mypath
	@type recursive: Boolean
	@param filesonly; Only return files, not more directories
	@type filesonly: Boolean
	@param ignorecvs: Ignore CVS directories ('CVS','.svn','SCCS')
	@type ignorecvs: Boolean
	@param ignorelist: List of filenames/directories to exclude
	@type ignorelist: List
	@param followSymlinks: Follow Symlink'd files and directories
	@type followSymlinks: Boolean
	@param EmptyOnError: Return [] if an error occurs.
	@type EmptyOnError: Boolean
	@param dirsonly: Only return directories.
	@type dirsonly: Boolean
	@rtype: List
	@returns: A list of files and directories (or just files or just directories) or an empty list.
	"""

	list, ftype = cacheddir(mypath, ignorecvs, ignorelist, EmptyOnError, followSymlinks)

	if list is None:
		list=[]
	if ftype is None:
		ftype=[]

	if not (filesonly or dirsonly or recursive):
		return list

	if recursive:
		x=0
		while x<len(ftype):
			if ftype[x]==1 and not (ignorecvs and os.path.basename(list[x]) in ('CVS','.svn','SCCS')):
				l,f = cacheddir(mypath+"/"+list[x], ignorecvs, ignorelist, EmptyOnError,
					followSymlinks)

				l=l[:]
				for y in range(0,len(l)):
					l[y]=list[x]+"/"+l[y]
				list=list+l
				ftype=ftype+f
			x+=1
	if filesonly:
		rlist=[]
		for x in range(0,len(ftype)):
			if ftype[x]==0:
				rlist=rlist+[list[x]]
	elif dirsonly:
		rlist = []
		for x in range(0, len(ftype)):
			if ftype[x] == 1:
				rlist = rlist + [list[x]]	
	else:
		rlist=list

	return rlist

def flatten(mytokens):
	"""this function now turns a [1,[2,3]] list into
	a [1,2,3] list and returns it."""
	newlist=[]
	for x in mytokens:
		if isinstance(x, list):
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist

#beautiful directed graph object

class digraph(object):
	def __init__(self):
		"""Create an empty digraph"""
		
		# { node : ( { child : priority } , { parent : priority } ) }
		self.nodes = {}
		self.order = []

	def add(self, node, parent, priority=0):
		"""Adds the specified node with the specified parent.
		
		If the dep is a soft-dep and the node already has a hard
		relationship to the parent, the relationship is left as hard."""
		
		if node not in self.nodes:
			self.nodes[node] = ({}, {})
			self.order.append(node)
		
		if not parent:
			return
		
		if parent not in self.nodes:
			self.nodes[parent] = ({}, {})
			self.order.append(parent)
		
		if parent in self.nodes[node][1]:
			if priority > self.nodes[node][1][parent]:
				self.nodes[node][1][parent] = priority
		else:
			self.nodes[node][1][parent] = priority
		
		if node in self.nodes[parent][0]:
			if priority > self.nodes[parent][0][node]:
				self.nodes[parent][0][node] = priority
		else:
			self.nodes[parent][0][node] = priority

	def remove(self, node):
		"""Removes the specified node from the digraph, also removing
		and ties to other nodes in the digraph. Raises KeyError if the
		node doesn't exist."""
		
		if node not in self.nodes:
			raise KeyError(node)
		
		for parent in self.nodes[node][1]:
			del self.nodes[parent][0][node]
		for child in self.nodes[node][0]:
			del self.nodes[child][1][node]
		
		del self.nodes[node]
		self.order.remove(node)

	def contains(self, node):
		"""Checks if the digraph contains mynode"""
		return node in self.nodes

	def all_nodes(self):
		"""Return a list of all nodes in the graph"""
		return self.order[:]

	def child_nodes(self, node, ignore_priority=None):
		"""Return all children of the specified node"""
		if ignore_priority is None:
			return self.nodes[node][0].keys()
		children = []
		for child, priority in self.nodes[node][0].iteritems():
			if priority > ignore_priority:
				children.append(child)
		return children

	def parent_nodes(self, node):
		"""Return all parents of the specified node"""
		return self.nodes[node][1].keys()

	def leaf_nodes(self, ignore_priority=None):
		"""Return all nodes that have no children
		
		If ignore_soft_deps is True, soft deps are not counted as
		children in calculations."""
		
		leaf_nodes = []
		for node in self.order:
			is_leaf_node = True
			for child in self.nodes[node][0]:
				if self.nodes[node][0][child] > ignore_priority:
					is_leaf_node = False
					break
			if is_leaf_node:
				leaf_nodes.append(node)
		return leaf_nodes

	def root_nodes(self, ignore_priority=None):
		"""Return all nodes that have no parents.
		
		If ignore_soft_deps is True, soft deps are not counted as
		parents in calculations."""
		
		root_nodes = []
		for node in self.order:
			is_root_node = True
			for parent in self.nodes[node][1]:
				if self.nodes[node][1][parent] > ignore_priority:
					is_root_node = False
					break
			if is_root_node:
				root_nodes.append(node)
		return root_nodes

	def is_empty(self):
		"""Checks if the digraph is empty"""
		return len(self.nodes) == 0

	def clone(self):
		clone = digraph()
		clone.nodes = {}
		for k, v in self.nodes.iteritems():
			clone.nodes[k] = (v[0].copy(), v[1].copy())
		clone.order = self.order[:]
		return clone

	# Backward compatibility
	addnode = add
	allnodes = all_nodes
	allzeros = leaf_nodes
	hasnode = contains
	empty = is_empty
	copy = clone

	def delnode(self, node):
		try:
			self.remove(node)
		except KeyError:
			pass

	def firstzero(self):
		leaf_nodes = self.leaf_nodes()
		if leaf_nodes:
			return leaf_nodes[0]
		return None

	def hasallzeros(self, ignore_priority=None):
		return len(self.leaf_nodes(ignore_priority=ignore_priority)) == \
			len(self.order)

	def debug_print(self):
		for node in self.nodes:
			print node,
			if self.nodes[node][0]:
				print "depends on"
			else:
				print "(no children)"
			for child in self.nodes[node][0]:
				print "  ",child,
				print "(%s)" % self.nodes[node][0][child]


#parse /etc/env.d and generate /etc/profile.env

def env_update(makelinks=1, target_root=None, prev_mtimes=None, contents=None,
	env=None):
	if target_root is None:
		global root
		target_root = root
	if prev_mtimes is None:
		global mtimedb
		prev_mtimes = mtimedb["ldpath"]
	if env is None:
		env = os.environ
	envd_dir = os.path.join(target_root, "etc", "env.d")
	portage.util.ensure_dirs(envd_dir, mode=0755)
	fns = listdir(envd_dir, EmptyOnError=1)
	fns.sort()
	templist = []
	for x in fns:
		if len(x) < 3:
			continue
		if not x[0].isdigit() or not x[1].isdigit():
			continue
		if x.startswith(".") or x.endswith("~") or x.endswith(".bak"):
			continue
		templist.append(x)
	fns = templist
	del templist

	space_separated = set(["CONFIG_PROTECT", "CONFIG_PROTECT_MASK"])
	colon_separated = set(["ADA_INCLUDE_PATH", "ADA_OBJECTS_PATH",
		"CLASSPATH", "INFODIR", "INFOPATH", "KDEDIRS", "LDPATH", "MANPATH",
		  "PATH", "PKG_CONFIG_PATH", "PRELINK_PATH", "PRELINK_PATH_MASK",
		  "PYTHONPATH", "ROOTPATH"])

	config_list = []

	for x in fns:
		file_path = os.path.join(envd_dir, x)
		try:
			myconfig = getconfig(file_path, expand=False)
		except portage.exception.ParseError, e:
			writemsg("!!! '%s'\n" % str(e), noiselevel=-1)
			del e
			continue
		if myconfig is None:
			# broken symlink or file removed by a concurrent process
			writemsg("!!! File Not Found: '%s'\n" % file_path, noiselevel=-1)
			continue
		config_list.append(myconfig)
		if "SPACE_SEPARATED" in myconfig:
			space_separated.update(myconfig["SPACE_SEPARATED"].split())
			del myconfig["SPACE_SEPARATED"]
		if "COLON_SEPARATED" in myconfig:
			colon_separated.update(myconfig["COLON_SEPARATED"].split())
			del myconfig["COLON_SEPARATED"]

	env = {}
	specials = {}
	for var in space_separated:
		mylist = []
		for myconfig in config_list:
			if var in myconfig:
				for item in myconfig[var].split():
					if item and not item in mylist:
						mylist.append(item)
				del myconfig[var] # prepare for env.update(myconfig)
		if mylist:
			env[var] = " ".join(mylist)
		specials[var] = mylist

	for var in colon_separated:
		mylist = []
		for myconfig in config_list:
			if var in myconfig:
				for item in myconfig[var].split(":"):
					if item and not item in mylist:
						mylist.append(item)
				del myconfig[var] # prepare for env.update(myconfig)
		if mylist:
			env[var] = ":".join(mylist)
		specials[var] = mylist

	for myconfig in config_list:
		"""Cumulative variables have already been deleted from myconfig so that
		they won't be overwritten by this dict.update call."""
		env.update(myconfig)

	ldsoconf_path = os.path.join(target_root, "etc", "ld.so.conf")
	try:
		myld = open(ldsoconf_path)
		myldlines=myld.readlines()
		myld.close()
		oldld=[]
		for x in myldlines:
			#each line has at least one char (a newline)
			if x[0]=="#":
				continue
			oldld.append(x[:-1])
	except (IOError, OSError), e:
		if e.errno != errno.ENOENT:
			raise
		oldld = None

	ld_cache_update=False

	newld = specials["LDPATH"]
	if (oldld!=newld):
		#ld.so.conf needs updating and ldconfig needs to be run
		myfd = atomic_ofstream(ldsoconf_path)
		myfd.write("# ld.so.conf autogenerated by env-update; make all changes to\n")
		myfd.write("# contents of /etc/env.d directory\n")
		for x in specials["LDPATH"]:
			myfd.write(x+"\n")
		myfd.close()
		ld_cache_update=True

	# Update prelink.conf if we are prelink-enabled
	if prelink_capable:
		newprelink = atomic_ofstream(
			os.path.join(target_root, "etc", "prelink.conf"))
		newprelink.write("# prelink.conf autogenerated by env-update; make all changes to\n")
		newprelink.write("# contents of /etc/env.d directory\n")

		for x in ["/bin","/sbin","/usr/bin","/usr/sbin","/lib","/usr/lib"]:
			newprelink.write("-l "+x+"\n");
		for x in specials["LDPATH"]+specials["PATH"]+specials["PRELINK_PATH"]:
			if not x:
				continue
			if x[-1]!='/':
				x=x+"/"
			plmasked=0
			for y in specials["PRELINK_PATH_MASK"]:
				if not y:
					continue
				if y[-1]!='/':
					y=y+"/"
				if y==x[0:len(y)]:
					plmasked=1
					break
			if not plmasked:
				newprelink.write("-h "+x+"\n")
		for x in specials["PRELINK_PATH_MASK"]:
			newprelink.write("-b "+x+"\n")
		newprelink.close()

	# Portage stores mtimes with 1 second granularity but in >=python-2.5 finer
	# granularity is possible.  In order to avoid the potential ambiguity of
	# mtimes that differ by less than 1 second, sleep here if any of the
	# directories have been modified during the current second.
	sleep_for_mtime_granularity = False
	current_time = long(time.time())
	mtime_changed = False
	lib_dirs = set()
	for lib_dir in portage.util.unique_array(specials["LDPATH"]+['usr/lib','usr/lib64','usr/lib32','lib','lib64','lib32']):
		x = os.path.join(target_root, lib_dir.lstrip(os.sep))
		try:
			newldpathtime = long(os.stat(x).st_mtime)
			lib_dirs.add(normalize_path(x))
		except OSError, oe:
			if oe.errno == errno.ENOENT:
				try:
					del prev_mtimes[x]
				except KeyError:
					pass
				# ignore this path because it doesn't exist
				continue
			raise
		if newldpathtime == current_time:
			sleep_for_mtime_granularity = True
		if x in prev_mtimes:
			if prev_mtimes[x] == newldpathtime:
				pass
			else:
				prev_mtimes[x] = newldpathtime
				mtime_changed = True
		else:
			prev_mtimes[x] = newldpathtime
			mtime_changed = True

	if mtime_changed:
		ld_cache_update = True

	if makelinks and \
		not ld_cache_update and \
		contents is not None:
		libdir_contents_changed = False
		for mypath, mydata in contents.iteritems():
			if mydata[0] not in ("obj","sym"):
				continue
			head, tail = os.path.split(mypath)
			if head in lib_dirs:
				libdir_contents_changed = True
				break
		if not libdir_contents_changed:
			makelinks = False

	ldconfig = "/sbin/ldconfig"
	if "CHOST" in env and "CBUILD" in env and \
		env["CHOST"] != env["CBUILD"]:
		from portage.process import find_binary
		ldconfig = find_binary("%s-ldconfig" % env["CHOST"])

	# Only run ldconfig as needed
	if (ld_cache_update or makelinks) and ldconfig:
		# ldconfig has very different behaviour between FreeBSD and Linux
		if ostype=="Linux" or ostype.lower().endswith("gnu"):
			# We can't update links if we haven't cleaned other versions first, as
			# an older package installed ON TOP of a newer version will cause ldconfig
			# to overwrite the symlinks we just made. -X means no links. After 'clean'
			# we can safely create links.
			writemsg(">>> Regenerating %setc/ld.so.cache...\n" % target_root)
			if makelinks:
				os.system("cd / ; %s -r '%s'" % (ldconfig, target_root))
			else:
				os.system("cd / ; %s -X -r '%s'" % (ldconfig, target_root))
		elif ostype in ("FreeBSD","DragonFly"):
			writemsg(">>> Regenerating %svar/run/ld-elf.so.hints...\n" % \
				target_root)
			os.system(("cd / ; %s -elf -i " + \
				"-f '%svar/run/ld-elf.so.hints' '%setc/ld.so.conf'") % \
				(ldconfig, target_root, target_root))

	del specials["LDPATH"]

	penvnotice  = "# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.\n"
	penvnotice += "# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES\n"
	cenvnotice  = penvnotice[:]
	penvnotice += "# GO INTO /etc/profile NOT /etc/profile.env\n\n"
	cenvnotice += "# GO INTO /etc/csh.cshrc NOT /etc/csh.env\n\n"

	#create /etc/profile.env for bash support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "profile.env"))
	outfile.write(penvnotice)

	env_keys = [ x for x in env if x != "LDPATH" ]
	env_keys.sort()
	for k in env_keys:
		v = env[k]
		if v.startswith('$') and not v.startswith('${'):
			outfile.write("export %s=$'%s'\n" % (k, v[1:]))
		else:
			outfile.write("export %s='%s'\n" % (k, v))
	outfile.close()

	#create /etc/csh.env for (t)csh support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "csh.env"))
	outfile.write(cenvnotice)
	for x in env_keys:
		outfile.write("setenv %s '%s'\n" % (x, env[x]))
	outfile.close()

	if sleep_for_mtime_granularity:
		while current_time == long(time.time()):
			sleep(1)

def ExtractKernelVersion(base_dir):
	"""
	Try to figure out what kernel version we are running
	@param base_dir: Path to sources (usually /usr/src/linux)
	@type base_dir: string
	@rtype: tuple( version[string], error[string])
	@returns:
	1. tuple( version[string], error[string])
	Either version or error is populated (but never both)

	"""
	lines = []
	pathname = os.path.join(base_dir, 'Makefile')
	try:
		f = open(pathname, 'r')
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))

	try:
		for i in range(4):
			lines.append(f.readline())
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))

	lines = [l.strip() for l in lines]

	version = ''

	#XXX: The following code relies on the ordering of vars within the Makefile
	for line in lines:
		# split on the '=' then remove annoying whitespace
		items = line.split("=")
		items = [i.strip() for i in items]
		if items[0] == 'VERSION' or \
			items[0] == 'PATCHLEVEL':
			version += items[1]
			version += "."
		elif items[0] == 'SUBLEVEL':
			version += items[1]
		elif items[0] == 'EXTRAVERSION' and \
			items[-1] != items[0]:
			version += items[1]

	# Grab a list of files named localversion* and sort them
	localversions = os.listdir(base_dir)
	for x in range(len(localversions)-1,-1,-1):
		if localversions[x][:12] != "localversion":
			del localversions[x]
	localversions.sort()

	# Append the contents of each to the version string, stripping ALL whitespace
	for lv in localversions:
		version += "".join( " ".join( grabfile( base_dir+ "/" + lv ) ).split() )

	# Check the .config for a CONFIG_LOCALVERSION and append that too, also stripping whitespace
	kernelconfig = getconfig(base_dir+"/.config")
	if kernelconfig and kernelconfig.has_key("CONFIG_LOCALVERSION"):
		version += "".join(kernelconfig["CONFIG_LOCALVERSION"].split())

	return (version,None)

def autouse(myvartree, use_cache=1, mysettings=None):
	"""
	autuse returns a list of USE variables auto-enabled to packages being installed

	@param myvartree: Instance of the vartree class (from /var/db/pkg...)
	@type myvartree: vartree
	@param use_cache: read values from cache
	@type use_cache: Boolean
	@param mysettings: Instance of config
	@type mysettings: config
	@rtype: string
	@returns: A string containing a list of USE variables that are enabled via use.defaults
	"""
	if mysettings is None:
		global settings
		mysettings = settings
	if mysettings.profile_path is None:
		return ""
	myusevars=""
	usedefaults = mysettings.use_defs
	for myuse in usedefaults:
		dep_met = True
		for mydep in usedefaults[myuse]:
			if not myvartree.dep_match(mydep,use_cache=True):
				dep_met = False
				break
		if dep_met:
			myusevars += " "+myuse
	return myusevars

def check_config_instance(test):
	if not isinstance(test, config):
		raise TypeError("Invalid type for config object: %s (should be %s)" % (test.__class__, config))

class config(object):
	"""
	This class encompasses the main portage configuration.  Data is pulled from
	ROOT/PORTDIR/profiles/, from ROOT/etc/make.profile incrementally through all 
	parent profiles as well as from ROOT/PORTAGE_CONFIGROOT/* for user specified
	overrides.
	
	Generally if you need data like USE flags, FEATURES, environment variables,
	virtuals ...etc you look in here.
	"""

	_environ_whitelist = []

	# Whitelisted variables are always allowed to enter the ebuild
	# environment. Generally, this only includes special portage
	# variables. Ebuilds can unset variables that are not whitelisted
	# and rely on them remaining unset for future phases, without them
	# leaking back in from various locations (bug #189417). It's very
	# important to set our special BASH_ENV variable in the ebuild
	# environment in order to prevent sandbox from sourcing /etc/profile
	# in it's bashrc (causing major leakage).
	_environ_whitelist += [
		"BASH_ENV", "BUILD_PREFIX", "D",
		"DISTDIR", "DOC_SYMLINKS_DIR", "EBUILD",
		"EBUILD_EXIT_STATUS_FILE", "EBUILD_FORCE_TEST",
		"EBUILD_PHASE", "ECLASSDIR", "ECLASS_DEPTH", "EMERGE_FROM",
		"FEATURES", "FILESDIR", "HOME", "PATH",
		"PKGDIR",
		"PKGUSE", "PKG_LOGDIR", "PKG_TMPDIR",
		"PORTAGE_ACTUAL_DISTDIR", "PORTAGE_ARCHLIST",
		"PORTAGE_BASHRC",
		"PORTAGE_BINPKG_FILE", "PORTAGE_BINPKG_TMPFILE",
		"PORTAGE_BIN_PATH",
		"PORTAGE_BUILDDIR", "PORTAGE_COLORMAP",
		"PORTAGE_CONFIGROOT", "PORTAGE_DEBUG", "PORTAGE_DEPCACHEDIR",
		"PORTAGE_GID", "PORTAGE_INST_GID", "PORTAGE_INST_UID",
		"PORTAGE_IUSE",
		"PORTAGE_LOG_FILE", "PORTAGE_MASTER_PID",
		"PORTAGE_PYM_PATH", "PORTAGE_REPO_NAME", "PORTAGE_RESTRICT",
		"PORTAGE_TMPDIR", "PORTAGE_UPDATE_ENV", "PORTAGE_WORKDIR_MODE",
		"PORTDIR", "PORTDIR_OVERLAY", "PREROOTPATH", "PROFILE_PATHS",
		"ROOT", "ROOTPATH", "STARTDIR", "T", "TMP", "TMPDIR",
		"USE_EXPAND", "USE_ORDER", "WORKDIR",
		"XARGS",
	]

	_environ_whitelist += [
		"A", "AA", "CATEGORY", "P", "PF", "PN", "PR", "PV", "PVR"
	]

	# misc variables inherited from the calling environment
	_environ_whitelist += [
		"COLORTERM", "DISPLAY", "EDITOR", "LESS",
		"LESSOPEN", "LOGNAME", "LS_COLORS", "PAGER",
		"TERM", "TERMCAP", "USER",
	]

	# other variables inherited from the calling environment
	_environ_whitelist += [
		"CVS_RSH", "ECHANGELOG_USER",
		"GPG_AGENT_INFO",
		"SSH_AGENT_PID", "SSH_AUTH_SOCK",
		"STY", "WINDOW", "XAUTHORITY",
	]

	_environ_whitelist = frozenset(_environ_whitelist)

	_environ_whitelist_re = re.compile(r'^(CCACHE_|DISTCC_).*')

	# Filter selected variables in the config.environ() method so that
	# they don't needlessly propagate down into the ebuild environment.
	_environ_filter = []

	# misc variables inherited from the calling environment
	_environ_filter += [
		"INFOPATH", "MANPATH",
	]

	# portage config variables and variables set directly by portage
	_environ_filter += [
		"ACCEPT_KEYWORDS", "AUTOCLEAN",
		"CLEAN_DELAY", "COLLISION_IGNORE", "CONFIG_PROTECT",
		"CONFIG_PROTECT_MASK", "EMERGE_DEFAULT_OPTS",
		"EMERGE_WARNING_DELAY", "FETCHCOMMAND", "FETCHCOMMAND_FTP",
		"FETCHCOMMAND_HTTP", "FETCHCOMMAND_SFTP",
		"GENTOO_MIRRORS", "NOCONFMEM", "O",
		"PORTAGE_BINHOST_CHUNKSIZE", "PORTAGE_CALLER",
		"PORTAGE_ECLASS_WARNING_ENABLE", "PORTAGE_ELOG_CLASSES",
		"PORTAGE_ELOG_MAILFROM", "PORTAGE_ELOG_MAILSUBJECT",
		"PORTAGE_ELOG_MAILURI", "PORTAGE_ELOG_SYSTEM", "PORTAGE_GPG_DIR",
		"PORTAGE_GPG_KEY", "PORTAGE_PACKAGE_EMPTY_ABORT",
		"PORTAGE_RSYNC_EXTRA_OPTS", "PORTAGE_RSYNC_OPTS",
		"PORTAGE_RSYNC_RETRIES", "PORTAGE_USE", "PORT_LOGDIR",
		"QUICKPKG_DEFAULT_OPTS",
		"RESUMECOMMAND", "RESUMECOMMAND_HTTP", "RESUMECOMMAND_HTTP",
		"RESUMECOMMAND_SFTP", "SYNC", "USE_EXPAND_HIDDEN", "USE_ORDER",
	]

	_environ_filter = frozenset(_environ_filter)

	def __init__(self, clone=None, mycpv=None, config_profile_path=None,
		config_incrementals=None, config_root=None, target_root=None,
		local_config=True):
		"""
		@param clone: If provided, init will use deepcopy to copy by value the instance.
		@type clone: Instance of config class.
		@param mycpv: CPV to load up (see setcpv), this is the same as calling init with mycpv=None
		and then calling instance.setcpv(mycpv).
		@type mycpv: String
		@param config_profile_path: Configurable path to the profile (usually PROFILE_PATH from portage.const)
		@type config_profile_path: String
		@param config_incrementals: List of incremental variables (usually portage.const.INCREMENTALS)
		@type config_incrementals: List
		@param config_root: path to read local config from (defaults to "/", see PORTAGE_CONFIGROOT)
		@type config_root: String
		@param target_root: __init__ override of $ROOT env variable.
		@type target_root: String
		@param local_config: Enables loading of local config (/etc/portage); used most by repoman to
		ignore local config (keywording and unmasking)
		@type local_config: Boolean
		"""

		# When initializing the global portage.settings instance, avoid
		# raising exceptions whenever possible since exceptions thrown
		# from 'import portage' or 'import portage.exceptions' statements
		# can practically render the api unusable for api consumers.
		tolerant = "_initializing_globals" in globals()

		self.already_in_regenerate = 0

		self._filter_calling_env = False
		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []
		self.uvlist = []

		self.virtuals = {}
		self.virts_p = {}
		self.dirVirtuals = None
		self.v_count  = 0

		# Virtuals obtained from the vartree
		self.treeVirtuals = {}
		# Virtuals by user specification. Includes negatives.
		self.userVirtuals = {}
		# Virtual negatives from user specifications.
		self.negVirtuals  = {}
		# Virtuals added by the depgraph via self.setinst().
		self._depgraphVirtuals = {}

		self.user_profile_dir = None
		self.local_config = local_config
		self._use_wildcards = False

		if clone:
			self._filter_calling_env = copy.deepcopy(clone._filter_calling_env)
			self.incrementals = copy.deepcopy(clone.incrementals)
			self.profile_path = copy.deepcopy(clone.profile_path)
			self.user_profile_dir = copy.deepcopy(clone.user_profile_dir)
			self.local_config = copy.deepcopy(clone.local_config)

			self.module_priority = copy.deepcopy(clone.module_priority)
			self.modules         = copy.deepcopy(clone.modules)

			self.depcachedir = copy.deepcopy(clone.depcachedir)

			self.packages = copy.deepcopy(clone.packages)
			self.virtuals = copy.deepcopy(clone.virtuals)

			self.dirVirtuals = copy.deepcopy(clone.dirVirtuals)
			self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
			self.userVirtuals = copy.deepcopy(clone.userVirtuals)
			self.negVirtuals  = copy.deepcopy(clone.negVirtuals)
			self._depgraphVirtuals = copy.deepcopy(clone._depgraphVirtuals)

			self.use_defs = copy.deepcopy(clone.use_defs)
			self.usemask  = copy.deepcopy(clone.usemask)
			self.usemask_list = copy.deepcopy(clone.usemask_list)
			self.pusemask_list = copy.deepcopy(clone.pusemask_list)
			self.useforce      = copy.deepcopy(clone.useforce)
			self.useforce_list = copy.deepcopy(clone.useforce_list)
			self.puseforce_list = copy.deepcopy(clone.puseforce_list)
			self.puse     = copy.deepcopy(clone.puse)
			self.make_defaults_use = copy.deepcopy(clone.make_defaults_use)
			self.pkgprofileuse = copy.deepcopy(clone.pkgprofileuse)
			self.mycpv    = copy.deepcopy(clone.mycpv)

			self.configlist = copy.deepcopy(clone.configlist)
			self.lookuplist = self.configlist[:]
			self.lookuplist.reverse()
			self.configdict = {
				"env.d":     self.configlist[0],
				"pkginternal": self.configlist[1],
				"globals":     self.configlist[2],
				"defaults":    self.configlist[3],
				"conf":        self.configlist[4],
				"pkg":         self.configlist[5],
				"auto":        self.configlist[6],
				"backupenv":   self.configlist[7],
				"env":         self.configlist[8] }
			self.profiles = copy.deepcopy(clone.profiles)
			self.backupenv  = self.configdict["backupenv"]
			self.pusedict   = copy.deepcopy(clone.pusedict)
			self.categories = copy.deepcopy(clone.categories)
			self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
			self.pmaskdict = copy.deepcopy(clone.pmaskdict)
			self.punmaskdict = copy.deepcopy(clone.punmaskdict)
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.pprovideddict = copy.deepcopy(clone.pprovideddict)
			self.features = copy.deepcopy(clone.features)

			self._accept_license = copy.deepcopy(clone._accept_license)
			self._plicensedict = copy.deepcopy(clone._plicensedict)
			self._use_wildcards = copy.deepcopy(clone._use_wildcards)
		else:

			def check_var_directory(varname, var):
				if not os.path.isdir(var):
					writemsg(("!!! Error: %s='%s' is not a directory. " + \
						"Please correct this.\n") % (varname, var),
						noiselevel=-1)
					raise portage.exception.DirectoryNotFound(var)

			if config_root is None:
				config_root = "/"

			config_root = normalize_path(os.path.abspath(
				config_root)).rstrip(os.path.sep) + os.path.sep

			check_var_directory("PORTAGE_CONFIGROOT", config_root)

			self.depcachedir = DEPCACHE_PATH

			if not config_profile_path:
				config_profile_path = \
					os.path.join(config_root, PROFILE_PATH.lstrip(os.path.sep))
				if os.path.isdir(config_profile_path):
					self.profile_path = config_profile_path
				else:
					self.profile_path = None
			else:
				self.profile_path = config_profile_path[:]

			if not config_incrementals:
				writemsg("incrementals not specified to class config\n")
				self.incrementals = copy.deepcopy(portage.const.INCREMENTALS)
			else:
				self.incrementals = copy.deepcopy(config_incrementals)

			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"] = getconfig(
				os.path.join(config_root, MODULES_FILE_PATH.lstrip(os.path.sep)))
			if self.modules["user"] is None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "portage.cache.metadata.database",
				"portdbapi.auxdbmodule":  "portage.cache.flat_hash.database",
			}

			self.usemask=[]
			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ env.d, globals, defaults, conf, pkg, auto, backupenv, env ]
			self.configlist.append({})
			self.configdict["env.d"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkginternal"] = self.configlist[-1]

			# The symlink might not exist or might not be a symlink.
			if self.profile_path is None:
				self.profiles = []
			else:
				self.profiles = []
				def addProfile(currentPath):
					parentsFile = os.path.join(currentPath, "parent")
					if os.path.exists(parentsFile):
						parents = grabfile(parentsFile)
						if not parents:
							raise portage.exception.ParseError(
								"Empty parent file: '%s'" % parents_file)
						for parentPath in parents:
							parentPath = normalize_path(os.path.join(
								currentPath, parentPath))
							if os.path.exists(parentPath):
								addProfile(parentPath)
							else:
								raise portage.exception.ParseError(
									"Parent '%s' not found: '%s'" %  \
									(parentPath, parentsFile))
					self.profiles.append(currentPath)
				try:
					addProfile(os.path.realpath(self.profile_path))
				except portage.exception.ParseError, e:
					writemsg("!!! Unable to parse profile: '%s'\n" % \
						self.profile_path, noiselevel=-1)
					writemsg("!!! ParseError: %s\n" % str(e), noiselevel=-1)
					del e
					self.profiles = []
			if local_config:
				custom_prof = os.path.join(
					config_root, CUSTOM_PROFILE_PATH.lstrip(os.path.sep))
				if os.path.exists(custom_prof):
					self.user_profile_dir = custom_prof
					self.profiles.append(custom_prof)
				del custom_prof

			self.packages_list = [grabfile_package(os.path.join(x, "packages")) for x in self.profiles]
			self.packages      = stack_lists(self.packages_list, incremental=1)
			del self.packages_list
			#self.packages = grab_stacked("packages", self.profiles, grabfile, incremental_lines=1)

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				mycatpkg=dep_getkey(x)
				if not self.prevmaskdict.has_key(mycatpkg):
					self.prevmaskdict[mycatpkg]=[x]
				else:
					self.prevmaskdict[mycatpkg].append(x)

			# get profile-masked use flags -- INCREMENTAL Child over parent
			self.usemask_list = [grabfile(os.path.join(x, "use.mask")) \
				for x in self.profiles]
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			use_defs_lists = [grabdict(os.path.join(x, "use.defaults")) for x in self.profiles]
			self.use_defs  = stack_dictlist(use_defs_lists, incremental=True)
			del use_defs_lists

			self.pusemask_list = []
			rawpusemask = [grabdict_package(
				os.path.join(x, "package.use.mask")) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawpusemask[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.pusemask_list.append(cpdict)
			del rawpusemask

			self.pkgprofileuse = []
			rawprofileuse = [grabdict_package(
				os.path.join(x, "package.use"), juststrings=True) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawprofileuse[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.pkgprofileuse.append(cpdict)
			del rawprofileuse

			self.useforce_list = [grabfile(os.path.join(x, "use.force")) \
				for x in self.profiles]
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))

			self.puseforce_list = []
			rawpuseforce = [grabdict_package(
				os.path.join(x, "package.use.force")) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawpuseforce[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.puseforce_list.append(cpdict)
			del rawpuseforce

			# make.globals should not be relative to config_root
			# because it only contains constants.
			self.mygcfg   = getconfig(os.path.join("/etc", "make.globals"))

			if self.mygcfg is None:
				self.mygcfg = {}

			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.make_defaults_use = []
			self.mygcfg = {}
			if self.profiles:
				mygcfg_dlists = [getconfig(os.path.join(x, "make.defaults")) \
					for x in self.profiles]
				for cfg in mygcfg_dlists:
					if cfg:
						self.make_defaults_use.append(cfg.get("USE", ""))
					else:
						self.make_defaults_use.append("")
				self.mygcfg = stack_dicts(mygcfg_dlists,
					incrementals=portage.const.INCREMENTALS, ignore_none=1)
				if self.mygcfg is None:
					self.mygcfg = {}
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			self.mygcfg = getconfig(
				os.path.join(config_root, MAKE_CONF_FILE.lstrip(os.path.sep)),
				tolerant=tolerant, allow_sourcing=True)
			if self.mygcfg is None:
				self.mygcfg = {}

			# Don't allow the user to override certain variables in make.conf
			profile_only_variables = self.configdict["defaults"].get(
				"PROFILE_ONLY_VARIABLES", "").split()
			for k in profile_only_variables:
				self.mygcfg.pop(k, None)
			
			# Allow ROOT setting to come from make.conf if it's not overridden
			# by the constructor argument (from the calling environment).  As a
			# special exception for a very common use case, config_root == "/"
			# implies that ROOT in make.conf should be ignored.  That way, the
			# user can chroot into $ROOT and the ROOT setting in make.conf will
			# be automatically ignored (unless config_root is other than "/").
			if config_root != "/" and \
				target_root is None and "ROOT" in self.mygcfg:
				target_root = self.mygcfg["ROOT"]
			
			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

			# backupenv is used for calculating incremental variables.
			self.backupenv = os.environ.copy()
			self.configlist.append(self.backupenv) # XXX Why though?
			self.configdict["backupenv"]=self.configlist[-1]

			# Don't allow the user to override certain variables in the env
			for k in profile_only_variables:
				self.backupenv.pop(k, None)

			self.configlist.append(self.backupenv.copy())
			self.configdict["env"]=self.configlist[-1]

			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			# Blacklist vars that could interfere with portage internals.
			for blacklisted in "CATEGORY", "PKGUSE", "PORTAGE_CONFIGROOT", \
				"PORTAGE_IUSE", "PORTAGE_USE", "ROOT":
				for cfg in self.lookuplist:
					cfg.pop(blacklisted, None)
			del blacklisted, cfg

			if target_root is None:
				target_root = "/"

			target_root = normalize_path(os.path.abspath(
				target_root)).rstrip(os.path.sep) + os.path.sep

			portage.util.ensure_dirs(target_root)
			check_var_directory("ROOT", target_root)

			env_d = getconfig(
				os.path.join(target_root, "etc", "profile.env"), expand=False)
			# env_d will be None if profile.env doesn't exist.
			if env_d:
				self.configdict["env.d"].update(env_d)
				# Remove duplicate values so they don't override updated
				# profile.env values later (profile.env is reloaded in each
				# call to self.regenerate).
				for cfg in (self.configdict["backupenv"],
					self.configdict["env"]):
					for k, v in env_d.iteritems():
						try:
							if cfg[k] == v:
								del cfg[k]
						except KeyError:
							pass
				del cfg, k, v

			self["PORTAGE_CONFIGROOT"] = config_root
			self.backup_changes("PORTAGE_CONFIGROOT")
			self["ROOT"] = target_root
			self.backup_changes("ROOT")

			self.pusedict = {}
			self.pkeywordsdict = {}
			self._plicensedict = {}
			self.punmaskdict = {}
			abs_user_config = os.path.join(config_root,
				USER_CONFIG_PATH.lstrip(os.path.sep))

			# locations for "categories" and "arch.list" files
			locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations.extend(self.profiles)

			""" repoman controls PORTDIR_OVERLAY via the environment, so no
			special cases are needed here."""
			overlay_profiles = []
			for ov in self["PORTDIR_OVERLAY"].split():
				ov = normalize_path(ov)
				profiles_dir = os.path.join(ov, "profiles")
				if os.path.isdir(profiles_dir):
					overlay_profiles.append(profiles_dir)
			locations += overlay_profiles
			
			pmask_locations.extend(overlay_profiles)

			if local_config:
				locations.append(abs_user_config)
				pmask_locations.append(abs_user_config)
				pusedict = grabdict_package(
					os.path.join(abs_user_config, "package.use"), recursive=1)
				for key in pusedict.keys():
					cp = dep_getkey(key)
					if not self.pusedict.has_key(cp):
						self.pusedict[cp] = {}
					self.pusedict[cp][key] = pusedict[key]
					if not self._use_wildcards:
						for x in pusedict[key]:
							if x.endswith("_*"):
								self._use_wildcards = True
								break

				#package.keywords
				pkgdict = grabdict_package(
					os.path.join(abs_user_config, "package.keywords"),
					recursive=1)
				for key in pkgdict.keys():
					# default to ~arch if no specific keyword is given
					if not pkgdict[key]:
						mykeywordlist = []
						if self.configdict["defaults"] and self.configdict["defaults"].has_key("ACCEPT_KEYWORDS"):
							groups = self.configdict["defaults"]["ACCEPT_KEYWORDS"].split()
						else:
							groups = []
						for keyword in groups:
							if not keyword[0] in "~-":
								mykeywordlist.append("~"+keyword)
						pkgdict[key] = mykeywordlist
					cp = dep_getkey(key)
					if not self.pkeywordsdict.has_key(cp):
						self.pkeywordsdict[cp] = {}
					self.pkeywordsdict[cp][key] = pkgdict[key]
				
				#package.license
				licdict = grabdict_package(os.path.join(
					abs_user_config, "package.license"), recursive=1)
				for k, v in licdict.iteritems():
					cp = dep_getkey(k)
					cp_dict = self._plicensedict.get(cp)
					if not cp_dict:
						cp_dict = {}
						self._plicensedict[cp] = cp_dict
					cp_dict[k] = self.expandLicenseTokens(v)

				#package.unmask
				pkgunmasklines = grabfile_package(
					os.path.join(abs_user_config, "package.unmask"),
					recursive=1)
				for x in pkgunmasklines:
					mycatpkg=dep_getkey(x)
					if self.punmaskdict.has_key(mycatpkg):
						self.punmaskdict[mycatpkg].append(x)
					else:
						self.punmaskdict[mycatpkg]=[x]

			#getting categories from an external file now
			categories = [grabfile(os.path.join(x, "categories")) for x in locations]
			self.categories = stack_lists(categories, incremental=1)
			del categories

			archlist = [grabfile(os.path.join(x, "arch.list")) for x in locations]
			archlist = stack_lists(archlist, incremental=1)
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = " ".join(archlist)

			#package.mask
			pkgmasklines = []
			for x in pmask_locations:
				pkgmasklines.append(grabfile_package(
					os.path.join(x, "package.mask"), recursive=1))
			pkgmasklines = stack_lists(pkgmasklines, incremental=1)

			self.pmaskdict = {}
			for x in pkgmasklines:
				mycatpkg=dep_getkey(x)
				if self.pmaskdict.has_key(mycatpkg):
					self.pmaskdict[mycatpkg].append(x)
				else:
					self.pmaskdict[mycatpkg]=[x]

			pkgprovidedlines = [grabfile(os.path.join(x, "package.provided")) for x in self.profiles]
			pkgprovidedlines = stack_lists(pkgprovidedlines, incremental=1)
			has_invalid_data = False
			for x in range(len(pkgprovidedlines)-1, -1, -1):
				myline = pkgprovidedlines[x]
				if not isvalidatom("=" + myline):
					writemsg("Invalid package name in package.provided:" + \
						" %s\n" % myline, noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
				cpvr = catpkgsplit(pkgprovidedlines[x])
				if not cpvr or cpvr[0] == "null":
					writemsg("Invalid package name in package.provided: "+pkgprovidedlines[x]+"\n",
						noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
				if cpvr[0] == "virtual":
					writemsg("Virtual package in package.provided: %s\n" % \
						myline, noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
			if has_invalid_data:
				writemsg("See portage(5) for correct package.provided usage.\n",
					noiselevel=-1)
			self.pprovideddict = {}
			for x in pkgprovidedlines:
				cpv=catpkgsplit(x)
				if not x:
					continue
				mycatpkg=dep_getkey(x)
				if self.pprovideddict.has_key(mycatpkg):
					self.pprovideddict[mycatpkg].append(x)
				else:
					self.pprovideddict[mycatpkg]=[x]

			# parse licensegroups
			self._license_groups = {}
			for x in locations:
				self._license_groups.update(
					grabdict(os.path.join(x, "license_groups")))

			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			if "USE_ORDER" not in self:
				self.backupenv["USE_ORDER"] = "env:pkg:conf:defaults:pkginternal:env.d"

			self["PORTAGE_GID"] = str(portage_gid)
			self.backup_changes("PORTAGE_GID")

			if self.get("PORTAGE_DEPCACHEDIR", None):
				self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			self["PORTAGE_DEPCACHEDIR"] = self.depcachedir
			self.backup_changes("PORTAGE_DEPCACHEDIR")

			overlays = self.get("PORTDIR_OVERLAY","").split()
			if overlays:
				new_ov = []
				for ov in overlays:
					ov = normalize_path(ov)
					if os.path.isdir(ov):
						new_ov.append(ov)
					else:
						writemsg("!!! Invalid PORTDIR_OVERLAY" + \
							" (not a dir): '%s'\n" % ov, noiselevel=-1)
				self["PORTDIR_OVERLAY"] = " ".join(new_ov)
				self.backup_changes("PORTDIR_OVERLAY")

			if "CBUILD" not in self and "CHOST" in self:
				self["CBUILD"] = self["CHOST"]
				self.backup_changes("CBUILD")

			self["PORTAGE_BIN_PATH"] = PORTAGE_BIN_PATH
			self.backup_changes("PORTAGE_BIN_PATH")
			self["PORTAGE_PYM_PATH"] = PORTAGE_PYM_PATH
			self.backup_changes("PORTAGE_PYM_PATH")

			# Expand license groups
			# This has to do be done for each config layer before regenerate()
			# in order for incremental negation to work properly.
			if local_config:
				for c in self.configdict.itervalues():
					v = c.get("ACCEPT_LICENSE")
					if not v:
						continue
					v = " ".join(self.expandLicenseTokens(v.split()))
					c["ACCEPT_LICENSE"] = v
					del c, v

			for var in ("PORTAGE_INST_UID", "PORTAGE_INST_GID"):
				try:
					self[var] = str(int(self.get(var, "0")))
				except ValueError:
					writemsg(("!!! %s='%s' is not a valid integer.  " + \
						"Falling back to '0'.\n") % (var, self[var]),
						noiselevel=-1)
					self[var] = "0"
				self.backup_changes(var)

			# initialize self.features
			self.regenerate()

			if local_config:
				self._accept_license = \
					set(self.get("ACCEPT_LICENSE", "").split())
				# In order to enforce explicit acceptance for restrictive
				# licenses that require it, "*" will not be allowed in the
				# user config.  Don't enforce this until license groups are
				# fully implemented in the tree.
				#self._accept_license.discard("*")
				if not self._accept_license:
					self._accept_license = set(["*"])
			else:
				# repoman will accept any license
				self._accept_license = set(["*"])

			if "gpg" in self.features:
				if not os.path.exists(self["PORTAGE_GPG_DIR"]) or \
					not os.path.isdir(self["PORTAGE_GPG_DIR"]):
					writemsg(colorize("BAD", "PORTAGE_GPG_DIR is invalid." + \
						" Removing gpg from FEATURES.\n"), noiselevel=-1)
					self.features.remove("gpg")

			if not portage.process.sandbox_capable and \
				("sandbox" in self.features or "usersandbox" in self.features):
				if self.profile_path is not None and \
					os.path.realpath(self.profile_path) == \
					os.path.realpath(PROFILE_PATH):
					""" Don't show this warning when running repoman and the
					sandbox feature came from a profile that doesn't belong to
					the user."""
					writemsg(colorize("BAD", "!!! Problem with sandbox" + \
						" binary. Disabling...\n\n"), noiselevel=-1)
				if "sandbox" in self.features:
					self.features.remove("sandbox")
				if "usersandbox" in self.features:
					self.features.remove("usersandbox")

			self.features.sort()
			if "gpg" in self.features:
				writemsg(colorize("WARN", "!!! FEATURES=gpg is unmaintained, incomplete and broken. Disabling it."), noiselevel=-1)
				self.features.remove("gpg")
			self["FEATURES"] = " ".join(self.features)
			self.backup_changes("FEATURES")

			self._init_dirs()

		if mycpv:
			self.setcpv(mycpv)

	def _init_dirs(self):
		"""
		Create a few directories that are critical to portage operation
		"""
		if not os.access(self["ROOT"], os.W_OK):
			return

		dir_mode_map = {
			"tmp"             : (-1,          01777, 0),
			"var/tmp"         : (-1,          01777, 0),
			PRIVATE_PATH      : (portage_gid, 02750, 02),
			CACHE_PATH.lstrip(os.path.sep) : (portage_gid, 0755, 02)
		}

		for mypath, (gid, mode, modemask) in dir_mode_map.iteritems():
			try:
				mydir = os.path.join(self["ROOT"], mypath)
				portage.util.ensure_dirs(mydir, gid=gid, mode=mode, mask=modemask)
			except portage.exception.PortageException, e:
				writemsg("!!! Directory initialization failed: '%s'\n" % mydir,
					noiselevel=-1)
				writemsg("!!! %s\n" % str(e),
					noiselevel=-1)

	def expandLicenseTokens(self, tokens):
		""" Take a token from ACCEPT_LICENSE or package.license and expand it
		if it's a group token (indicated by @) or just return it if it's not a
		group.  If a group is negated then negate all group elements."""
		expanded_tokens = []
		for x in tokens:
			expanded_tokens.extend(self._expandLicenseToken(x, None))
		return expanded_tokens

	def _expandLicenseToken(self, token, traversed_groups):
		negate = False
		rValue = []
		if token.startswith("-"):
			negate = True
			license_name = token[1:]
		else:
			license_name = token
		if not license_name.startswith("@"):
			rValue.append(token)
			return rValue
		group_name = license_name[1:]
		if not traversed_groups:
			traversed_groups = set()
		license_group = self._license_groups.get(group_name)
		if group_name in traversed_groups:
			writemsg(("Circular license group reference" + \
				" detected in '%s'\n") % group_name, noiselevel=-1)
			rValue.append("@"+group_name)
		elif license_group:
			traversed_groups.add(group_name)
			for l in license_group:
				if l.startswith("-"):
					writemsg(("Skipping invalid element %s" + \
						" in license group '%s'\n") % (l, group_name),
						noiselevel=-1)
				else:
					rValue.extend(self._expandLicenseToken(l, traversed_groups))
		else:
			writemsg("Undefined license group '%s'\n" % group_name,
				noiselevel=-1)
			rValue.append("@"+group_name)
		if negate:
			rValue = ["-" + token for token in rValue]
		return rValue

	def validate(self):
		"""Validate miscellaneous settings and display warnings if necessary.
		(This code was previously in the global scope of portage.py)"""

		groups = self["ACCEPT_KEYWORDS"].split()
		archlist = self.archlist()
		if not archlist:
			writemsg("--- 'profiles/arch.list' is empty or " + \
				"not available. Empty portage tree?\n", noiselevel=1)
		else:
			for group in groups:
				if group not in archlist and \
					not (group.startswith("-") and group[1:] in archlist) and \
					group not in ("*", "~*", "**"):
					writemsg("!!! INVALID ACCEPT_KEYWORDS: %s\n" % str(group),
						noiselevel=-1)

		abs_profile_path = os.path.join(self["PORTAGE_CONFIGROOT"],
			PROFILE_PATH.lstrip(os.path.sep))
		if not self.profile_path or (not os.path.islink(abs_profile_path) and \
			not os.path.exists(os.path.join(abs_profile_path, "parent")) and \
			os.path.exists(os.path.join(self["PORTDIR"], "profiles"))):
			writemsg("\a\n\n!!! %s is not a symlink and will probably prevent most merges.\n" % abs_profile_path,
				noiselevel=-1)
			writemsg("!!! It should point into a profile within %s/profiles/\n" % self["PORTDIR"])
			writemsg("!!! (You can safely ignore this message when syncing. It's harmless.)\n\n\n")

		abs_user_virtuals = os.path.join(self["PORTAGE_CONFIGROOT"],
			USER_VIRTUALS_FILE.lstrip(os.path.sep))
		if os.path.exists(abs_user_virtuals):
			writemsg("\n!!! /etc/portage/virtuals is deprecated in favor of\n")
			writemsg("!!! /etc/portage/profile/virtuals. Please move it to\n")
			writemsg("!!! this new location.\n\n")

	def loadVirtuals(self,root):
		"""Not currently used by portage."""
		writemsg("DEPRECATED: portage.config.loadVirtuals\n")
		self.getvirtuals(root)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		mod = None
		try:
			mod = load_mod(best_mod)
		except ImportError:
			if best_mod.startswith("cache."):
				best_mod = "portage." + best_mod
				try:
					mod = load_mod(best_mod)
				except ImportError:
					pass
		if mod is None:
			raise
		return mod

	def lock(self):
		self.locked = 1

	def unlock(self):
		self.locked = 0

	def modifying(self):
		if self.locked:
			raise Exception, "Configuration is locked."

	def backup_changes(self,key=None):
		self.modifying()
		if key and self.configdict["env"].has_key(key):
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError, "No such key defined in environment: %s" % key

	def reset(self,keeping_pkg=0,use_cache=1):
		"""
		Restore environment from self.backupenv, call self.regenerate()
		@param keeping_pkg: Should we keep the set_cpv() data or delete it.
		@type keeping_pkg: Boolean
		@param use_cache: Should self.regenerate use the cache or not
		@type use_cache: Boolean
		@rype: None
		"""
		self.modifying()
		self.configdict["env"].clear()
		self.configdict["env"].update(self.backupenv)

		self.modifiedkeys = []
		if not keeping_pkg:
			self.mycpv = None
			self.puse = ""
			self.configdict["pkg"].clear()
			self.configdict["pkginternal"].clear()
			self.configdict["defaults"]["USE"] = \
				" ".join(self.make_defaults_use)
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))
		self.regenerate(use_cache=use_cache)

	def load_infodir(self,infodir):
		self.modifying()
		backup_pkg_metadata = dict(self.configdict["pkg"].iteritems())
		if "pkg" in self.configdict and \
			"CATEGORY" in self.configdict["pkg"]:
			self.configdict["pkg"].clear()
			self.configdict["pkg"]["CATEGORY"] = \
				backup_pkg_metadata["CATEGORY"]
		else:
			raise portage.exception.PortageException(
				"No pkg setup for settings instance?")

		retval = 0
		found_category_file = False
		if os.path.isdir(infodir):
			if os.path.exists(infodir+"/environment"):
				self.configdict["pkg"]["PORT_ENV_FILE"] = infodir+"/environment"

			myre = re.compile('^[A-Z]+$')
			null_byte = "\0"
			for filename in listdir(infodir,filesonly=1,EmptyOnError=1):
				if filename == "FEATURES":
					# FEATURES from the build host shouldn't be interpreted as
					# FEATURES on the client system.
					continue
				if filename == "CATEGORY":
					found_category_file = True
					continue
				if myre.match(filename):
					try:
						file_path = os.path.join(infodir, filename)
						mydata = open(file_path).read().strip()
						if len(mydata) < 2048 or filename == "USE":
							if null_byte in mydata:
								writemsg("!!! Null byte found in metadata " + \
									"file: '%s'\n" % file_path, noiselevel=-1)
								continue
							if filename == "USE":
								binpkg_flags = "-* " + mydata
								self.configdict["pkg"][filename] = binpkg_flags
								self.configdict["env"][filename] = mydata
							else:
								self.configdict["pkg"][filename] = mydata
								self.configdict["env"][filename] = mydata
					except (OSError, IOError):
						writemsg("!!! Unable to read file: %s\n" % infodir+"/"+filename,
							noiselevel=-1)
						pass
			retval = 1

		# Missing or corrupt CATEGORY will cause problems for
		# doebuild(), which uses it to infer the cpv. We already
		# know the category, so there's no need to trust this
		# file. Show a warning if the file is missing though,
		# because it's required (especially for binary packages).
		if not found_category_file:
			writemsg("!!! CATEGORY file is missing: %s\n" % \
				os.path.join(infodir, "CATEGORY"), noiselevel=-1)
			self.configdict["pkg"].update(backup_pkg_metadata)
			retval = 0
		return retval

	def setcpv(self, mycpv, use_cache=1, mydb=None):
		"""
		Load a particular CPV into the config, this lets us see the
		Default USE flags for a particular ebuild as well as the USE
		flags from package.use.

		@param mycpv: A cpv to load
		@type mycpv: string
		@param use_cache: Enables caching
		@type use_cache: Boolean
		@param mydb: a dbapi instance that supports aux_get with the IUSE key.
		@type mydb: dbapi or derivative.
		@rtype: None
		"""

		self.modifying()
		if self.mycpv == mycpv:
			return
		ebuild_phase = self.get("EBUILD_PHASE")
		has_changed = False
		self.mycpv = mycpv
		cp = dep_getkey(mycpv)
		cpv_slot = self.mycpv
		pkginternaluse = ""
		iuse = ""
		if mydb:
			if isinstance(mydb, dict):
				slot = mydb["SLOT"]
				iuse = mydb["IUSE"]
			else:
				slot, iuse = mydb.aux_get(self.mycpv, ["SLOT", "IUSE"])
			cpv_slot = "%s:%s" % (self.mycpv, slot)
			pkginternaluse = []
			for x in iuse.split():
				if x.startswith("+"):
					pkginternaluse.append(x[1:])
				elif x.startswith("-"):
					pkginternaluse.append(x)
			pkginternaluse = " ".join(pkginternaluse)
		if pkginternaluse != self.configdict["pkginternal"].get("USE", ""):
			self.configdict["pkginternal"]["USE"] = pkginternaluse
			has_changed = True
		defaults = []
		pos = 0
		for i in xrange(len(self.profiles)):
			cpdict = self.pkgprofileuse[i].get(cp, None)
			if cpdict:
				keys = cpdict.keys()
				while keys:
					bestmatch = best_match_to_list(cpv_slot, keys)
					if bestmatch:
						keys.remove(bestmatch)
						defaults.insert(pos, cpdict[bestmatch])
					else:
						break
				del keys
			if self.make_defaults_use[i]:
				defaults.insert(pos, self.make_defaults_use[i])
			pos = len(defaults)
		defaults = " ".join(defaults)
		if defaults != self.configdict["defaults"].get("USE",""):
			self.configdict["defaults"]["USE"] = defaults
			has_changed = True
		useforce = []
		pos = 0
		for i in xrange(len(self.profiles)):
			cpdict = self.puseforce_list[i].get(cp, None)
			if cpdict:
				keys = cpdict.keys()
				while keys:
					best_match = best_match_to_list(cpv_slot, keys)
					if best_match:
						keys.remove(best_match)
						useforce.insert(pos, cpdict[best_match])
					else:
						break
				del keys
			if self.useforce_list[i]:
				useforce.insert(pos, self.useforce_list[i])
			pos = len(useforce)
		useforce = set(stack_lists(useforce, incremental=True))
		if useforce != self.useforce:
			self.useforce = useforce
			has_changed = True
		usemask = []
		pos = 0
		for i in xrange(len(self.profiles)):
			cpdict = self.pusemask_list[i].get(cp, None)
			if cpdict:
				keys = cpdict.keys()
				while keys:
					best_match = best_match_to_list(cpv_slot, keys)
					if best_match:
						keys.remove(best_match)
						usemask.insert(pos, cpdict[best_match])
					else:
						break
				del keys
			if self.usemask_list[i]:
				usemask.insert(pos, self.usemask_list[i])
			pos = len(usemask)
		usemask = set(stack_lists(usemask, incremental=True))
		if usemask != self.usemask:
			self.usemask = usemask
			has_changed = True
		oldpuse = self.puse
		self.puse = ""
		cpdict = self.pusedict.get(cp)
		if cpdict:
			keys = cpdict.keys()
			while keys:
				self.pusekey = best_match_to_list(cpv_slot, keys)
				if self.pusekey:
					keys.remove(self.pusekey)
					self.puse = (" ".join(cpdict[self.pusekey])) + " " + self.puse
				else:
					break
			del keys
		if oldpuse != self.puse:
			has_changed = True
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE
		if iuse != self.configdict["pkg"].get("IUSE",""):
			self.configdict["pkg"]["IUSE"] = iuse
			test_use_changed = False
			if "test" in self.features:
				test_use_changed = \
					bool(re.search(r'(^|\s)[-+]?test(\s|$)', iuse)) != \
					("test" in self["USE"].split())
			if self.get("EBUILD_PHASE") or \
				self._use_wildcards or \
				test_use_changed:
				# Without this conditional, regenerate() would be called
				# *every* time.
				has_changed = True
		# CATEGORY is essential for doebuild calls
		self.configdict["pkg"]["CATEGORY"] = mycpv.split("/")[0]
		if has_changed:
			self.reset(keeping_pkg=1,use_cache=use_cache)

		# Filter out USE flags that aren't part of IUSE. This has to
		# be done for every setcpv() call since practically every
		# package has different IUSE. Some flags are considered to
		# be implicit members of IUSE:
		#
		#  * Flags derived from ARCH
		#  * Flags derived from USE_EXPAND_HIDDEN variables
		#  * Masked flags, such as those from {,package}use.mask
		#  * Forced flags, such as those from {,package}use.force
		#  * build and bootstrap flags used by bootstrap.sh

		usesplit = self["USE"].split()
		iuse_implicit = set(x.lstrip("+-") for x in iuse.split())

		# Flags derived from ARCH.
		arch = self.configdict["defaults"].get("ARCH")
		if arch:
			iuse_implicit.add(arch)
		iuse_implicit.update(self.get("PORTAGE_ARCHLIST", "").split())

		# Flags derived from USE_EXPAND_HIDDEN variables
		# such as ELIBC, KERNEL, and USERLAND.
		use_expand_hidden = self.get("USE_EXPAND_HIDDEN", "").split()
		use_expand_hidden_raw = use_expand_hidden
		if use_expand_hidden:
			use_expand_hidden = re.compile("^(%s)_.*" % \
				("|".join(x.lower() for x in use_expand_hidden)))
			for x in usesplit:
				if use_expand_hidden.match(x):
					iuse_implicit.add(x)

		# Flags that have been masked or forced.
		iuse_implicit.update(self.usemask)
		iuse_implicit.update(self.useforce)

		# build and bootstrap flags used by bootstrap.sh
		iuse_implicit.add("build")
		iuse_implicit.add("bootstrap")

		if ebuild_phase:
			iuse_grep = iuse_implicit.copy()
			if use_expand_hidden_raw:
				for x in use_expand_hidden_raw:
					iuse_grep.add(x.lower() + "_.*")
			if iuse_grep:
				iuse_grep = "^(%s)$" % "|".join(sorted(iuse_grep))
			else:
				iuse_grep = ""
			self.configdict["pkg"]["PORTAGE_IUSE"] = iuse_grep

		# Filtered for the ebuild environment. Store this in a separate
		# attribute since we still want to be able to see global USE
		# settings for things like emerge --info.
		self.configdict["pkg"]["PORTAGE_USE"] = " ".join(sorted(
			x for x in usesplit if \
			x in iuse_implicit))

	def getMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask. PROVIDE
		is not checked, so atoms will not be found for old-style virtuals.

		@param cpv: The package name
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: String
		@return: An matching atom string or None if one is not found.
		"""

		cp = cpv_getkey(cpv)
		mask_atoms = self.pmaskdict.get(cp)
		if mask_atoms:
			pkg_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			unmask_atoms = self.punmaskdict.get(cp)
			for x in mask_atoms:
				if not match_from_list(x, pkg_list):
					continue
				if unmask_atoms:
					for y in unmask_atoms:
						if match_from_list(y, pkg_list):
							return None
				return x
		return None

	def getProfileMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching profile atom, or None if no
		such atom exists. Note that a profile atom may or may not have a "*"
		prefix. PROVIDE is not checked, so atoms will not be found for
		old-style virtuals.

		@param cpv: The package name
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: String
		@return: An matching profile atom string or None if one is not found.
		"""

		cp = cpv_getkey(cpv)
		profile_atoms = self.prevmaskdict.get(cp)
		if profile_atoms:
			pkg_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			for x in profile_atoms:
				if match_from_list(x.lstrip("*"), pkg_list):
					continue
				return x
		return None

	def getMissingKeywords(self, cpv, metadata):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		may need to accept for the given package. If the KEYWORDS are empty
		and the the ** keyword has not been accepted, the returned list will
		contain ** alone (in order to distiguish from the case of "none
		missing").

		@param cpv: The package name (for package.keywords support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of KEYWORDS that have not been accepted.
		"""

		# Hack: Need to check the env directly here as otherwise stacking 
		# doesn't work properly as negative values are lost in the config
		# object (bug #139600)
		egroups = self.configdict["backupenv"].get(
			"ACCEPT_KEYWORDS", "").split()
		mygroups = metadata["KEYWORDS"].split()
		# Repoman may modify this attribute as necessary.
		pgroups = self["ACCEPT_KEYWORDS"].split()
		match=0
		cp = dep_getkey(cpv)
		pkgdict = self.pkeywordsdict.get(cp)
		matches = False
		if pkgdict:
			cpv_slot_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			for atom, pkgkeywords in pkgdict.iteritems():
				if match_from_list(atom, cpv_slot_list):
					matches = True
					pgroups.extend(pkgkeywords)
		if matches or egroups:
			pgroups.extend(egroups)
			inc_pgroups = set()
			for x in pgroups:
				if x.startswith("-"):
					if x == "-*":
						inc_pgroups.clear()
					else:
						inc_pgroups.discard(x[1:])
				else:
					inc_pgroups.add(x)
			pgroups = inc_pgroups
			del inc_pgroups
		hasstable = False
		hastesting = False
		for gp in mygroups:
			if gp == "*" or (gp == "-*" and len(mygroups) == 1):
				writemsg(("--- WARNING: Package '%s' uses" + \
					" '%s' keyword.\n") % (cpv, gp), noiselevel=-1)
				if gp == "*":
					match = 1
					break
			elif gp in pgroups:
				match=1
				break
			elif gp.startswith("~"):
				hastesting = True
			elif not gp.startswith("-"):
				hasstable = True
		if not match and \
			((hastesting and "~*" in pgroups) or \
			(hasstable and "*" in pgroups) or "**" in pgroups):
			match=1
		if match:
			missing = []
		else:
			if not mygroups:
				# If KEYWORDS is empty then we still have to return something
				# in order to distiguish from the case of "none missing".
				mygroups.append("**")
			missing = mygroups
		return missing

	def getMissingLicenses(self, cpv, metadata):
		"""
		Take a LICENSE string and return a list any licenses that the user may
		may need to accept for the given package.  The returned list will not
		contain any licenses that have already been accepted.  This method
		can throw an InvalidDependString exception.

		@param cpv: The package name (for package.license support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of licenses that have not been accepted.
		"""
		if "*" in self._accept_license:
			return []
		acceptable_licenses = self._accept_license
		cpdict = self._plicensedict.get(dep_getkey(cpv), None)
		if cpdict:
			acceptable_licenses = self._accept_license.copy()
			cpv_slot = "%s:%s" % (cpv, metadata["SLOT"])
			for atom in match_to_list(cpv_slot, cpdict.keys()):
				acceptable_licenses.update(cpdict[atom])
		license_struct = portage.dep.paren_reduce(metadata["LICENSE"])
		license_struct = portage.dep.use_reduce(
			license_struct, uselist=metadata["USE"].split())
		license_struct = portage.dep.dep_opconvert(license_struct)
		return self._getMissingLicenses(license_struct, acceptable_licenses)

	def _getMissingLicenses(self, license_struct, acceptable_licenses):
		if not license_struct:
			return []
		if license_struct[0] == "||":
			ret = []
			for element in license_struct[1:]:
				if isinstance(element, list):
					if element:
						ret.append(self._getMissingLicenses(
							element, acceptable_licenses))
						if not ret[-1]:
							return []
				else:
					if element in acceptable_licenses:
						return []
					ret.append(element)
			# Return all masked licenses, since we don't know which combination
			# (if any) the user will decide to unmask.
			return flatten(ret)

		ret = []
		for element in license_struct:
			if isinstance(element, list):
				if element:
					ret.extend(self._getMissingLicenses(element,
						acceptable_licenses))
			else:
				if element not in acceptable_licenses:
					ret.append(element)
		return ret

	def setinst(self,mycpv,mydbapi):
		"""This updates the preferences for old-style virtuals,
		affecting the behavior of dep_expand() and dep_check()
		calls. It can change dbapi.match() behavior since that
		calls dep_expand(). However, dbapi instances have
		internal match caches that are not invalidated when
		preferences are updated here. This can potentially
		lead to some inconsistency (relevant to bug #1343)."""
		self.modifying()
		if len(self.virtuals) == 0:
			self.getvirtuals()
		# Grab the virtuals this package provides and add them into the tree virtuals.
		if isinstance(mydbapi, dict):
			provides = mydbapi["PROVIDE"]
		else:
			provides = mydbapi.aux_get(mycpv, ["PROVIDE"])[0]
		if not provides:
			return
		if isinstance(mydbapi, portdbapi):
			self.setcpv(mycpv, mydb=mydbapi)
			myuse = self["PORTAGE_USE"]
		elif isinstance(mydbapi, dict):
			myuse = mydbapi["USE"]
		else:
			myuse = mydbapi.aux_get(mycpv, ["USE"])[0]
		virts = flatten(portage.dep.use_reduce(portage.dep.paren_reduce(provides), uselist=myuse.split()))

		modified = False
		cp = dep_getkey(mycpv)
		for virt in virts:
			virt = dep_getkey(virt)
			providers = self.virtuals.get(virt)
			if providers and cp in providers:
				continue
			providers = self._depgraphVirtuals.get(virt)
			if providers is None:
				providers = []
				self._depgraphVirtuals[virt] = providers
			if cp not in providers:
				providers.append(cp)
				modified = True

		if modified:
			self.virtuals = self.__getvirtuals_compile()

	def reload(self):
		"""Reload things like /etc/profile.env that can change during runtime."""
		env_d_filename = os.path.join(self["ROOT"], "etc", "profile.env")
		self.configdict["env.d"].clear()
		env_d = getconfig(env_d_filename, expand=False)
		if env_d:
			# env_d will be None if profile.env doesn't exist.
			self.configdict["env.d"].update(env_d)

	def regenerate(self,useonly=0,use_cache=1):
		"""
		Regenerate settings
		This involves regenerating valid USE flags, re-expanding USE_EXPAND flags
		re-stacking USE flags (-flag and -*), as well as any other INCREMENTAL
		variables.  This also updates the env.d configdict; useful in case an ebuild
		changes the environment.

		If FEATURES has already stacked, it is not stacked twice.

		@param useonly: Only regenerate USE flags (not any other incrementals)
		@type useonly: Boolean
		@param use_cache: Enable Caching (only for autouse)
		@type use_cache: Boolean
		@rtype: None
		"""

		self.modifying()
		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals = self.incrementals
		myincrementals = set(myincrementals)
		# If self.features exists, it has already been stacked and may have
		# been mutated, so don't stack it again or else any mutations will be
		# reverted.
		if "FEATURES" in myincrementals and hasattr(self, "features"):
			myincrementals.remove("FEATURES")

		if "USE" in myincrementals:
			# Process USE last because it depends on USE_EXPAND which is also
			# an incremental!
			myincrementals.remove("USE")

		for mykey in myincrementals:

			mydbs=self.configlist[:-1]

			myflags=[]
			for curdb in mydbs:
				if mykey not in curdb:
					continue
				#variables are already expanded
				mysplit = curdb[mykey].split()

				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags = []
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(red("USE flags should not start with a '+': %s\n" % x),
							noiselevel=-1)
						x=x[1:]
						if not x:
							continue

					if (x[0]=="-"):
						if (x[1:] in myflags):
							# Unset/Remove it.
							del myflags[myflags.index(x[1:])]
						continue

					# We got here, so add it now.
					if x not in myflags:
						myflags.append(x)

			myflags.sort()
			#store setting in last element of configlist, the original environment:
			if myflags or mykey in self:
				self.configlist[-1][mykey] = " ".join(myflags)
			del myflags

		# Do the USE calculation last because it depends on USE_EXPAND.
		if "auto" in self["USE_ORDER"].split(":"):
			self.configdict["auto"]["USE"] = autouse(
				vartree(root=self["ROOT"], categories=self.categories,
					settings=self),
				use_cache=use_cache, mysettings=self)
		else:
			self.configdict["auto"]["USE"] = ""

		use_expand = self.get("USE_EXPAND", "").split()

		if not self.uvlist:
			for x in self["USE_ORDER"].split(":"):
				if x in self.configdict:
					self.uvlist.append(self.configdict[x])
			self.uvlist.reverse()

		myflags = set()
		for curdb in self.uvlist:
			cur_use_expand = [x for x in use_expand if x in curdb]
			mysplit = curdb.get("USE", "").split()
			if not mysplit and not cur_use_expand:
				continue
			for x in mysplit:
				if x == "-*":
					myflags.clear()
					continue

				if x[0] == "+":
					writemsg(colorize("BAD", "USE flags should not start " + \
						"with a '+': %s\n" % x), noiselevel=-1)
					x = x[1:]
					if not x:
						continue

				if x[0] == "-":
					myflags.discard(x[1:])
					continue

				myflags.add(x)

			for var in cur_use_expand:
				var_lower = var.lower()
				is_not_incremental = var not in myincrementals
				if is_not_incremental:
					prefix = var_lower + "_"
					for x in list(myflags):
						if x.startswith(prefix):
							myflags.remove(x)
				for x in curdb[var].split():
					if x[0] == "+":
						if is_not_incremental:
							writemsg(colorize("BAD", "Invalid '+' " + \
								"operator in non-incremental variable " + \
								 "'%s': '%s'\n" % (var, x)), noiselevel=-1)
							continue
						else:
							writemsg(colorize("BAD", "Invalid '+' " + \
								"operator in incremental variable " + \
								 "'%s': '%s'\n" % (var, x)), noiselevel=-1)
						x = x[1:]
					if x[0] == "-":
						if is_not_incremental:
							writemsg(colorize("BAD", "Invalid '-' " + \
								"operator in non-incremental variable " + \
								 "'%s': '%s'\n" % (var, x)), noiselevel=-1)
							continue
						myflags.discard(var_lower + "_" + x[1:])
						continue
					myflags.add(var_lower + "_" + x)

		myflags.update(self.useforce)

		iuse = self.configdict["pkg"].get("IUSE","").split()
		iuse = [ x.lstrip("+-") for x in iuse ]
		# FEATURES=test should imply USE=test
		if not hasattr(self, "features"):
			self.features = list(sorted(set(
				self.configlist[-1].get("FEATURES","").split())))
		self["FEATURES"] = " ".join(self.features)
		ebuild_force_test = self.get("EBUILD_FORCE_TEST") == "1"
		if ebuild_force_test and \
			self.get("EBUILD_PHASE") == "test" and \
			not hasattr(self, "_ebuild_force_test_msg_shown"):
				self._ebuild_force_test_msg_shown = True
				writemsg("Forcing test.\n", noiselevel=-1)
		if "test" in self.features and "test" in iuse:
			if "test" in self.usemask and not ebuild_force_test:
				# "test" is in IUSE and USE=test is masked, so execution
				# of src_test() probably is not reliable. Therefore,
				# temporarily disable FEATURES=test just for this package.
				self["FEATURES"] = " ".join(x for x in self.features \
					if x != "test")
				myflags.discard("test")
			else:
				myflags.add("test")
				if ebuild_force_test:
					self.usemask.discard("test")

		usesplit = [ x for x in myflags if \
			x not in self.usemask]

		# Use the calculated USE flags to regenerate the USE_EXPAND flags so
		# that they are consistent.
		for var in use_expand:
			prefix = var.lower() + "_"
			prefix_len = len(prefix)
			expand_flags = set([ x[prefix_len:] for x in usesplit \
				if x.startswith(prefix) ])
			var_split = self.get(var, "").split()
			# Preserve the order of var_split because it can matter for things
			# like LINGUAS.
			var_split = [ x for x in var_split if x in expand_flags ]
			var_split.extend(expand_flags.difference(var_split))
			has_wildcard = "*" in var_split
			if has_wildcard:
				var_split = [ x for x in var_split if x != "*" ]
				self._use_wildcards = True
			has_iuse = False
			for x in iuse:
				if x.startswith(prefix):
					has_iuse = True
					break
			if has_wildcard:
				# * means to enable everything in IUSE that's not masked
				if has_iuse:
					for x in iuse:
						if x.startswith(prefix) and x not in self.usemask:
							suffix = x[prefix_len:]
							if suffix in var_split:
								continue
							var_split.append(suffix)
							usesplit.append(x)
				else:
					# If there is a wildcard and no matching flags in IUSE then
					# LINGUAS should be unset so that all .mo files are
					# installed.
					var_split = []
			if var_split:
				self[var] = " ".join(var_split)
			else:
				# Don't export empty USE_EXPAND vars unless the user config
				# exports them as empty.  This is required for vars such as
				# LINGUAS, where unset and empty have different meanings.
				if has_wildcard:
					# ebuild.sh will see this and unset the variable so
					# that things like LINGUAS work properly
					self[var] = "*"
				else:
					if has_iuse:
						self[var] = ""
					else:
						# It's not in IUSE, so just allow the variable content
						# to pass through if it is defined somewhere.  This
						# allows packages that support LINGUAS but don't
						# declare it in IUSE to use the variable outside of the
						# USE_EXPAND context.
						pass

		arch = self.configdict["defaults"].get("ARCH")
		if arch and arch not in usesplit:
			usesplit.append(arch)

		usesplit = [x for x in usesplit if \
			x not in self.usemask]

		usesplit.sort()
		self.configlist[-1]["USE"]= " ".join(usesplit)

		self.already_in_regenerate = 0

	def get_virts_p(self, myroot):
		if self.virts_p:
			return self.virts_p
		virts = self.getvirtuals(myroot)
		if virts:
			for x in virts:
				vkeysplit = x.split("/")
				if not self.virts_p.has_key(vkeysplit[1]):
					self.virts_p[vkeysplit[1]] = virts[x]
		return self.virts_p

	def getvirtuals(self, myroot=None):
		"""myroot is now ignored because, due to caching, it has always been
		broken for all but the first call."""
		myroot = self["ROOT"]
		if self.virtuals:
			return self.virtuals

		virtuals_list = []
		for x in self.profiles:
			virtuals_file = os.path.join(x, "virtuals")
			virtuals_dict = grabdict(virtuals_file)
			for k in virtuals_dict.keys():
				if not isvalidatom(k) or dep_getkey(k) != k:
					writemsg("--- Invalid virtuals atom in %s: %s\n" % \
						(virtuals_file, k), noiselevel=-1)
					del virtuals_dict[k]
					continue
				myvalues = virtuals_dict[k]
				for x in myvalues:
					myatom = x
					if x.startswith("-"):
						# allow incrementals
						myatom = x[1:]
					if not isvalidatom(myatom):
						writemsg("--- Invalid atom in %s: %s\n" % \
							(virtuals_file, x), noiselevel=-1)
						myvalues.remove(x)
				if not myvalues:
					del virtuals_dict[k]
			if virtuals_dict:
				virtuals_list.append(virtuals_dict)

		self.dirVirtuals = stack_dictlist(virtuals_list, incremental=True)
		del virtuals_list

		for virt in self.dirVirtuals:
			# Preference for virtuals decreases from left to right.
			self.dirVirtuals[virt].reverse()

		# Repoman does not use user or tree virtuals.
		if self.local_config and not self.treeVirtuals:
			temp_vartree = vartree(myroot, None,
				categories=self.categories, settings=self)
			# Reduce the provides into a list by CP.
			self.treeVirtuals = map_dictlist_vals(getCPFromCPV,temp_vartree.get_all_provides())

		self.virtuals = self.__getvirtuals_compile()
		return self.virtuals

	def __getvirtuals_compile(self):
		"""Stack installed and profile virtuals.  Preference for virtuals
		decreases from left to right.
		Order of preference:
		1. installed and in profile
		2. installed only
		3. profile only
		"""

		# Virtuals by profile+tree preferences.
		ptVirtuals   = {}

		for virt, installed_list in self.treeVirtuals.iteritems():
			profile_list = self.dirVirtuals.get(virt, None)
			if not profile_list:
				continue
			for cp in installed_list:
				if cp in profile_list:
					ptVirtuals.setdefault(virt, [])
					ptVirtuals[virt].append(cp)

		virtuals = stack_dictlist([ptVirtuals, self.treeVirtuals,
			self.dirVirtuals, self._depgraphVirtuals])
		return virtuals

	def __delitem__(self,mykey):
		self.modifying()
		for x in self.lookuplist:
			if x != None:
				if mykey in x:
					del x[mykey]

	def __getitem__(self,mykey):
		for d in self.lookuplist:
			if mykey in d:
				return d[mykey]
		return '' # for backward compat, don't raise KeyError

	def get(self, k, x=None):
		for d in self.lookuplist:
			if k in d:
				return d[k]
		return x

	def pop(self, key, *args):
		if len(args) > 1:
			raise TypeError(
				"pop expected at most 2 arguments, got " + \
				repr(1 + len(args)))
		v = self
		for d in reversed(self.lookuplist):
			v = d.pop(key, v)
		if v is self:
			if args:
				return args[0]
			raise KeyError(key)
		return v

	def has_key(self,mykey):
		return mykey in self

	def __contains__(self, mykey):
		"""Called to implement membership test operators (in and not in)."""
		for d in self.lookuplist:
			if mykey in d:
				return True
		return False

	def setdefault(self, k, x=None):
		v = self.get(k)
		if v is not None:
			return v
		else:
			self[k] = x
			return x

	def keys(self):
		return list(self)

	def __iter__(self):
		keys = set()
		for d in self.lookuplist:
			keys.update(d)
		return iter(keys)

	def iterkeys(self):
		return iter(self)

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		if not isinstance(myvalue, str):
			raise ValueError("Invalid type being used as a value: '%s': '%s'" % (str(mykey),str(myvalue)))
		self.modifying()
		self.modifiedkeys += [mykey]
		self.configdict["env"][mykey]=myvalue

	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		environ_filter = self._environ_filter
		filter_calling_env = self._filter_calling_env
		environ_whitelist = self._environ_whitelist
		env_d = self.configdict["env.d"]
		for x in self:
			if x in environ_filter:
				continue
			myvalue = self[x]
			if not isinstance(myvalue, basestring):
				writemsg("!!! Non-string value in config: %s=%s\n" % \
					(x, myvalue), noiselevel=-1)
				continue
			if filter_calling_env and \
				x not in environ_whitelist and \
				not self._environ_whitelist_re.match(x):
				# Do not allow anything to leak into the ebuild
				# environment unless it is explicitly whitelisted.
				# This ensures that variables unset by the ebuild
				# remain unset.
				continue
			mydict[x] = myvalue
		if not mydict.has_key("HOME") and mydict.has_key("BUILD_PREFIX"):
			writemsg("*** HOME not set. Setting to "+mydict["BUILD_PREFIX"]+"\n")
			mydict["HOME"]=mydict["BUILD_PREFIX"][:]

		if filter_calling_env:
			phase = self.get("EBUILD_PHASE")
			if phase:
				whitelist = []
				if "rpm" == phase:
					whitelist.append("RPMDIR")
				for k in whitelist:
					v = self.get(k)
					if v is not None:
						mydict[k] = v

		# Filtered by IUSE and implicit IUSE.
		mydict["USE"] = self.get("PORTAGE_USE", "")

		# sandbox's bashrc sources /etc/profile which unsets ROOTPATH,
		# so we have to back it up and restore it.
		rootpath = mydict.get("ROOTPATH")
		if rootpath:
			mydict["PORTAGE_ROOTPATH"] = rootpath

		return mydict

	def thirdpartymirrors(self):
		if getattr(self, "_thirdpartymirrors", None) is None:
			profileroots = [os.path.join(self["PORTDIR"], "profiles")]
			for x in self["PORTDIR_OVERLAY"].split():
				profileroots.insert(0, os.path.join(x, "profiles"))
			thirdparty_lists = [grabdict(os.path.join(x, "thirdpartymirrors")) for x in profileroots]
			self._thirdpartymirrors = stack_dictlist(thirdparty_lists, incremental=True)
		return self._thirdpartymirrors

	def archlist(self):
		return flatten([[myarch, "~" + myarch] \
			for myarch in self["PORTAGE_ARCHLIST"].split()])

	def selinux_enabled(self):
		if getattr(self, "_selinux_enabled", None) is None:
			self._selinux_enabled = 0
			if "selinux" in self["USE"].split():
				if "selinux" in globals():
					if selinux.is_selinux_enabled() == 1:
						self._selinux_enabled = 1
					else:
						self._selinux_enabled = 0
				else:
					writemsg("!!! SELinux module not found. Please verify that it was installed.\n",
						noiselevel=-1)
					self._selinux_enabled = 0
			if self._selinux_enabled == 0:
				try:	
					del sys.modules["selinux"]
				except KeyError:
					pass
		return self._selinux_enabled

def _shell_quote(s):
	"""
	Quote a string in double-quotes and use backslashes to
	escape any backslashes, double-quotes, dollar signs, or
	backquotes in the string.
	"""
	for letter in "\\\"$`":
		if letter in s:
			s = s.replace(letter, "\\" + letter)
	return "\"%s\"" % s

# In some cases, openpty can be slow when it fails. Therefore,
# stop trying to use it after the first failure.
_disable_openpty = False

# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring, mysettings, debug=0, free=0, droppriv=0, sesandbox=0, fakeroot=0, **keywords):
	"""
	Spawn a subprocess with extra portage-specific options.
	Optiosn include:

	Sandbox: Sandbox means the spawned process will be limited in its ability t
	read and write files (normally this means it is restricted to ${IMAGE}/)
	SElinux Sandbox: Enables sandboxing on SElinux
	Reduced Privileges: Drops privilages such that the process runs as portage:portage
	instead of as root.

	Notes: os.system cannot be used because it messes with signal handling.  Instead we
	use the portage.process spawn* family of functions.

	This function waits for the process to terminate.

	@param mystring: Command to run
	@type mystring: String
	@param mysettings: Either a Dict of Key,Value pairs or an instance of portage.config
	@type mysettings: Dictionary or config instance
	@param debug: Ignored
	@type debug: Boolean
	@param free: Enable sandboxing for this process
	@type free: Boolean
	@param droppriv: Drop to portage:portage when running this command
	@type droppriv: Boolean
	@param sesandbox: Enable SELinux Sandboxing (toggles a context switch)
	@type sesandbox: Boolean
	@param fakeroot: Run this command with faked root privileges
	@type fakeroot: Boolean
	@param keywords: Extra options encoded as a dict, to be passed to spawn
	@type keywords: Dictionary
	@rtype: Integer
	@returns:
	1. The return code of the spawned process.
	"""

	if isinstance(mysettings, dict):
		env=mysettings
		keywords["opt_name"]="[ %s ]" % "portage"
	else:
		check_config_instance(mysettings)
		env=mysettings.environ()
		keywords["opt_name"]="[%s]" % mysettings["PF"]

	fd_pipes = keywords.get("fd_pipes")
	if fd_pipes is None:
		fd_pipes = {
			0:sys.stdin.fileno(),
			1:sys.stdout.fileno(),
			2:sys.stderr.fileno(),
		}
	# In some cases the above print statements don't flush stdout, so
	# it needs to be flushed before allowing a child process to use it
	# so that output always shows in the correct order.
	for fd in fd_pipes.itervalues():
		if fd == sys.stdout.fileno():
			sys.stdout.flush()
		if fd == sys.stderr.fileno():
			sys.stderr.flush()

	# The default policy for the sesandbox domain only allows entry (via exec)
	# from shells and from binaries that belong to portage (the number of entry
	# points is minimized).  The "tee" binary is not among the allowed entry
	# points, so it is spawned outside of the sesandbox domain and reads from a
	# pseudo-terminal that connects two domains.
	logfile = keywords.get("logfile")
	mypids = []
	master_fd = None
	slave_fd = None
	fd_pipes_orig = None
	got_pty = False
	if logfile:
		del keywords["logfile"]
		if 1 not in fd_pipes or 2 not in fd_pipes:
			raise ValueError(fd_pipes)
		global _disable_openpty
		if _disable_openpty:
			master_fd, slave_fd = os.pipe()
		else:
			from pty import openpty
			try:
				master_fd, slave_fd = openpty()
				got_pty = True
			except EnvironmentError, e:
				_disable_openpty = True
				writemsg("openpty failed: '%s'\n" % str(e), noiselevel=1)
				del e
				master_fd, slave_fd = os.pipe()
		if got_pty:
			# Disable post-processing of output since otherwise weird
			# things like \n -> \r\n transformations may occur.
			import termios
			mode = termios.tcgetattr(slave_fd)
			mode[1] &= ~termios.OPOST
			termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

		# We must set non-blocking mode before we close the slave_fd
		# since otherwise the fcntl call can fail on FreeBSD (the child
		# process might have already exited and closed slave_fd so we
		# have to keep it open in order to avoid FreeBSD potentially
		# generating an EAGAIN exception).
		import fcntl
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes_orig = fd_pipes.copy()
		if got_pty and os.isatty(fd_pipes_orig[1]):
			from portage.output import get_term_size, set_term_size
			rows, columns = get_term_size()
			set_term_size(rows, columns, slave_fd)
		fd_pipes[0] = fd_pipes_orig[0]
		fd_pipes[1] = slave_fd
		fd_pipes[2] = slave_fd
		keywords["fd_pipes"] = fd_pipes

	features = mysettings.features
	# TODO: Enable fakeroot to be used together with droppriv.  The
	# fake ownership/permissions will have to be converted to real
	# permissions in the merge phase.
	fakeroot = fakeroot and uid != 0 and portage.process.fakeroot_capable
	if droppriv and not uid and portage_gid and portage_uid:
		keywords.update({"uid":portage_uid,"gid":portage_gid,
			"groups":userpriv_groups,"umask":002})
	if not free:
		free=((droppriv and "usersandbox" not in features) or \
			(not droppriv and "sandbox" not in features and \
			"usersandbox" not in features))

	if free or "SANDBOX_ACTIVE" in os.environ:
		keywords["opt_name"] += " bash"
		spawn_func = portage.process.spawn_bash
	elif fakeroot:
		keywords["opt_name"] += " fakeroot"
		keywords["fakeroot_state"] = os.path.join(mysettings["T"], "fakeroot.state")
		spawn_func = portage.process.spawn_fakeroot
	else:
		keywords["opt_name"] += " sandbox"
		spawn_func = portage.process.spawn_sandbox

	if sesandbox:
		con = selinux.getcontext()
		con = con.replace(mysettings["PORTAGE_T"],
			mysettings["PORTAGE_SANDBOX_T"])
		selinux.setexec(con)

	returnpid = keywords.get("returnpid")
	keywords["returnpid"] = True
	try:
		mypids.extend(spawn_func(mystring, env=env, **keywords))
	finally:
		if logfile:
			os.close(slave_fd)
		if sesandbox:
			selinux.setexec(None)

	if returnpid:
		return mypids

	if logfile:
		log_file = open(logfile, 'a')
		stdout_file = os.fdopen(os.dup(fd_pipes_orig[1]), 'w')
		master_file = os.fdopen(master_fd, 'r')
		iwtd = [master_file]
		owtd = []
		ewtd = []
		import array, select
		buffsize = 65536
		eof = False
		while not eof:
			events = select.select(iwtd, owtd, ewtd)
			for f in events[0]:
				# Use non-blocking mode to prevent read
				# calls from blocking indefinitely.
				buf = array.array('B')
				try:
					buf.fromfile(f, buffsize)
				except EOFError:
					pass
				if not buf:
					eof = True
					break
				if f is master_file:
					buf.tofile(stdout_file)
					stdout_file.flush()
					buf.tofile(log_file)
					log_file.flush()
		log_file.close()
		stdout_file.close()
		master_file.close()
	pid = mypids[-1]
	retval = os.waitpid(pid, 0)[1]
	portage.process.spawned_pids.remove(pid)
	if retval != os.EX_OK:
		if retval & 0xff:
			return (retval & 0xff) << 8
		return retval >> 8
	return retval

def _checksum_failure_temp_file(distdir, basename):
	"""
	First try to find a duplicate temp file with the same checksum and return
	that filename if available. Otherwise, use mkstemp to create a new unique
	filename._checksum_failure_.$RANDOM, rename the given file, and return the
	new filename. In any case, filename will be renamed or removed before this
	function returns a temp filename.
	"""

	filename = os.path.join(distdir, basename)
	size = os.stat(filename).st_size
	checksum = None
	tempfile_re = re.compile(re.escape(basename) + r'\._checksum_failure_\..*')
	for temp_filename in os.listdir(distdir):
		if not tempfile_re.match(temp_filename):
			continue
		temp_filename = os.path.join(distdir, temp_filename)
		try:
			if size != os.stat(temp_filename).st_size:
				continue
		except OSError:
			continue
		try:
			temp_checksum = portage.checksum.perform_md5(temp_filename)
		except portage.exception.FileNotFound:
			# Apparently the temp file disappeared. Let it go.
			continue
		if checksum is None:
			checksum = portage.checksum.perform_md5(filename)
		if checksum == temp_checksum:
			os.unlink(filename)
			return temp_filename

	from tempfile import mkstemp
	fd, temp_filename = mkstemp("", basename + "._checksum_failure_.", distdir)
	os.close(fd)
	os.rename(filename, temp_filename)
	return temp_filename

def fetch(myuris, mysettings, listonly=0, fetchonly=0, locks_in_subdir=".locks",use_locks=1, try_mirrors=1):
	"fetch files.  Will use digest file if available."

	features = mysettings.features
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()
	# 'nomirror' is bad/negative logic. You Restrict mirroring, not no-mirroring.
	if "mirror" in restrict or \
	   "nomirror" in restrict:
		if ("mirror" in features) and ("lmirror" not in features):
			# lmirror should allow you to bypass mirror restrictions.
			# XXX: This is not a good thing, and is temporary at best.
			print ">>> \"mirror\" mode desired and \"mirror\" restriction found; skipping fetch."
			return 1

	# Generally, downloading the same file repeatedly from
	# every single available mirror is a waste of bandwidth
	# and time, so there needs to be a cap.
	checksum_failure_max_tries = 5
	# Behave like the package has RESTRICT="primaryuri" after a
	# couple of checksum failures, to increase the probablility
	# of success before checksum_failure_max_tries is reached.
	checksum_failure_primaryuri = 2
	thirdpartymirrors = mysettings.thirdpartymirrors()

	check_config_instance(mysettings)

	custommirrors = grabdict(os.path.join(mysettings["PORTAGE_CONFIGROOT"],
		CUSTOM_MIRRORS_FILE.lstrip(os.path.sep)), recursive=1)

	mymirrors=[]

	if listonly or ("distlocks" not in features):
		use_locks = 0

	fetch_to_ro = 0
	if "skiprocheck" in features:
		fetch_to_ro = 1

	if not os.access(mysettings["DISTDIR"],os.W_OK) and fetch_to_ro:
		if use_locks:
			writemsg(red("!!! For fetching to a read-only filesystem, " + \
				"locking should be turned off.\n"), noiselevel=-1)
			writemsg("!!! This can be done by adding -distlocks to " + \
				"FEATURES in /etc/make.conf\n", noiselevel=-1)
#			use_locks = 0

	# local mirrors are always added
	if custommirrors.has_key("local"):
		mymirrors += custommirrors["local"]

	if "nomirror" in restrict or \
	   "mirror" in restrict:
		# We don't add any mirrors.
		pass
	else:
		if try_mirrors:
			mymirrors += [x.rstrip("/") for x in mysettings["GENTOO_MIRRORS"].split() if x]

	pkgdir = mysettings.get("O")
	if pkgdir:
		mydigests = Manifest(
			pkgdir, mysettings["DISTDIR"]).getTypeDigests("DIST")
	else:
		# no digests because fetch was not called for a specific package
		mydigests = {}

	fsmirrors = []
	for x in range(len(mymirrors)-1,-1,-1):
		if mymirrors[x] and mymirrors[x][0]=='/':
			fsmirrors += [mymirrors[x]]
			del mymirrors[x]

	restrict_fetch = "fetch" in restrict
	custom_local_mirrors = custommirrors.get("local", [])
	if restrict_fetch:
		# With fetch restriction, a normal uri may only be fetched from
		# custom local mirrors (if available).  A mirror:// uri may also
		# be fetched from specific mirrors (effectively overriding fetch
		# restriction, but only for specific mirrors).
		locations = custom_local_mirrors
	else:
		locations = mymirrors

	filedict={}
	primaryuri_indexes={}
	primaryuri_dict = {}
	for myuri in myuris:
		myfile=os.path.basename(myuri)
		if not filedict.has_key(myfile):
			filedict[myfile]=[]
			for y in range(0,len(locations)):
				filedict[myfile].append(locations[y]+"/distfiles/"+myfile)
		if myuri[:9]=="mirror://":
			eidx = myuri.find("/", 9)
			if eidx != -1:
				mirrorname = myuri[9:eidx]

				# Try user-defined mirrors first
				if custommirrors.has_key(mirrorname):
					for cmirr in custommirrors[mirrorname]:
						filedict[myfile].append(cmirr+"/"+myuri[eidx+1:])
						# remove the mirrors we tried from the list of official mirrors
						if cmirr.strip() in thirdpartymirrors[mirrorname]:
							thirdpartymirrors[mirrorname].remove(cmirr)
				# now try the official mirrors
				if thirdpartymirrors.has_key(mirrorname):
					shuffle(thirdpartymirrors[mirrorname])

					for locmirr in thirdpartymirrors[mirrorname]:
						filedict[myfile].append(locmirr+"/"+myuri[eidx+1:])

				if not filedict[myfile]:
					writemsg("No known mirror by the name: %s\n" % (mirrorname))
			else:
				writemsg("Invalid mirror definition in SRC_URI:\n", noiselevel=-1)
				writemsg("  %s\n" % (myuri), noiselevel=-1)
		else:
			if restrict_fetch:
				# Only fetch from specific mirrors is allowed.
				continue
			if "primaryuri" in restrict:
				# Use the source site first.
				if primaryuri_indexes.has_key(myfile):
					primaryuri_indexes[myfile] += 1
				else:
					primaryuri_indexes[myfile] = 0
				filedict[myfile].insert(primaryuri_indexes[myfile], myuri)
			else:
				filedict[myfile].append(myuri)
			primaryuris = primaryuri_dict.get(myfile)
			if primaryuris is None:
				primaryuris = []
				primaryuri_dict[myfile] = primaryuris
			primaryuris.append(myuri)

	can_fetch=True

	if listonly:
		can_fetch = False

	for var_name in ("FETCHCOMMAND", "RESUMECOMMAND"):
		if not mysettings.get(var_name, None):
			can_fetch = False

	if can_fetch:
		dirmode  = 02070
		filemode =   060
		modemask =    02
		distdir_dirs = [""]
		if "distlocks" in features:
			distdir_dirs.append(".locks")
		try:
			
			for x in distdir_dirs:
				mydir = os.path.join(mysettings["DISTDIR"], x)
				if portage.util.ensure_dirs(mydir, gid=portage_gid, mode=dirmode, mask=modemask):
					writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage.exception.OperationNotPermitted(
							"Failed to apply recursive permissions for the portage group.")
		except portage.exception.PortageException, e:
			if not os.path.isdir(mysettings["DISTDIR"]):
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Directory Not Found: DISTDIR='%s'\n" % mysettings["DISTDIR"], noiselevel=-1)
				writemsg("!!! Fetching will fail!\n", noiselevel=-1)

	if can_fetch and \
		not fetch_to_ro and \
		not os.access(mysettings["DISTDIR"], os.W_OK):
		writemsg("!!! No write access to '%s'\n" % mysettings["DISTDIR"],
			noiselevel=-1)
		can_fetch = False

	if can_fetch and use_locks and locks_in_subdir:
			distlocks_subdir = os.path.join(mysettings["DISTDIR"], locks_in_subdir)
			if not os.access(distlocks_subdir, os.W_OK):
				writemsg("!!! No write access to write to %s.  Aborting.\n" % distlocks_subdir,
					noiselevel=-1)
				return 0
			del distlocks_subdir

	for myfile in filedict:
		"""
		fetched  status
		0        nonexistent
		1        partially downloaded
		2        completely downloaded
		"""
		myfile_path = os.path.join(mysettings["DISTDIR"], myfile)
		fetched=0
		has_space = True
		file_lock = None
		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		else:
			# check if there is enough space in DISTDIR to completely store myfile
			# overestimate the filesize so we aren't bitten by FS overhead
			vfs_stat = os.statvfs(mysettings["DISTDIR"])
			if myfile in mydigests \
				and (mydigests[myfile]["size"] + vfs_stat.f_bsize) >= (vfs_stat.f_bsize * vfs_stat.f_bavail):
				writemsg("!!! Insufficient space to store %s in %s\n" % (myfile, mysettings["DISTDIR"]), noiselevel=-1)
				has_space = False

			if use_locks and can_fetch:
				waiting_msg = None
				if "parallel-fetch" in features:
					waiting_msg = ("Downloading '%s'... " + \
						"see /var/log/emerge-fetch.log for details.") % myfile
				if locks_in_subdir:
					file_lock = portage.locks.lockfile(
						os.path.join(mysettings["DISTDIR"],
						locks_in_subdir, myfile), wantnewlockfile=1,
						waiting_msg=waiting_msg)
				else:
					file_lock = portage.locks.lockfile(
						myfile_path, wantnewlockfile=1,
						waiting_msg=waiting_msg)
		try:
			if not listonly:
				if fsmirrors and not os.path.exists(myfile_path) and has_space:
					for mydir in fsmirrors:
						mirror_file = os.path.join(mydir, myfile)
						try:
							shutil.copyfile(mirror_file, myfile_path)
							writemsg(_("Local mirror has file:" + \
								" %(file)s\n" % {"file":myfile}))
							break
						except (IOError, OSError), e:
							if e.errno != errno.ENOENT:
								raise
							del e

				try:
					mystat = os.stat(myfile_path)
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
				else:
					try:
						apply_secpass_permissions(
							myfile_path, gid=portage_gid, mode=0664, mask=02,
							stat_cached=mystat)
					except portage.exception.PortageException, e:
						if not os.access(myfile_path, os.R_OK):
							writemsg("!!! Failed to adjust permissions:" + \
								" %s\n" % str(e), noiselevel=-1)

					# If the file is empty then it's obviously invalid. Remove
					# the empty file and try to download if possible.
					if mystat.st_size == 0:
						if can_fetch:
							try:
								os.unlink(myfile_path)
							except EnvironmentError:
								pass
					elif myfile not in mydigests:
						# We don't have a digest, but the file exists.  We must
						# assume that it is fully downloaded.
						continue
					else:
						if mystat.st_size < mydigests[myfile]["size"] and \
							not restrict_fetch:
							fetched = 1 # Try to resume this download.
						else:
							verified_ok, reason = portage.checksum.verify_all(
								myfile_path, mydigests[myfile])
							if not verified_ok:
								writemsg("!!! Previously fetched" + \
									" file: '%s'\n" % myfile, noiselevel=-1)
								writemsg("!!! Reason: %s\n" % reason[0],
									noiselevel=-1)
								writemsg(("!!! Got:      %s\n" + \
									"!!! Expected: %s\n") % \
									(reason[1], reason[2]), noiselevel=-1)
								if reason[0] == "Insufficient data for checksum verification":
									return 0
								if can_fetch and not restrict_fetch:
									temp_filename = \
										_checksum_failure_temp_file(
										mysettings["DISTDIR"], myfile)
									writemsg_stdout("Refetching... " + \
										"File renamed to '%s'\n\n" % \
										temp_filename, noiselevel=-1)
							else:
								eout = portage.output.EOutput()
								eout.quiet = \
									mysettings.get("PORTAGE_QUIET", None) == "1"
								digests = mydigests.get(myfile)
								if digests:
									digests = digests.keys()
									digests.sort()
									eout.ebegin(
										"%s %s ;-)" % (myfile, " ".join(digests)))
									eout.eend(0)
								continue # fetch any remaining files

			# Create a reversed list since that is optimal for list.pop().
			uri_list = filedict[myfile][:]
			uri_list.reverse()
			checksum_failure_count = 0
			tried_locations = set()
			while uri_list:
				loc = uri_list.pop()
				# Eliminate duplicates here in case we've switched to
				# "primaryuri" mode on the fly due to a checksum failure.
				if loc in tried_locations:
					continue
				tried_locations.add(loc)
				if listonly:
					writemsg_stdout(loc+" ", noiselevel=-1)
					continue
				# allow different fetchcommands per protocol
				protocol = loc[0:loc.find("://")]
				if mysettings.has_key("FETCHCOMMAND_"+protocol.upper()):
					fetchcommand=mysettings["FETCHCOMMAND_"+protocol.upper()]
				else:
					fetchcommand=mysettings["FETCHCOMMAND"]
				if mysettings.has_key("RESUMECOMMAND_"+protocol.upper()):
					resumecommand=mysettings["RESUMECOMMAND_"+protocol.upper()]
				else:
					resumecommand=mysettings["RESUMECOMMAND"]

				if not can_fetch:
					if fetched != 2:
						if fetched == 0:
							writemsg("!!! File %s isn't fetched but unable to get it.\n" % myfile,
								noiselevel=-1)
						else:
							writemsg("!!! File %s isn't fully fetched, but unable to complete it\n" % myfile,
								noiselevel=-1)
						for var_name in ("FETCHCOMMAND", "RESUMECOMMAND"):
							if not mysettings.get(var_name, None):
								writemsg(("!!! %s is unset.  It should " + \
								"have been defined in /etc/make.globals.\n") \
								 % var_name, noiselevel=-1)
						return 0
					else:
						continue

				if fetched != 2 and has_space:
					#we either need to resume or start the download
					#you can't use "continue" when you're inside a "try" block
					if fetched==1:
						#resume mode:
						writemsg(">>> Resuming download...\n")
						locfetch=resumecommand
					else:
						#normal mode:
						locfetch=fetchcommand
					writemsg_stdout(">>> Downloading '%s'\n" % \
						re.sub(r'//(.+):.+@(.+)/',r'//\1:*password*@\2/', loc))
					variables = {
						"DISTDIR": mysettings["DISTDIR"],
						"URI":     loc,
						"FILE":    myfile
					}
					import shlex, StringIO
					lexer = shlex.shlex(StringIO.StringIO(locfetch), posix=True)
					lexer.whitespace_split = True
					myfetch = [varexpand(x, mydict=variables) for x in lexer]

					spawn_keywords = {}
					# Redirect all output to stdout since some fetchers like
					# wget pollute stderr (if portage detects a problem then it
					# can send it's own message to stderr).
					spawn_keywords["fd_pipes"] = {
						0:sys.stdin.fileno(),
						1:sys.stdout.fileno(),
						2:sys.stdout.fileno()
					}
					if "userfetch" in mysettings.features and \
						os.getuid() == 0 and portage_gid and portage_uid:
						spawn_keywords.update({
							"uid"    : portage_uid,
							"gid"    : portage_gid,
							"groups" : userpriv_groups,
							"umask"  : 002})
					myret = -1
					try:

						if mysettings.selinux_enabled():
							con = selinux.getcontext()
							con = con.replace(mysettings["PORTAGE_T"], mysettings["PORTAGE_FETCH_T"])
							selinux.setexec(con)
							# bash is an allowed entrypoint, while most binaries are not
							myfetch = ["bash", "-c", "exec \"$@\"", myfetch[0]] + myfetch

						myret = portage.process.spawn(myfetch,
							env=mysettings.environ(), **spawn_keywords)

						if mysettings.selinux_enabled():
							selinux.setexec(None)

					finally:
						try:
							apply_secpass_permissions(myfile_path,
								gid=portage_gid, mode=0664, mask=02)
						except portage.exception.FileNotFound, e:
							pass
						except portage.exception.PortageException, e:
							if not os.access(myfile_path, os.R_OK):
								writemsg("!!! Failed to adjust permissions:" + \
									" %s\n" % str(e), noiselevel=-1)

					# If the file is empty then it's obviously invalid.  Don't
					# trust the return value from the fetcher.  Remove the
					# empty file and try to download again.
					try:
						if os.stat(myfile_path).st_size == 0:
							os.unlink(myfile_path)
							fetched = 0
							continue
					except EnvironmentError:
						pass

					if mydigests!=None and mydigests.has_key(myfile):
						try:
							mystat = os.stat(myfile_path)
						except OSError, e:
							if e.errno != errno.ENOENT:
								raise
							del e
							fetched = 0
						else:
							# no exception?  file exists. let digestcheck() report
							# an appropriately for size or checksum errors

							# If the fetcher reported success and the file is
							# too small, it's probably because the digest is
							# bad (upstream changed the distfile).  In this
							# case we don't want to attempt to resume. Show a
							# digest verification failure to that the user gets
							# a clue about what just happened.
							if myret != os.EX_OK and \
								mystat.st_size < mydigests[myfile]["size"]:
								# Fetch failed... Try the next one... Kill 404 files though.
								if (mystat[stat.ST_SIZE]<100000) and (len(myfile)>4) and not ((myfile[-5:]==".html") or (myfile[-4:]==".htm")):
									html404=re.compile("<title>.*(not found|404).*</title>",re.I|re.M)
									if html404.search(open(mysettings["DISTDIR"]+"/"+myfile).read()):
										try:
											os.unlink(mysettings["DISTDIR"]+"/"+myfile)
											writemsg(">>> Deleting invalid distfile. (Improper 404 redirect from server.)\n")
											fetched = 0
											continue
										except (IOError, OSError):
											pass
								fetched = 1
								continue
							if not fetchonly:
								fetched=2
								break
							else:
								# File is the correct size--check the checksums for the fetched
								# file NOW, for those users who don't have a stable/continuous
								# net connection. This way we have a chance to try to download
								# from another mirror...
								verified_ok,reason = portage.checksum.verify_all(mysettings["DISTDIR"]+"/"+myfile, mydigests[myfile])
								if not verified_ok:
									print reason
									writemsg("!!! Fetched file: "+str(myfile)+" VERIFY FAILED!\n",
										noiselevel=-1)
									writemsg("!!! Reason: "+reason[0]+"\n",
										noiselevel=-1)
									writemsg("!!! Got:      %s\n!!! Expected: %s\n" % \
										(reason[1], reason[2]), noiselevel=-1)
									if reason[0] == "Insufficient data for checksum verification":
										return 0
									temp_filename = \
										_checksum_failure_temp_file(
										mysettings["DISTDIR"], myfile)
									writemsg_stdout("Refetching... " + \
										"File renamed to '%s'\n\n" % \
										temp_filename, noiselevel=-1)
									fetched=0
									checksum_failure_count += 1
									if checksum_failure_count == \
										checksum_failure_primaryuri:
										# Switch to "primaryuri" mode in order
										# to increase the probablility of
										# of success.
										primaryuris = \
											primaryuri_dict.get(myfile)
										if primaryuris:
											uri_list.extend(
												reversed(primaryuris))
									if checksum_failure_count >= \
										checksum_failure_max_tries:
										break
								else:
									eout = portage.output.EOutput()
									eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
									digests = mydigests.get(myfile)
									if digests:
										eout.ebegin("%s %s ;-)" % \
											(myfile, " ".join(sorted(digests))))
										eout.eend(0)
									fetched=2
									break
					else:
						if not myret:
							fetched=2
							break
						elif mydigests!=None:
							writemsg("No digest file available and download failed.\n\n",
								noiselevel=-1)
		finally:
			if use_locks and file_lock:
				portage.locks.unlockfile(file_lock)

		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		if fetched != 2:
			if restrict_fetch:
				print "\n!!!", mysettings["CATEGORY"] + "/" + \
					mysettings["PF"], "has fetch restriction turned on."
				print "!!! This probably means that this " + \
					"ebuild's files must be downloaded"
				print "!!! manually.  See the comments in" + \
					" the ebuild for more information.\n"
				mysettings["EBUILD_PHASE"] = "unpack"
				spawn(EBUILD_SH_BINARY + " nofetch", mysettings)
			elif listonly:
				continue
			elif not filedict[myfile]:
				writemsg("Warning: No mirrors available for file" + \
					" '%s'\n" % (myfile), noiselevel=-1)
			else:
				writemsg("!!! Couldn't download '%s'. Aborting.\n" % myfile,
					noiselevel=-1)
			return 0
	return 1

def digestgen(myarchives, mysettings, overwrite=1, manifestonly=0, myportdb=None):
	"""
	Generates a digest file if missing.  Assumes all files are available.
	DEPRECATED: this now only is a compability wrapper for 
	            portage.manifest.Manifest()
	NOTE: manifestonly and overwrite are useless with manifest2 and
	      are therefore ignored."""
	if myportdb is None:
		writemsg("Warning: myportdb not specified to digestgen\n")
		global portdb
		myportdb = portdb
	global _doebuild_manifest_exempt_depend
	try:
		_doebuild_manifest_exempt_depend += 1
		distfiles_map = {}
		fetchlist_dict = FetchlistDict(mysettings["O"], mysettings, myportdb)
		for cpv in fetchlist_dict:
			try:
				for myfile in fetchlist_dict[cpv]:
					distfiles_map.setdefault(myfile, []).append(cpv)
			except portage.exception.InvalidDependString, e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				del e
				return 0
		mytree = os.path.dirname(os.path.dirname(mysettings["O"]))
		manifest1_compat = False
		mf = Manifest(mysettings["O"], mysettings["DISTDIR"],
			fetchlist_dict=fetchlist_dict, manifest1_compat=manifest1_compat)
		# Don't require all hashes since that can trigger excessive
		# fetches when sufficient digests already exist.  To ease transition
		# while Manifest 1 is being removed, only require hashes that will
		# exist before and after the transition.
		required_hash_types = set()
		required_hash_types.add("size")
		required_hash_types.add(portage.const.MANIFEST2_REQUIRED_HASH)
		dist_hashes = mf.fhashdict.get("DIST", {})
		missing_hashes = set()
		for myfile in distfiles_map:
			myhashes = dist_hashes.get(myfile)
			if not myhashes:
				missing_hashes.add(myfile)
				continue
			if required_hash_types.difference(myhashes):
				missing_hashes.add(myfile)
				continue
			if myhashes["size"] == 0:
				missing_hashes.add(myfile)
		if missing_hashes:
			missing_files = []
			for myfile in missing_hashes:
				try:
					st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
					missing_files.append(myfile)
				else:
					# If the file is empty then it's obviously invalid.
					if st.st_size == 0:
						missing_files.append(myfile)
			if missing_files:
				mytree = os.path.realpath(os.path.dirname(
					os.path.dirname(mysettings["O"])))
				fetch_settings = config(clone=mysettings)
				debug = mysettings.get("PORTAGE_DEBUG") == "1"
				for myfile in missing_files:
					success = False
					for cpv in distfiles_map[myfile]:
						myebuild = os.path.join(mysettings["O"],
							catsplit(cpv)[1] + ".ebuild")
						# for RESTRICT=fetch, mirror, etc...
						doebuild_environment(myebuild, "fetch",
							mysettings["ROOT"], fetch_settings,
							debug, 1, myportdb)
						alluris, aalist = myportdb.getfetchlist(
							cpv, mytree=mytree, all=True,
							mysettings=fetch_settings)
						myuris = [uri for uri in alluris \
							if os.path.basename(uri) == myfile]
						fetch_settings["A"] = myfile # for use by pkg_nofetch()
						if fetch(myuris, fetch_settings):
							success = True
							break
					if not success:
						writemsg(("!!! File %s doesn't exist, can't update " + \
							"Manifest\n") % myfile, noiselevel=-1)
						return 0
		writemsg_stdout(">>> Creating Manifest for %s\n" % mysettings["O"])
		try:
			mf.create(requiredDistfiles=myarchives,
				assumeDistHashesSometimes=True,
				assumeDistHashesAlways=(
				"assume-digests" in mysettings.features))
		except portage.exception.FileNotFound, e:
			writemsg(("!!! File %s doesn't exist, can't update " + \
				"Manifest\n") % e, noiselevel=-1)
			return 0
		mf.write(sign=False)
		if "assume-digests" not in mysettings.features:
			distlist = mf.fhashdict.get("DIST", {}).keys()
			distlist.sort()
			auto_assumed = []
			for filename in distlist:
				if not os.path.exists(
					os.path.join(mysettings["DISTDIR"], filename)):
					auto_assumed.append(filename)
			if auto_assumed:
				mytree = os.path.realpath(
					os.path.dirname(os.path.dirname(mysettings["O"])))
				cp = os.path.sep.join(mysettings["O"].split(os.path.sep)[-2:])
				pkgs = myportdb.cp_list(cp, mytree=mytree)
				pkgs.sort()
				writemsg_stdout("  digest.assumed" + portage.output.colorize("WARN",
					str(len(auto_assumed)).rjust(18)) + "\n")
				for pkg_key in pkgs:
					fetchlist = myportdb.getfetchlist(pkg_key,
						mysettings=mysettings, all=True, mytree=mytree)[1]
					pv = pkg_key.split("/")[1]
					for filename in auto_assumed:
						if filename in fetchlist:
							writemsg_stdout(
								"   %s::%s\n" % (pv, filename))
		return 1
	finally:
		_doebuild_manifest_exempt_depend -= 1

def digestParseFile(myfilename, mysettings=None):
	"""(filename) -- Parses a given file for entries matching:
	<checksumkey> <checksum_hex_string> <filename> <filesize>
	Ignores lines that don't start with a valid checksum identifier
	and returns a dict with the filenames as keys and {checksumkey:checksum}
	as the values.
	DEPRECATED: this function is now only a compability wrapper for
	            portage.manifest.Manifest()."""

	mysplit = myfilename.split(os.sep)
	if mysplit[-2] == "files" and mysplit[-1].startswith("digest-"):
		pkgdir = os.sep + os.sep.join(mysplit[:-2]).strip(os.sep)
	elif mysplit[-1] == "Manifest":
		pkgdir = os.sep + os.sep.join(mysplit[:-1]).strip(os.sep)

	if mysettings is None:
		global settings
		mysettings = config(clone=settings)

	return Manifest(pkgdir, mysettings["DISTDIR"]).getDigests()

def digestcheck(myfiles, mysettings, strict=0, justmanifest=0):
	"""Verifies checksums.  Assumes all files have been downloaded.
	DEPRECATED: this is now only a compability wrapper for 
	            portage.manifest.Manifest()."""
	if not strict:
		return 1
	pkgdir = mysettings["O"]
	manifest_path = os.path.join(pkgdir, "Manifest")
	if not os.path.exists(manifest_path):
		writemsg("!!! Manifest file not found: '%s'\n" % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
	mf = Manifest(pkgdir, mysettings["DISTDIR"])
	eout = portage.output.EOutput()
	eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
	try:
		eout.ebegin("checking ebuild checksums ;-)")
		mf.checkTypeHashes("EBUILD")
		eout.eend(0)
		eout.ebegin("checking auxfile checksums ;-)")
		mf.checkTypeHashes("AUX")
		eout.eend(0)
		eout.ebegin("checking miscfile checksums ;-)")
		mf.checkTypeHashes("MISC", ignoreMissingFiles=True)
		eout.eend(0)
		for f in myfiles:
			eout.ebegin("checking %s ;-)" % f)
			mf.checkFileHashes(mf.findFile(f), f)
			eout.eend(0)
	except KeyError, e:
		eout.eend(1)
		writemsg("\n!!! Missing digest for %s\n" % str(e), noiselevel=-1)
		return 0
	except portage.exception.FileNotFound, e:
		eout.eend(1)
		writemsg("\n!!! A file listed in the Manifest could not be found: %s\n" % str(e),
			noiselevel=-1)
		return 0
	except portage.exception.DigestException, e:
		eout.eend(1)
		writemsg("\n!!! Digest verification failed:\n", noiselevel=-1)
		writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
		writemsg("!!! Reason: %s\n" % e.value[1], noiselevel=-1)
		writemsg("!!! Got: %s\n" % e.value[2], noiselevel=-1)
		writemsg("!!! Expected: %s\n" % e.value[3], noiselevel=-1)
		return 0
	# Make sure that all of the ebuilds are actually listed in the Manifest.
	for f in os.listdir(pkgdir):
		if f.endswith(".ebuild") and not mf.hasFile("EBUILD", f):
			writemsg("!!! A file is not listed in the Manifest: '%s'\n" % \
				os.path.join(pkgdir, f), noiselevel=-1)
			return 0
	""" epatch will just grab all the patches out of a directory, so we have to
	make sure there aren't any foreign files that it might grab."""
	filesdir = os.path.join(pkgdir, "files")
	for parent, dirs, files in os.walk(filesdir):
		for d in dirs:
			if d.startswith(".") or d == "CVS":
				dirs.remove(d)
		for f in files:
			if f.startswith("."):
				continue
			f = os.path.join(parent, f)[len(filesdir) + 1:]
			file_type = mf.findFile(f)
			if file_type != "AUX" and not f.startswith("digest-"):
				writemsg("!!! A file is not listed in the Manifest: '%s'\n" % \
					os.path.join(filesdir, f), noiselevel=-1)
				return 0
	return 1

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo,actionmap,mysettings,debug,alwaysdep=0,logfile=None):
	if alwaysdep or "noauto" not in mysettings.features:
		# process dependency first
		if "dep" in actionmap[mydo]:
			retval=spawnebuild(actionmap[mydo]["dep"],actionmap,mysettings,debug,alwaysdep=alwaysdep,logfile=logfile)
			if retval:
				return retval
	kwargs = actionmap[mydo]["args"]
	mysettings["EBUILD_PHASE"] = mydo
	_doebuild_exit_status_unlink(
		mysettings.get("EBUILD_EXIT_STATUS_FILE"))
	filter_calling_env_state = mysettings._filter_calling_env
	if os.path.exists(os.path.join(mysettings["T"], "environment")):
		mysettings._filter_calling_env = True
	try:
		phase_retval = spawn(actionmap[mydo]["cmd"] % mydo,
			mysettings, debug=debug, logfile=logfile, **kwargs)
	finally:
		mysettings["EBUILD_PHASE"] = ""
		mysettings._filter_calling_env = filter_calling_env_state
	msg = _doebuild_exit_status_check(mydo, mysettings)
	if msg:
		phase_retval = 1
		from textwrap import wrap
		from portage.elog.messages import eerror
		for l in wrap(msg, 72):
			eerror(l, phase=mydo, key=mysettings.mycpv)

	if "userpriv" in mysettings.features and \
		not kwargs["droppriv"] and secpass >= 2:
		""" Privileged phases may have left files that need to be made
		writable to a less privileged user."""
		apply_recursive_permissions(mysettings["T"],
			uid=portage_uid, gid=portage_gid, dirmode=070, dirmask=0,
			filemode=060, filemask=0)

	if phase_retval == os.EX_OK:
		if mydo == "install":
			# User and group bits that match the "portage" user or group are
			# automatically mapped to PORTAGE_INST_UID and PORTAGE_INST_GID if
			# necessary.  The chown system call may clear S_ISUID and S_ISGID
			# bits, so those bits are restored if necessary.
			inst_uid = int(mysettings["PORTAGE_INST_UID"])
			inst_gid = int(mysettings["PORTAGE_INST_GID"])
			for parent, dirs, files in os.walk(mysettings["D"]):
				for fname in chain(dirs, files):
					fpath = os.path.join(parent, fname)
					mystat = os.lstat(fpath)
					if mystat.st_uid != portage_uid and \
						mystat.st_gid != portage_gid:
						continue
					myuid = -1
					mygid = -1
					if mystat.st_uid == portage_uid:
						myuid = inst_uid
					if mystat.st_gid == portage_gid:
						mygid = inst_gid
					apply_secpass_permissions(fpath, uid=myuid, gid=mygid,
						mode=mystat.st_mode, stat_cached=mystat,
						follow_links=False)
			# Note: PORTAGE_BIN_PATH may differ from the global
			# constant when portage is reinstalling itself.
			portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
			misc_sh_binary = os.path.join(portage_bin_path,
				os.path.basename(MISC_SH_BINARY))
			mycommand = " ".join([_shell_quote(misc_sh_binary),
				"install_qa_check", "install_symlink_html_docs"])
			_doebuild_exit_status_unlink(
				mysettings.get("EBUILD_EXIT_STATUS_FILE"))
			filter_calling_env_state = mysettings._filter_calling_env
			if os.path.exists(os.path.join(mysettings["T"], "environment")):
				mysettings._filter_calling_env = True
			try:
				qa_retval = spawn(mycommand, mysettings, debug=debug,
					logfile=logfile, **kwargs)
			finally:
				mysettings._filter_calling_env = filter_calling_env_state
			msg = _doebuild_exit_status_check(mydo, mysettings)
			if msg:
				qa_retval = 1
				from textwrap import wrap
				from portage.elog.messages import eerror
				for l in wrap(msg, 72):
					eerror(l, phase=mydo, key=mysettings.mycpv)
			if qa_retval != os.EX_OK:
				writemsg("!!! install_qa_check failed; exiting.\n",
					noiselevel=-1)
			return qa_retval
	return phase_retval


def eapi_is_supported(eapi):
	try:
		eapi = int(str(eapi).strip())
	except ValueError:
		eapi = -1
	if eapi < 0:
		return False
	return eapi <= portage.const.EAPI

def doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, mydbapi):

	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if mysettings.configdict["pkg"].has_key("CATEGORY"):
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(normalize_path(os.path.join(pkg_dir, "..")))
	mypv = os.path.basename(ebuild_path)[:-7]	
	mycpv = cat+"/"+mypv
	mysplit=pkgsplit(mypv,silent=0)
	if mysplit is None:
		raise portage.exception.IncorrectParameter(
			"Invalid ebuild path: '%s'" % myebuild)

	# Make a backup of PORTAGE_TMPDIR prior to calling config.reset()
	# so that the caller can override it.
	tmpdir = mysettings["PORTAGE_TMPDIR"]

	# This variable is a signal to setcpv where it triggers
	# filtering of USE for the ebuild environment.
	mysettings["EBUILD_PHASE"] = mydo
	mysettings.backup_changes("EBUILD_PHASE")

	if mydo != "depend":
		"""For performance reasons, setcpv only triggers reset when it
		detects a package-specific change in config.  For the ebuild
		environment, a reset call is forced in order to ensure that the
		latest env.d variables are used."""
		mysettings.reload()
		mysettings.reset(use_cache=use_cache)
		mysettings.setcpv(mycpv, use_cache=use_cache, mydb=mydbapi)

	# config.reset() might have reverted a change made by the caller,
	# so restore it to it's original value.
	mysettings["PORTAGE_TMPDIR"] = tmpdir

	mysettings.pop("EBUILD_PHASE", None) # remove from backupenv
	mysettings["EBUILD_PHASE"] = mydo

	mysettings["PORTAGE_MASTER_PID"] = str(os.getpid())

	# We are disabling user-specific bashrc files.
	mysettings["BASH_ENV"] = INVALID_ENV_FILE

	if debug: # Otherwise it overrides emerge's settings.
		# We have no other way to set debug... debug can't be passed in
		# due to how it's coded... Don't overwrite this so we can use it.
		mysettings["PORTAGE_DEBUG"] = "1"

	mysettings["ROOT"]     = myroot
	mysettings["STARTDIR"] = getcwd()

	mysettings["PORTAGE_REPO_NAME"] = ""
	# bindbapi has no getRepositories() method
	if mydbapi and hasattr(mydbapi, "getRepositories"):
		# do we have a origin repository name for the current package
		repopath = os.sep.join(pkg_dir.split(os.path.sep)[:-2])
		for reponame in mydbapi.getRepositories():
			if mydbapi.getRepositoryPath(reponame) == repopath:
				mysettings["PORTAGE_REPO_NAME"] = reponame
				break

	mysettings["EBUILD"]   = ebuild_path
	mysettings["O"]        = pkg_dir
	mysettings.configdict["pkg"]["CATEGORY"] = cat
	mysettings["FILESDIR"] = pkg_dir+"/files"
	mysettings["PF"]       = mypv

	mysettings["PORTDIR"] = os.path.realpath(mysettings["PORTDIR"])
	mysettings["DISTDIR"] = os.path.realpath(mysettings["DISTDIR"])
	mysettings["RPMDIR"]  = os.path.realpath(mysettings["RPMDIR"])

	mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"
	mysettings["SANDBOX_LOG"] = mycpv.replace("/", "_-_")

	mysettings["PROFILE_PATHS"] = "\n".join(mysettings.profiles)
	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if portage.util.noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mydo != "depend":
		eapi, mysettings["INHERITED"], mysettings["SLOT"], mysettings["RESTRICT"]  = \
			mydbapi.aux_get(mycpv, ["EAPI", "INHERITED", "SLOT", "RESTRICT"])
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise portage.exception.UnsupportedAPIException(mycpv, eapi)
		try:
			mysettings["PORTAGE_RESTRICT"] = " ".join(flatten(
				portage.dep.use_reduce(portage.dep.paren_reduce(
				mysettings.get("RESTRICT","")),
				uselist=mysettings.get("USE","").split())))
		except portage.exception.InvalidDependString:
			# RESTRICT is validated again inside doebuild, so let this go
			mysettings["PORTAGE_RESTRICT"] = ""

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	if mysettings.has_key("PATH"):
		mysplit=mysettings["PATH"].split(":")
	else:
		mysplit=[]
	# Note: PORTAGE_BIN_PATH may differ from the global constant
	# when portage is reinstalling itself.
	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	if portage_bin_path not in mysplit:
		mysettings["PATH"] = portage_bin_path + ":" + mysettings["PATH"]

	# Sandbox needs cannonical paths.
	mysettings["PORTAGE_TMPDIR"] = os.path.realpath(
		mysettings["PORTAGE_TMPDIR"])
	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/binpkgs"
	
	# Package {pre,post}inst and {pre,post}rm may overlap, so they must have separate
	# locations in order to prevent interference.
	if mydo in ("unmerge", "prerm", "postrm", "cleanrm"):
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(
			mysettings["PKG_TMPDIR"],
			mysettings["CATEGORY"], mysettings["PF"])
	else:
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(
			mysettings["BUILD_PREFIX"],
			mysettings["CATEGORY"], mysettings["PF"])

	mysettings["HOME"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "homedir")
	mysettings["WORKDIR"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "work")
	mysettings["D"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "image") + os.sep
	mysettings["T"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "temp")

	mysettings["PORTAGE_BASHRC"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_FILE.lstrip(os.path.sep))
	mysettings["EBUILD_EXIT_STATUS_FILE"] = os.path.join(
		mysettings["PORTAGE_BUILDDIR"], ".exit_status")

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if mydo != "depend" and "KV" not in mysettings:
		mykv,err1=ExtractKernelVersion(os.path.join(myroot, "usr/src/linux"))
		if mykv:
			# Regular source tree
			mysettings["KV"]=mykv
		else:
			mysettings["KV"]=""
		mysettings.backup_changes("KV")

	# Allow color.map to control colors associated with einfo, ewarn, etc...
	mycolors = []
	for c in ("GOOD", "WARN", "BAD", "HILITE", "BRACKET"):
		mycolors.append("%s=$'%s'" % (c, portage.output.codes[c]))
	mysettings["PORTAGE_COLORMAP"] = "\n".join(mycolors)

def prepare_build_dirs(myroot, mysettings, cleanup):

	clean_dirs = [mysettings["HOME"]]

	# We enable cleanup when we want to make sure old cruft (such as the old
	# environment) doesn't interfere with the current phase.
	if cleanup:
		clean_dirs.append(mysettings["T"])

	for clean_dir in clean_dirs:
		try:
			shutil.rmtree(clean_dir)
		except OSError, oe:
			if errno.ENOENT == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg("Operation Not Permitted: rmtree('%s')\n" % \
					clean_dir, noiselevel=-1)
				return 1
			else:
				raise

	def makedirs(dir_path):
		try:
			os.makedirs(dir_path)
		except OSError, oe:
			if errno.EEXIST == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg("Operation Not Permitted: makedirs('%s')\n" % \
					dir_path, noiselevel=-1)
				return False
			else:
				raise
		return True

	mysettings["PKG_LOGDIR"] = os.path.join(mysettings["T"], "logging")

	mydirs = [os.path.dirname(mysettings["PORTAGE_BUILDDIR"])]
	mydirs.append(os.path.dirname(mydirs[-1]))

	try:
		for mydir in mydirs:
			portage.util.ensure_dirs(mydir)
			portage.util.apply_secpass_permissions(mydir,
				gid=portage_gid, uid=portage_uid, mode=070, mask=0)
		for dir_key in ("PORTAGE_BUILDDIR", "HOME", "PKG_LOGDIR", "T"):
			"""These directories don't necessarily need to be group writable.
			However, the setup phase is commonly run as a privileged user prior
			to the other phases being run by an unprivileged user.  Currently,
			we use the portage group to ensure that the unprivleged user still
			has write access to these directories in any case."""
			portage.util.ensure_dirs(mysettings[dir_key], mode=0775)
			portage.util.apply_secpass_permissions(mysettings[dir_key],
				uid=portage_uid, gid=portage_gid)
	except portage.exception.PermissionDenied, e:
		writemsg("Permission Denied: %s\n" % str(e), noiselevel=-1)
		return 1
	except portage.exception.OperationNotPermitted, e:
		writemsg("Operation Not Permitted: %s\n" % str(e), noiselevel=-1)
		return 1
	except portage.exception.FileNotFound, e:
		writemsg("File Not Found: '%s'\n" % str(e), noiselevel=-1)
		return 1

	features_dirs = {
		"ccache":{
			"basedir_var":"CCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "ccache"),
			"always_recurse":False},
		"confcache":{
			"basedir_var":"CONFCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "confcache"),
			"always_recurse":False},
		"distcc":{
			"basedir_var":"DISTCC_DIR",
			"default_dir":os.path.join(mysettings["BUILD_PREFIX"], ".distcc"),
			"subdirs":("lock", "state"),
			"always_recurse":True}
	}
	dirmode  = 02070
	filemode =   060
	modemask =    02
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()
	from portage.data import secpass
	droppriv = secpass >= 2 and \
		"userpriv" in mysettings.features and \
		"userpriv" not in restrict
	for myfeature, kwargs in features_dirs.iteritems():
		if myfeature in mysettings.features:
			basedir = mysettings[kwargs["basedir_var"]]
			if basedir == "":
				basedir = kwargs["default_dir"]
				mysettings[kwargs["basedir_var"]] = basedir
			try:
				mydirs = [mysettings[kwargs["basedir_var"]]]
				if "subdirs" in kwargs:
					for subdir in kwargs["subdirs"]:
						mydirs.append(os.path.join(basedir, subdir))
				for mydir in mydirs:
					modified = portage.util.ensure_dirs(mydir)
					# Generally, we only want to apply permissions for
					# initial creation.  Otherwise, we don't know exactly what
					# permissions the user wants, so should leave them as-is.
					droppriv_fix = False
					if droppriv:
						st = os.stat(mydir)
						if st.st_gid != portage_gid or \
							not stat.S_IMODE(st.st_mode) & dirmode:
							droppriv_fix = True
					if modified or kwargs["always_recurse"] or droppriv_fix:
						if modified:
							writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
								noiselevel=-1)
						def onerror(e):
							raise	# The feature is disabled if a single error
									# occurs during permissions adjustment.
						if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
							raise portage.exception.OperationNotPermitted(
								"Failed to apply recursive permissions for the portage group.")
			except portage.exception.PortageException, e:
				mysettings.features.remove(myfeature)
				mysettings["FEATURES"] = " ".join(mysettings.features)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Failed resetting perms on %s='%s'\n" % \
					(kwargs["basedir_var"], basedir), noiselevel=-1)
				writemsg("!!! Disabled FEATURES='%s'\n" % myfeature,
					noiselevel=-1)
				time.sleep(5)

	workdir_mode = 0700
	try:
		mode = mysettings["PORTAGE_WORKDIR_MODE"]
		if mode.isdigit():
			parsed_mode = int(mode, 8)
		elif mode == "":
			raise KeyError()
		else:
			raise ValueError()
		if parsed_mode & 07777 != parsed_mode:
			raise ValueError("Invalid file mode: %s" % mode)
		else:
			workdir_mode = parsed_mode
	except KeyError, e:
		writemsg("!!! PORTAGE_WORKDIR_MODE is unset, using %s.\n" % oct(workdir_mode))
	except ValueError, e:
		if len(str(e)) > 0:
			writemsg("%s\n" % e)
		writemsg("!!! Unable to parse PORTAGE_WORKDIR_MODE='%s', using %s.\n" % \
		(mysettings["PORTAGE_WORKDIR_MODE"], oct(workdir_mode)))
	mysettings["PORTAGE_WORKDIR_MODE"] = oct(workdir_mode)
	try:
		apply_secpass_permissions(mysettings["WORKDIR"],
		uid=portage_uid, gid=portage_gid, mode=workdir_mode)
	except portage.exception.FileNotFound:
		pass # ebuild.sh will create it

	if mysettings.get("PORT_LOGDIR", "") == "":
		while "PORT_LOGDIR" in mysettings:
			del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		try:
			modified = portage.util.ensure_dirs(mysettings["PORT_LOGDIR"])
			if modified:
				apply_secpass_permissions(mysettings["PORT_LOGDIR"],
					uid=portage_uid, gid=portage_gid, mode=02770)
		except portage.exception.PortageException, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! Permission issues with PORT_LOGDIR='%s'\n" % \
				mysettings["PORT_LOGDIR"], noiselevel=-1)
			writemsg("!!! Disabling logging.\n", noiselevel=-1)
			while "PORT_LOGDIR" in mysettings:
				del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		logid_path = os.path.join(mysettings["PORTAGE_BUILDDIR"], ".logid")
		if not os.path.exists(logid_path):
			f = open(logid_path, "w")
			f.close()
			del f
		logid_time = time.strftime("%Y%m%d-%H%M%S",
			time.gmtime(os.stat(logid_path).st_mtime))
		mysettings["PORTAGE_LOG_FILE"] = os.path.join(
			mysettings["PORT_LOGDIR"], "%s:%s:%s.log" % \
			(mysettings["CATEGORY"], mysettings["PF"], logid_time))
		del logid_path, logid_time
	else:
		# When sesandbox is enabled, only log if PORT_LOGDIR is explicitly
		# enabled since it is possible that local SELinux security policies
		# do not allow ouput to be piped out of the sesandbox domain.
		if not (mysettings.selinux_enabled() and \
			"sesandbox" in mysettings.features):
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				mysettings["T"], "build.log")

def _doebuild_exit_status_check(mydo, settings):
	"""
	Returns an error string if the shell appeared
	to exit unsuccessfully, None otherwise.
	"""
	exit_status_file = settings.get("EBUILD_EXIT_STATUS_FILE")
	if not exit_status_file or \
		os.path.exists(exit_status_file):
		return None
	msg = ("The ebuild phase '%s' has exited " % mydo) + \
	"unexpectedly. This type of behavior " + \
	"is known to be triggered " + \
	"by things such as failed variable " + \
	"assignments (bug #190128) or bad substitution " + \
	"errors (bug #200313)."
	return msg

def _doebuild_exit_status_unlink(exit_status_file):
	"""
	Double check to make sure it really doesn't exist
	and raise an OSError if it still does (it shouldn't).
	OSError if necessary.
	"""
	if not exit_status_file:
		return
	try:
		os.unlink(exit_status_file)
	except OSError:
		pass
	if os.path.exists(exit_status_file):
		os.unlink(exit_status_file)

_doebuild_manifest_exempt_depend = 0
_doebuild_manifest_checked = None

def doebuild(myebuild, mydo, myroot, mysettings, debug=0, listonly=0,
	fetchonly=0, cleanup=0, dbkey=None, use_cache=1, fetchall=0, tree=None,
	mydbapi=None, vartree=None, prev_mtimes=None):
	
	"""
	Wrapper function that invokes specific ebuild phases through the spawning
	of ebuild.sh
	
	@param myebuild: name of the ebuild to invoke the phase on (CPV)
	@type myebuild: String
	@param mydo: Phase to run
	@type mydo: String
	@param myroot: $ROOT (usually '/', see man make.conf)
	@type myroot: String
	@param mysettings: Portage Configuration
	@type mysettings: instance of portage.config
	@param debug: Turns on various debug information (eg, debug for spawn)
	@type debug: Boolean
	@param listonly: Used to wrap fetch(); passed such that fetch only lists files required.
	@type listonly: Boolean
	@param fetchonly: Used to wrap fetch(); passed such that files are only fetched (no other actions)
	@type fetchonly: Boolean
	@param cleanup: Passed to prepare_build_dirs (TODO: what does it do?)
	@type cleanup: Boolean
	@param dbkey: A dict (usually keys and values from the depend phase, such as KEYWORDS, USE, etc..)
	@type dbkey: Dict or String
	@param use_cache: Enables the cache
	@type use_cache: Boolean
	@param fetchall: Used to wrap fetch(), fetches all URI's (even ones invalid due to USE conditionals)
	@type fetchall: Boolean
	@param tree: Which tree to use ('vartree','porttree','bintree', etc..), defaults to 'porttree'
	@type tree: String
	@param mydbapi: a dbapi instance to pass to various functions; this should be a portdbapi instance.
	@type mydbapi: portdbapi instance
	@param vartree: A instance of vartree; used for aux_get calls, defaults to db[myroot]['vartree']
	@type vartree: vartree instance
	@param prev_mtimes: A dict of { filename:mtime } keys used by merge() to do config_protection
	@type prev_mtimes: dictionary
	@rtype: Boolean
	@returns:
	1. 0 for success
	2. 1 for error
	
	Most errors have an accompanying error message.
	
	listonly and fetchonly are only really necessary for operations involving 'fetch'
	prev_mtimes are only necessary for merge operations.
	Other variables may not be strictly required, many have defaults that are set inside of doebuild.
	
	"""
	
	if not tree:
		writemsg("Warning: tree not specified to doebuild\n")
		tree = "porttree"
	global db
	
	# chunked out deps for each phase, so that ebuild binary can use it 
	# to collapse targets down.
	actionmap_deps={
	"setup":  [],
	"unpack": ["setup"],
	"compile":["unpack"],
	"test":   ["compile"],
	"install":["test"],
	"rpm":    ["install"],
	"package":["install"],
	}
	
	if mydbapi is None:
		mydbapi = db[myroot][tree].dbapi

	if vartree is None and mydo in ("merge", "qmerge", "unmerge"):
		vartree = db[myroot]["vartree"]

	features = mysettings.features

	validcommands = ["help","clean","prerm","postrm","cleanrm","preinst","postinst",
	                "config","info","setup","depend","fetch","digest",
	                "unpack","compile","test","install","rpm","qmerge","merge",
	                "package","unmerge", "manifest"]

	if mydo not in validcommands:
		validcommands.sort()
		writemsg("!!! doebuild: '%s' is not one of the following valid commands:" % mydo,
			noiselevel=-1)
		for vcount in range(len(validcommands)):
			if vcount%6 == 0:
				writemsg("\n!!! ", noiselevel=-1)
			writemsg(validcommands[vcount].ljust(11), noiselevel=-1)
		writemsg("\n", noiselevel=-1)
		return 1

	if not os.path.exists(myebuild):
		writemsg("!!! doebuild: %s not found for %s\n" % (myebuild, mydo),
			noiselevel=-1)
		return 1

	global _doebuild_manifest_exempt_depend

	if "strict" in features and \
		"digest" not in features and \
		tree == "porttree" and \
		mydo not in ("digest", "manifest", "help") and \
		not _doebuild_manifest_exempt_depend:
		# Always verify the ebuild checksums before executing it.
		pkgdir = os.path.dirname(myebuild)
		manifest_path = os.path.join(pkgdir, "Manifest")
		global _doebuild_manifest_checked
		# Avoid checking the same Manifest several times in a row during a
		# regen with an empty cache.
		if _doebuild_manifest_checked != manifest_path:
			if not os.path.exists(manifest_path):
				writemsg("!!! Manifest file not found: '%s'\n" % manifest_path,
					noiselevel=-1)
				return 1
			mf = Manifest(pkgdir, mysettings["DISTDIR"])
			try:
				mf.checkTypeHashes("EBUILD")
			except portage.exception.FileNotFound, e:
				writemsg("!!! A file listed in the Manifest " + \
					"could not be found: %s\n" % str(e), noiselevel=-1)
				return 1
			except portage.exception.DigestException, e:
				writemsg("!!! Digest verification failed:\n", noiselevel=-1)
				writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
				writemsg("!!! Reason: %s\n" % e.value[1], noiselevel=-1)
				writemsg("!!! Got: %s\n" % e.value[2], noiselevel=-1)
				writemsg("!!! Expected: %s\n" % e.value[3], noiselevel=-1)
				return 1
			# Make sure that all of the ebuilds are actually listed in the
			# Manifest.
			for f in os.listdir(pkgdir):
				if f.endswith(".ebuild") and not mf.hasFile("EBUILD", f):
					writemsg("!!! A file is not listed in the " + \
					"Manifest: '%s'\n" % os.path.join(pkgdir, f),
					noiselevel=-1)
					return 1
			_doebuild_manifest_checked = manifest_path

	def exit_status_check(retval):
		if retval != os.EX_OK:
			return retval
		msg = _doebuild_exit_status_check(mydo, mysettings)
		if msg:
			retval = 1
			from textwrap import wrap
			from portage.elog.messages import eerror
			for l in wrap(msg, 72):
				eerror(l, phase=mydo, key=mysettings.mycpv)
		return retval

	# Note: PORTAGE_BIN_PATH may differ from the global
	# constant when portage is reinstalling itself.
	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	ebuild_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(EBUILD_SH_BINARY))
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))

	logfile=None
	builddir_lock = None
	tmpdir = None
	tmpdir_orig = None
	filter_calling_env_state = mysettings._filter_calling_env
	try:
		if mydo in ("digest", "manifest", "help"):
			# Temporarily exempt the depend phase from manifest checks, in case
			# aux_get calls trigger cache generation.
			_doebuild_manifest_exempt_depend += 1

		# If we don't need much space and we don't need a constant location,
		# we can temporarily override PORTAGE_TMPDIR with a random temp dir
		# so that there's no need for locking and it can be used even if the
		# user isn't in the portage group.
		if mydo in ("info",):
			from tempfile import mkdtemp
			tmpdir = mkdtemp()
			tmpdir_orig = mysettings["PORTAGE_TMPDIR"]
			mysettings["PORTAGE_TMPDIR"] = tmpdir

		doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
			use_cache, mydbapi)

		# get possible slot information from the deps file
		if mydo == "depend":
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
			droppriv = "userpriv" in mysettings.features
			if isinstance(dbkey, dict):
				mysettings["dbkey"] = ""
				pr, pw = os.pipe()
				fd_pipes = {
					0:sys.stdin.fileno(),
					1:sys.stdout.fileno(),
					2:sys.stderr.fileno(),
					9:pw}
				mypids = spawn(_shell_quote(ebuild_sh_binary) + " depend",
					mysettings,
					fd_pipes=fd_pipes, returnpid=True, droppriv=droppriv)
				os.close(pw) # belongs exclusively to the child process now
				maxbytes = 1024
				mybytes = []
				while True:
					mybytes.append(os.read(pr, maxbytes))
					if not mybytes[-1]:
						break
				os.close(pr)
				mybytes = "".join(mybytes)
				global auxdbkeys
				for k, v in izip(auxdbkeys, mybytes.splitlines()):
					dbkey[k] = v
				retval = os.waitpid(mypids[0], 0)[1]
				portage.process.spawned_pids.remove(mypids[0])
				# If it got a signal, return the signal that was sent, but
				# shift in order to distinguish it from a return value. (just
				# like portage.process.spawn() would do).
				if retval & 0xff:
					return (retval & 0xff) << 8
				# Otherwise, return its exit code.
				return retval >> 8
			elif dbkey:
				mysettings["dbkey"] = dbkey
			else:
				mysettings["dbkey"] = \
					os.path.join(mysettings.depcachedir, "aux_db_key_temp")

			return spawn(_shell_quote(ebuild_sh_binary) + " depend",
				mysettings,
				droppriv=droppriv)

		# Validate dependency metadata here to ensure that ebuilds with invalid
		# data are never installed (even via the ebuild command).
		invalid_dep_exempt_phases = \
			set(["clean", "cleanrm", "help", "prerm", "postrm"])
		mycpv = mysettings["CATEGORY"] + "/" + mysettings["PF"]
		dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		misc_keys = ["LICENSE", "PROVIDE", "RESTRICT", "SRC_URI"]
		other_keys = ["SLOT"]
		all_keys = dep_keys + misc_keys + other_keys
		metadata = dict(izip(all_keys, mydbapi.aux_get(mycpv, all_keys)))
		class FakeTree(object):
			def __init__(self, mydb):
				self.dbapi = mydb
		dep_check_trees = {myroot:{}}
		dep_check_trees[myroot]["porttree"] = \
			FakeTree(fakedbapi(settings=mysettings))
		for dep_type in dep_keys:
			mycheck = dep_check(metadata[dep_type], None, mysettings,
				myuse="all", myroot=myroot, trees=dep_check_trees)
			if not mycheck[0]:
				writemsg("%s: %s\n%s\n" % (
					dep_type, metadata[dep_type], mycheck[1]), noiselevel=-1)
				if mydo not in invalid_dep_exempt_phases:
					return 1
			del dep_type, mycheck
		for k in misc_keys:
			try:
				portage.dep.use_reduce(
					portage.dep.paren_reduce(metadata[k]), matchall=True)
			except portage.exception.InvalidDependString, e:
				writemsg("%s: %s\n%s\n" % (
					k, metadata[k], str(e)), noiselevel=-1)
				del e
				if mydo not in invalid_dep_exempt_phases:
					return 1
			del k
		if not metadata["SLOT"]:
			writemsg("SLOT is undefined\n", noiselevel=-1)
			if mydo not in invalid_dep_exempt_phases:
				return 1
		del mycpv, dep_keys, metadata, misc_keys, FakeTree, dep_check_trees

		if "PORTAGE_TMPDIR" not in mysettings or \
			not os.path.isdir(mysettings["PORTAGE_TMPDIR"]):
			writemsg("The directory specified in your " + \
				"PORTAGE_TMPDIR variable, '%s',\n" % \
				mysettings.get("PORTAGE_TMPDIR", ""), noiselevel=-1)
			writemsg("does not exist.  Please create this directory or " + \
				"correct your PORTAGE_TMPDIR setting.\n", noiselevel=-1)
			return 1

		if mydo == "unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		# Build directory creation isn't required for any of these.
		have_build_dirs = False
		if mydo not in ("clean", "cleanrm", "digest",
			"fetch", "help", "manifest"):
			mystatus = prepare_build_dirs(myroot, mysettings, cleanup)
			if mystatus:
				return mystatus
			have_build_dirs = True
			# PORTAGE_LOG_FILE is set above by the prepare_build_dirs() call.
			logfile = mysettings.get("PORTAGE_LOG_FILE")
			if logfile and not os.access(os.path.dirname(logfile), os.W_OK):
				logfile = None
		if have_build_dirs:
			env_file = os.path.join(mysettings["T"], "environment")
			env_stat = None
			saved_env = None
			try:
				env_stat = os.stat(env_file)
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
			if not env_stat:
				saved_env = os.path.join(
					os.path.dirname(myebuild), "environment.bz2")
				if not os.path.isfile(saved_env):
					saved_env = None
			if saved_env:
				retval = os.system(
					"bzip2 -dc %s > %s" % \
					(_shell_quote(saved_env),
					_shell_quote(env_file)))
				try:
					env_stat = os.stat(env_file)
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
				if os.WIFEXITED(retval) and \
					os.WEXITSTATUS(retval) == os.EX_OK and \
					env_stat and env_stat.st_size > 0:
					# This is a signal to ebuild.sh, so that it knows to filter
					# out things like SANDBOX_{DENY,PREDICT,READ,WRITE} that
					# would be preserved between normal phases.
					open(env_file + ".raw", "w")
				else:
					writemsg(("!!! Error extracting saved " + \
						"environment: '%s'\n") % \
						saved_env, noiselevel=-1)
					try:
						os.unlink(env_file)
					except OSError, e:
						if e.errno != errno.ENOENT:
							raise
						del e
					env_stat = None
			if env_stat:
				mysettings._filter_calling_env = True
			else:
				for var in ("ARCH", ):
					value = mysettings.get(var)
					if value and value.strip():
						continue
					msg = ("%s is not set... " % var) + \
						("Are you missing the '%setc/make.profile' symlink? " % \
						mysettings["PORTAGE_CONFIGROOT"]) + \
						"Is the symlink correct? " + \
						"Is your portage tree complete?"
					from portage.elog.messages import eerror
					from textwrap import wrap
					for line in wrap(msg, 70):
						eerror(line, phase="setup", key=mysettings.mycpv)
					from portage.elog import elog_process
					elog_process(mysettings.mycpv, mysettings)
					return 1
			del env_file, env_stat, saved_env
			_doebuild_exit_status_unlink(
				mysettings.get("EBUILD_EXIT_STATUS_FILE"))
		else:
			mysettings.pop("EBUILD_EXIT_STATUS_FILE", None)

		# if any of these are being called, handle them -- running them out of
		# the sandbox -- and stop now.
		if mydo in ["clean","cleanrm"]:
			return spawn(_shell_quote(ebuild_sh_binary) + " clean", mysettings,
				debug=debug, free=1, logfile=None)
		elif mydo == "help":
			return spawn(_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)
		elif mydo == "setup":
			infodir = os.path.join(
				mysettings["PORTAGE_BUILDDIR"], "build-info")
			if os.path.isdir(infodir):
				"""Load USE flags for setup phase of a binary package.
				Ideally, the environment.bz2 would be used instead."""
				mysettings.load_infodir(infodir)
			retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo, mysettings,
				debug=debug, free=1, logfile=logfile)
			retval = exit_status_check(retval)
			if secpass >= 2:
				""" Privileged phases may have left files that need to be made
				writable to a less privileged user."""
				apply_recursive_permissions(mysettings["T"],
					uid=portage_uid, gid=portage_gid, dirmode=070, dirmask=0,
					filemode=060, filemask=0)
			return retval
		elif mydo == "preinst":
			phase_retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)
			phase_retval = exit_status_check(phase_retval)
			if phase_retval == os.EX_OK:
				# Post phase logic and tasks that have been factored out of
				# ebuild.sh.
				myargs = [_shell_quote(misc_sh_binary),
					"preinst_bsdflags", "preinst_mask",
					"preinst_sfperms", "preinst_selinux_labels",
					"preinst_suid_scan"]
				_doebuild_exit_status_unlink(
					mysettings.get("EBUILD_EXIT_STATUS_FILE"))
				mysettings["EBUILD_PHASE"] = ""
				phase_retval = spawn(" ".join(myargs),
					mysettings, debug=debug, free=1, logfile=logfile)
				phase_retval = exit_status_check(phase_retval)
				if phase_retval != os.EX_OK:
					writemsg("!!! post preinst failed; exiting.\n",
						noiselevel=-1)
			return phase_retval
		elif mydo == "postinst":
			phase_retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)
			phase_retval = exit_status_check(phase_retval)
			if phase_retval == os.EX_OK:
				# Post phase logic and tasks that have been factored out of
				# ebuild.sh.
				myargs = [_shell_quote(misc_sh_binary), "postinst_bsdflags"]
				_doebuild_exit_status_unlink(
					mysettings.get("EBUILD_EXIT_STATUS_FILE"))
				mysettings["EBUILD_PHASE"] = ""
				phase_retval = spawn(" ".join(myargs),
					mysettings, debug=debug, free=1, logfile=logfile)
				phase_retval = exit_status_check(phase_retval)
				if phase_retval != os.EX_OK:
					writemsg("!!! post postinst failed; exiting.\n",
						noiselevel=-1)
			return phase_retval
		elif mydo in ("prerm", "postrm", "config", "info"):
			mysettings.load_infodir(mysettings["O"])
			retval =  spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)
			retval = exit_status_check(retval)
			return retval

		mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))

		# Make sure we get the correct tree in case there are overlays.
		mytree = os.path.realpath(
			os.path.dirname(os.path.dirname(mysettings["O"])))
		try:
			newuris, alist = mydbapi.getfetchlist(
				mycpv, mytree=mytree, mysettings=mysettings)
			alluris, aalist = mydbapi.getfetchlist(
				mycpv, mytree=mytree, all=True, mysettings=mysettings)
		except portage.exception.InvalidDependString, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! Invalid SRC_URI for '%s'.\n" % mycpv, noiselevel=-1)
			del e
			return 1
		mysettings["A"] = " ".join(alist)
		mysettings["AA"] = " ".join(aalist)
		if ("mirror" in features) or fetchall:
			fetchme = alluris[:]
			checkme = aalist[:]
		elif mydo == "digest":
			fetchme = alluris[:]
			checkme = aalist[:]
			# Skip files that we already have digests for.
			mf = Manifest(mysettings["O"], mysettings["DISTDIR"])
			mydigests = mf.getTypeDigests("DIST")
			required_hash_types = set()
			required_hash_types.add("size")
			required_hash_types.add(portage.const.MANIFEST2_REQUIRED_HASH)
			for filename, hashes in mydigests.iteritems():
				if not required_hash_types.difference(hashes):
					checkme = [i for i in checkme if i != filename]
					fetchme = [i for i in fetchme \
						if os.path.basename(i) != filename]
				del filename, hashes
		else:
			fetchme = newuris[:]
			checkme = alist[:]

		# Only try and fetch the files if we are going to need them ...
		# otherwise, if user has FEATURES=noauto and they run `ebuild clean
		# unpack compile install`, we will try and fetch 4 times :/
		need_distfiles = (mydo in ("fetch", "unpack") or \
			mydo not in ("digest", "manifest") and "noauto" not in features)
		if need_distfiles and not fetch(
			fetchme, mysettings, listonly=listonly, fetchonly=fetchonly):
			if have_build_dirs:
				# Create an elog message for this fetch failure since the
				# mod_echo module might push the original message off of the
				# top of the terminal and prevent the user from being able to
				# see it.
				from portage.elog.messages import eerror
				eerror("Fetch failed for '%s'" % mycpv,
					phase="unpack", key=mycpv)
				from portage.elog import elog_process
				elog_process(mysettings.mycpv, mysettings)
			return 1

		if mydo == "fetch" and listonly:
			return 0

		try:
			if mydo == "manifest":
				return not digestgen(aalist, mysettings, overwrite=1,
					manifestonly=1, myportdb=mydbapi)
			elif mydo == "digest":
				return not digestgen(aalist, mysettings, overwrite=1,
					myportdb=mydbapi)
			elif "digest" in mysettings.features:
				digestgen(aalist, mysettings, overwrite=0, myportdb=mydbapi)
		except portage.exception.PermissionDenied, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			if mydo in ("digest", "manifest"):
				return 1

		# See above comment about fetching only when needed
		if not digestcheck(checkme, mysettings, ("strict" in features),
			(mydo not in ["digest","fetch","unpack"] and \
			mysettings.get("PORTAGE_CALLER", None) == "ebuild" and \
			"noauto" in features)):
			return 1

		if mydo == "fetch":
			return 0

		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		if (mydo != "setup" and "noauto" not in features) or mydo == "unpack":
			orig_distdir = mysettings["DISTDIR"]
			mysettings["PORTAGE_ACTUAL_DISTDIR"] = orig_distdir
			edpath = mysettings["DISTDIR"] = \
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "distdir")
			if os.path.exists(edpath):
				try:
					if os.path.isdir(edpath) and not os.path.islink(edpath):
						shutil.rmtree(edpath)
					else:
						os.unlink(edpath)
				except OSError:
					print "!!! Failed reseting ebuild distdir path, " + edpath
					raise
			os.mkdir(edpath)
			apply_secpass_permissions(edpath, uid=portage_uid, mode=0755)
			try:
				for file in alist:
					os.symlink(os.path.join(orig_distdir, file),
						os.path.join(edpath, file))
			except OSError:
				print "!!! Failed symlinking in '%s' to ebuild distdir" % file
				raise

		#initial dep checks complete; time to process main commands

		restrict = mysettings["PORTAGE_RESTRICT"].split()
		nosandbox = (("userpriv" in features) and \
			("usersandbox" not in features) and \
			"userpriv" not in restrict and \
			"nouserpriv" not in restrict)
		if nosandbox and ("userpriv" not in features or \
			"userpriv" in restrict or \
			"nouserpriv" in restrict):
			nosandbox = ("sandbox" not in features and \
				"usersandbox" not in features)

		sesandbox = mysettings.selinux_enabled() and \
			"sesandbox" in mysettings.features

		droppriv = "userpriv" in mysettings.features and \
			"userpriv" not in restrict

		fakeroot = "fakeroot" in mysettings.features

		ebuild_sh = _shell_quote(ebuild_sh_binary) + " %s"
		misc_sh = _shell_quote(misc_sh_binary) + " dyn_%s"

		# args are for the to spawn function
		actionmap = {
"setup":  {"cmd":ebuild_sh, "args":{"droppriv":0,        "free":1,         "sesandbox":0,         "fakeroot":0}},
"unpack": {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":0,         "sesandbox":sesandbox, "fakeroot":0}},
"compile":{"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":nosandbox, "sesandbox":sesandbox, "fakeroot":0}},
"test":   {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":nosandbox, "sesandbox":sesandbox, "fakeroot":0}},
"install":{"cmd":ebuild_sh, "args":{"droppriv":0,        "free":0,         "sesandbox":sesandbox, "fakeroot":fakeroot}},
"rpm":    {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
"package":{"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
		}

		# merge the deps in so we have again a 'full' actionmap
		# be glad when this can die.
		for x in actionmap:
			if len(actionmap_deps.get(x, [])):
				actionmap[x]["dep"] = ' '.join(actionmap_deps[x])

		if mydo in actionmap:
			retval = spawnebuild(mydo,
				actionmap, mysettings, debug, logfile=logfile)
		elif mydo=="qmerge":
			# check to ensure install was run.  this *only* pops up when users
			# forget it and are using ebuild
			if not os.path.exists(
				os.path.join(mysettings["PORTAGE_BUILDDIR"], ".installed")):
				writemsg("!!! mydo=qmerge, but the install phase has not been run\n",
					noiselevel=-1)
				return 1
			# qmerge is a special phase that implies noclean.
			if "noclean" not in mysettings.features:
				mysettings.features.append("noclean")
			#qmerge is specifically not supposed to do a runtime dep check
			retval = merge(
				mysettings["CATEGORY"], mysettings["PF"], mysettings["D"],
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "build-info"),
				myroot, mysettings, myebuild=mysettings["EBUILD"], mytree=tree,
				mydbapi=mydbapi, vartree=vartree, prev_mtimes=prev_mtimes)
		elif mydo=="merge":
			retval = spawnebuild("install", actionmap, mysettings, debug,
				alwaysdep=1, logfile=logfile)
			retval = exit_status_check(retval)
			if retval != os.EX_OK:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				from portage.elog import elog_process
				elog_process(mysettings.mycpv, mysettings)
			if retval == os.EX_OK:
				retval = merge(mysettings["CATEGORY"], mysettings["PF"],
					mysettings["D"], os.path.join(mysettings["PORTAGE_BUILDDIR"],
					"build-info"), myroot, mysettings,
					myebuild=mysettings["EBUILD"], mytree=tree, mydbapi=mydbapi,
					vartree=vartree, prev_mtimes=prev_mtimes)
		else:
			print "!!! Unknown mydo:",mydo
			return 1

		return retval

	finally:
		mysettings._filter_calling_env = filter_calling_env_state
		if tmpdir:
			mysettings["PORTAGE_TMPDIR"] = tmpdir_orig
			shutil.rmtree(tmpdir)
		if builddir_lock:
			portage.locks.unlockdir(builddir_lock)

		# Make sure that DISTDIR is restored to it's normal value before we return!
		if "PORTAGE_ACTUAL_DISTDIR" in mysettings:
			mysettings["DISTDIR"] = mysettings["PORTAGE_ACTUAL_DISTDIR"]
			del mysettings["PORTAGE_ACTUAL_DISTDIR"]

		if logfile:
			try:
				if os.stat(logfile).st_size == 0:
					os.unlink(logfile)
			except OSError:
				pass

		if mydo in ("digest", "manifest", "help"):
			# If necessary, depend phase has been triggered by aux_get calls
			# and the exemption is no longer needed.
			_doebuild_manifest_exempt_depend -= 1

expandcache={}

def _movefile(src, dest, **kwargs):
	"""Calls movefile and raises a PortageException if an error occurs."""
	if movefile(src, dest, **kwargs) is None:
		raise portage.exception.PortageException(
			"mv '%s' '%s'" % (src, dest))

def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	global lchown
	if mysettings is None:
		global settings
		mysettings = settings
	selinux_enabled = mysettings.selinux_enabled()
	try:
		if not sstat:
			sstat=os.lstat(src)

	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except (OSError, IOError):
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if bsd_chflags:
		if destexists and dstat.st_flags != 0:
			bsd_chflags.lchflags(dest, 0)
		# Use normal stat/chflags for the parent since we want to
		# follow any symlinks to the real parent directory.
		pflags = os.stat(os.path.dirname(dest)).st_flags
		if pflags != 0:
			bsd_chflags.chflags(os.path.dirname(dest), 0)

	if destexists:
		if stat.S_ISLNK(dstat[stat.ST_MODE]):
			try:
				os.unlink(dest)
				destexists=0
			except SystemExit, e:
				raise
			except Exception, e:
				pass

	if stat.S_ISLNK(sstat[stat.ST_MODE]):
		try:
			target=os.readlink(src)
			if mysettings and mysettings["D"]:
				if target.find(mysettings["D"])==0:
					target=target[len(mysettings["D"]):]
			if destexists and not stat.S_ISDIR(dstat[stat.ST_MODE]):
				os.unlink(dest)
			if selinux_enabled:
				sid = selinux.get_lsid(src)
				selinux.secure_symlink(target,dest,sid)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			# utime() only works on the target of a symlink, so it's not
			# possible to perserve mtime on symlinks.
			return os.lstat(dest)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! failed to properly create symlink:"
			print "!!!",dest,"->",target
			print "!!!",e
			return None

	renamefailed=1
	if sstat[stat.ST_DEV]==dstat[stat.ST_DEV] or selinux_enabled:
		try:
			if selinux_enabled:
				ret=selinux.secure_rename(src,dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except SystemExit, e:
			raise
		except Exception, e:
			if e[0]!=errno.EXDEV:
				# Some random error.
				print "!!! Failed to move",src,"to",dest
				print "!!!",e
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		didcopy=0
		if stat.S_ISREG(sstat[stat.ST_MODE]):
			try: # For safety copy then move it over.
				if selinux_enabled:
					selinux.secure_copy(src,dest+"#new")
					selinux.secure_rename(dest+"#new",dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except SystemExit, e:
				raise
			except Exception, e:
				print '!!! copy',src,'->',dest,'failed.'
				print "!!!",e
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			if selinux_enabled:
				a=commands.getstatusoutput(MOVE_BINARY+" -c -f "+"'"+src+"' '"+dest+"'")
			else:
				a=commands.getstatusoutput(MOVE_BINARY+" -f "+"'"+src+"' '"+dest+"'")
				if a[0]!=0:
					print "!!! Failed to move special file:"
					print "!!! '"+src+"' to '"+dest+"'"
					print "!!!",a
					return None # failure
		try:
			if didcopy:
				if stat.S_ISLNK(sstat[stat.ST_MODE]):
					lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				else:
					os.chown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				os.chmod(dest, stat.S_IMODE(sstat[stat.ST_MODE])) # Sticky is reset on chown
				os.unlink(src)
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! Failed to chown/chmod/unlink in movefile()"
			print "!!!",dest
			print "!!!",e
			return None

	if newmtime:
		os.utime(dest,(newmtime,newmtime))
	else:
		os.utime(dest, (sstat[stat.ST_ATIME], sstat[stat.ST_MTIME]))
		newmtime=sstat[stat.ST_MTIME]

	if bsd_chflags:
		# Restore the flags we saved before moving
		if pflags:
			bsd_chflags.chflags(os.path.dirname(dest), pflags)

	return newmtime

def merge(mycat, mypkg, pkgloc, infloc, myroot, mysettings, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None):
	if not os.access(myroot, os.W_OK):
		writemsg("Permission denied: access('%s', W_OK)\n" % myroot,
			noiselevel=-1)
		return errno.EACCES
	mylink = dblink(mycat, mypkg, myroot, mysettings, treetype=mytree,
		vartree=vartree)
	return mylink.merge(pkgloc, infloc, myroot, myebuild,
		mydbapi=mydbapi, prev_mtimes=prev_mtimes)

def unmerge(cat, pkg, myroot, mysettings, mytrimworld=1, vartree=None, ldpath_mtimes=None):
	mylink = dblink(
		cat, pkg, myroot, mysettings, treetype="vartree", vartree=vartree)
	try:
		mylink.lockdb()
		if mylink.exists():
			retval = mylink.unmerge(trimworld=mytrimworld, cleanup=1,
				ldpath_mtimes=ldpath_mtimes)
			if retval == os.EX_OK:
				mylink.delete()
			return retval
		return os.EX_OK
	finally:
		mylink.unlockdb()

def getCPFromCPV(mycpv):
	"""Calls pkgsplit on a cpv and returns only the cp."""
	return pkgsplit(mycpv)[0]

def dep_virtual(mysplit, mysettings):
	"Does virtual dependency conversion"
	newsplit=[]
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if isinstance(x, list):
			newsplit.append(dep_virtual(x, mysettings))
		else:
			mykey=dep_getkey(x)
			mychoices = myvirtuals.get(mykey, None)
			if mychoices:
				if len(mychoices) == 1:
					a = x.replace(mykey, mychoices[0])
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in mychoices:
						a.append(x.replace(mykey, y))
				newsplit.append(a)
			else:
				newsplit.append(x)
	return newsplit

def _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings, myroot="/",
	trees=None, **kwargs):
	"""Recursively expand new-style virtuals so as to collapse one or more
	levels of indirection.  In dep_zapdeps, new-style virtuals will be assigned
	zero cost regardless of whether or not they are currently installed. Virtual
	blockers are supported but only when the virtual expands to a single
	atom because it wouldn't necessarily make sense to block all the components
	of a compound virtual.  When more than one new-style virtual is matched,
	the matches are sorted from highest to lowest versions and the atom is
	expanded to || ( highest match ... lowest match )."""
	newsplit = []
	# According to GLEP 37, RDEPEND is the only dependency type that is valid
	# for new-style virtuals.  Repoman should enforce this.
	dep_keys = ["RDEPEND", "DEPEND", "PDEPEND"]
	def compare_pkgs(a, b):
		return pkgcmp(b[1], a[1])
	portdb = trees[myroot]["porttree"].dbapi
	if kwargs["use_binaries"]:
		portdb = trees[myroot]["bintree"].dbapi
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			newsplit.append(_expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, **kwargs))
			continue
		if portage.dep._dep_check_strict and \
			not isvalidatom(x, allow_blockers=True):
			raise portage.exception.ParseError(
				"invalid atom: '%s'" % x)
		mykey = dep_getkey(x)
		if not mykey.startswith("virtual/"):
			newsplit.append(x)
			continue
		mychoices = myvirtuals.get(mykey, [])
		isblocker = x.startswith("!")
		match_atom = x
		if isblocker:
			match_atom = x[1:]
		pkgs = {}
		for cpv in portdb.match(match_atom):
			# only use new-style matches
			if cpv.startswith("virtual/"):
				pkgs[cpv] = (cpv, catpkgsplit(cpv)[1:], portdb)
		if kwargs["use_binaries"] and "vartree" in trees[myroot]:
			vardb = trees[myroot]["vartree"].dbapi
			for cpv in vardb.match(match_atom):
				# only use new-style matches
				if cpv.startswith("virtual/"):
					if cpv in pkgs:
						continue
					pkgs[cpv] = (cpv, catpkgsplit(cpv)[1:], vardb)
		if not (pkgs or mychoices):
			# This one couldn't be expanded as a new-style virtual.  Old-style
			# virtuals have already been expanded by dep_virtual, so this one
			# is unavailable and dep_zapdeps will identify it as such.  The
			# atom is not eliminated here since it may still represent a
			# dependency that needs to be satisfied.
			newsplit.append(x)
			continue
		if not pkgs and len(mychoices) == 1:
			newsplit.append(x.replace(mykey, mychoices[0]))
			continue
		pkgs = pkgs.values()
		pkgs.sort(compare_pkgs) # Prefer higher versions.
		if isblocker:
			a = []
		else:
			a = ['||']
		for y in pkgs:
			depstring = " ".join(y[2].aux_get(y[0], dep_keys))
			if edebug:
				print "Virtual Parent:   ", y[0]
				print "Virtual Depstring:", depstring
			mycheck = dep_check(depstring, mydbapi, mysettings, myroot=myroot,
				trees=trees, **kwargs)
			if not mycheck[0]:
				raise portage.exception.ParseError(
					"%s: %s '%s'" % (y[0], mycheck[1], depstring))
			if isblocker:
				virtual_atoms = [atom for atom in mycheck[1] \
					if not atom.startswith("!")]
				if len(virtual_atoms) == 1:
					# It wouldn't make sense to block all the components of a
					# compound virtual, so only a single atom block is allowed.
					a.append("!" + virtual_atoms[0])
			else:
				mycheck[1].append("="+y[0]) # pull in the new-style virtual
				a.append(mycheck[1])
		# Plain old-style virtuals.  New-style virtuals are preferred.
		for y in mychoices:
			a.append(x.replace(mykey, y))
		if isblocker and not a:
			# Probably a compound virtual.  Pass the atom through unprocessed.
			newsplit.append(x)
			continue
		newsplit.append(a)
	return newsplit

def dep_eval(deplist):
	if not deplist:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if isinstance(x, list):
				if dep_eval(x)==1:
					return 1
			elif x==1:
					return 1
		#XXX: unless there's no available atoms in the list
		#in which case we need to assume that everything is
		#okay as some ebuilds are relying on an old bug.
		if len(deplist) == 1:
			return 1
		return 0
	else:
		for x in deplist:
			if isinstance(x, list):
				if dep_eval(x)==0:
					return 0
			elif x==0 or x==2:
				return 0
		return 1

def dep_zapdeps(unreduced, reduced, myroot, use_binaries=0, trees=None):
	"""Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies."""
	if trees is None:
		global db
		trees = db
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if not reduced or unreduced == ["||"] or dep_eval(reduced):
		return []

	if unreduced[0] != "||":
		unresolved = []
		for dep, satisfied in izip(unreduced, reduced):
			if isinstance(dep, list):
				unresolved += dep_zapdeps(dep, satisfied, myroot,
					use_binaries=use_binaries, trees=trees)
			elif not satisfied:
				unresolved.append(dep)
		return unresolved

	# We're at a ( || atom ... ) type level and need to make a choice
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	# Our preference order is for an the first item that:
	# a) contains all unmasked packages with the same key as installed packages
	# b) contains all unmasked packages
	# c) contains masked installed packages
	# d) is the first item

	preferred = []
	preferred_any_slot = []
	possible_upgrades = []
	other = []

	# Alias the trees we'll be checking availability against
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	# Sort the deps into preferred (installed) and other
	# with values of [[required_atom], availablility]
	for dep, satisfied in izip(deps, satisfieds):
		if isinstance(dep, list):
			atoms = dep_zapdeps(dep, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [dep]

		if not vardb:
			# called by repoman
			other.append((atoms, None, False))
			continue

		all_available = True
		versions = {}
		for atom in atoms:
			avail_pkg = best(mydbapi.match(atom))
			if avail_pkg:
				avail_slot = "%s:%s" % (dep_getkey(atom),
					mydbapi.aux_get(avail_pkg, ["SLOT"])[0])
			elif not avail_pkg:
				has_mask = False
				if hasattr(mydbapi, "xmatch"):
					has_mask = bool(mydbapi.xmatch("match-all", atom))
				if (use_binaries or not has_mask):
					avail_pkg = best(vardb.match(atom))
					if avail_pkg:
						avail_slot = "%s:%s" % (dep_getkey(atom),
							vardb.aux_get(avail_pkg, ["SLOT"])[0])
			if not avail_pkg:
				all_available = False
				break

			versions[avail_slot] = avail_pkg

		this_choice = (atoms, versions, all_available)
		if all_available:
			# The "all installed" criterion is not version or slot specific.
			# If any version of a package is installed then we assume that it
			# is preferred over other possible packages choices.
			all_installed = True
			for atom in set([dep_getkey(atom) for atom in atoms]):
				# New-style virtuals have zero cost to install.
				if not vardb.match(atom) and not atom.startswith("virtual/"):
					all_installed = False
					break
			all_installed_slots = False
			if all_installed:
				all_installed_slots = True
				for slot_atom in versions:
					# New-style virtuals have zero cost to install.
					if not vardb.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_installed_slots = False
						break
			if all_installed:
				if all_installed_slots:
					preferred.append(this_choice)
				else:
					preferred_any_slot.append(this_choice)
			else:
				possible_upgrades.append(this_choice)
		else:
			other.append(this_choice)

	# Compare the "all_installed" choices against the "all_available" choices
	# for possible missed upgrades.  The main purpose of this code is to find
	# upgrades of new-style virtuals since _expand_new_virtuals() expands them
	# into || ( highest version ... lowest version ).  We want to prefer the
	# highest all_available version of the new-style virtual when there is a
	# lower all_installed version.
	preferred.extend(preferred_any_slot)
	preferred.extend(possible_upgrades)
	possible_upgrades = preferred[1:]
	for possible_upgrade in possible_upgrades:
		atoms, versions, all_available = possible_upgrade
		myslots = set(versions)
		for other_choice in preferred:
			if possible_upgrade is other_choice:
				# possible_upgrade will not be promoted, so move on
				break
			o_atoms, o_versions, o_all_available = other_choice
			intersecting_slots = myslots.intersection(o_versions)
			if not intersecting_slots:
				continue
			has_upgrade = False
			has_downgrade = False
			for myslot in intersecting_slots:
				myversion = versions[myslot]
				o_version = o_versions[myslot]
				if myversion != o_version:
					if myversion == best([myversion, o_version]):
						has_upgrade = True
					else:
						has_downgrade = True
						break
			if has_upgrade and not has_downgrade:
				preferred.remove(possible_upgrade)
				o_index = preferred.index(other_choice)
				preferred.insert(o_index, possible_upgrade)
				break

	# preferred now contains a) and c) from the order above with
	# the masked flag differentiating the two. other contains b)
	# and d) so adding other to preferred will give us a suitable
	# list to iterate over.
	preferred.extend(other)

	for allow_masked in (False, True):
		for atoms, versions, all_available in preferred:
			if all_available or allow_masked:
				return atoms

	assert(False) # This point should not be reachable


def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	orig_dep = mydep
	mydep = dep_getcpv(orig_dep)
	myindex = orig_dep.index(mydep)
	prefix = orig_dep[:myindex]
	postfix = orig_dep[myindex+len(mydep):]
	return prefix + cpv_expand(
		mydep, mydb=mydb, use_cache=use_cache, settings=settings) + postfix

def dep_check(depstring, mydbapi, mysettings, use="yes", mode=None, myuse=None,
	use_cache=1, use_binaries=0, myroot="/", trees=None):
	"""Takes a depend string and parses the condition."""
	edebug = mysettings.get("PORTAGE_DEBUG", None) == "1"
	#check_config_instance(mysettings)
	if trees is None:
		trees = globals()["db"]
	if use=="yes":
		if myuse is None:
			#default behavior
			myusesplit = mysettings["PORTAGE_USE"].split()
		else:
			myusesplit = myuse
			# We've been given useflags to use.
			#print "USE FLAGS PASSED IN."
			#print myuse
			#if "bindist" in myusesplit:
			#	print "BINDIST is set!"
			#else:
			#	print "BINDIST NOT set."
	else:
		#we are being run by autouse(), don't consult USE vars yet.
		# WE ALSO CANNOT USE SETTINGS
		myusesplit=[]

	#convert parenthesis to sublists
	try:
		mysplit = portage.dep.paren_reduce(depstring)
	except portage.exception.InvalidDependString, e:
		return [0, str(e)]

	mymasks = set()
	useforce = set()
	useforce.add(mysettings["ARCH"])
	if use == "all":
		# This masking/forcing is only for repoman.  In other cases, relevant
		# masking/forcing should have already been applied via
		# config.regenerate().  Also, binary or installed packages may have
		# been built with flags that are now masked, and it would be
		# inconsistent to mask them now.  Additionally, myuse may consist of
		# flags from a parent package that is being merged to a $ROOT that is
		# different from the one that mysettings represents.
		mymasks.update(mysettings.usemask)
		mymasks.update(mysettings.archlist())
		mymasks.discard(mysettings["ARCH"])
		useforce.update(mysettings.useforce)
		useforce.difference_update(mymasks)
	try:
		mysplit = portage.dep.use_reduce(mysplit, uselist=myusesplit,
			masklist=mymasks, matchall=(use=="all"), excludeall=useforce)
	except portage.exception.InvalidDependString, e:
		return [0, str(e)]

	# Do the || conversions
	mysplit=portage.dep.dep_opconvert(mysplit)

	if mysplit == []:
		#dependencies were reduced to nothing
		return [1,[]]

	# Recursively expand new-style virtuals so as to
	# collapse one or more levels of indirection.
	try:
		mysplit = _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings,
			use=use, mode=mode, myuse=myuse, use_cache=use_cache,
			use_binaries=use_binaries, myroot=myroot, trees=trees)
	except portage.exception.ParseError, e:
		return [0, str(e)]

	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0,"Invalid token"]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	myzaps = dep_zapdeps(mysplit, mysplit2, myroot,
		use_binaries=use_binaries, trees=trees)
	mylist = flatten(myzaps)
	writemsg("myzaps:   %s\n" % (myzaps), 1)
	writemsg("mylist:   %s\n" % (mylist), 1)
	#remove duplicates
	mydict={}
	for x in mylist:
		mydict[x]=1
	writemsg("mydict:   %s\n" % (mydict), 1)
	return [1,mydict.keys()]

def dep_wordreduce(mydeplist,mysettings,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	deplist=mydeplist[:]
	for mypos in xrange(len(deplist)):
		if isinstance(deplist[mypos], list):
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mysettings,mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		else:
			mykey = dep_getkey(deplist[mypos])
			if mysettings and mysettings.pprovideddict.has_key(mykey) and \
			        match_from_list(deplist[mypos], mysettings.pprovideddict[mykey]):
				deplist[mypos]=True
			elif mydbapi is None:
				# Assume nothing is satisfied.  This forces dep_zapdeps to
				# return all of deps the deps that have been selected
				# (excluding those satisfied by package.provided).
				deplist[mypos] = False
			else:
				if mode:
					x = mydbapi.xmatch(mode, deplist[mypos])
					if mode.startswith("minimum-"):
						mydep = []
						if x:
							mydep.append(x)
					else:
						mydep = x
				else:
					mydep=mydbapi.match(deplist[mypos],use_cache=use_cache)
				if mydep!=None:
					tmp=(len(mydep)>=1)
					if deplist[mypos][0]=="!":
						tmp=False
					deplist[mypos]=tmp
				else:
					#encountered invalid string
					return None
	return deplist

def cpv_getkey(mycpv):
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	mylen=len(myslash)
	if mylen==2:
		return myslash[0]+"/"+mysplit[0]
	elif mylen==1:
		return mysplit[0]
	else:
		return mysplit

def key_expand(mykey, mydb=None, use_cache=1, settings=None):
	mysplit=mykey.split("/")
	if settings is None:
		settings = globals()["settings"]
	virts = settings.getvirtuals("/")
	virts_p = settings.get_virts_p("/")
	if len(mysplit)==1:
		if hasattr(mydb, "cp_list"):
			for x in mydb.categories:
				if mydb.cp_list(x+"/"+mykey,use_cache=use_cache):
					return x+"/"+mykey
			if virts_p.has_key(mykey):
				return(virts_p[mykey][0])
		return "null/"+mykey
	elif mydb:
		if hasattr(mydb, "cp_list"):
			if (not mydb.cp_list(mykey,use_cache=use_cache)) and virts and virts.has_key(mykey):
				return virts[mykey][0]
		return mykey

def cpv_expand(mycpv, mydb=None, use_cache=1, settings=None):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	if settings is None:
		settings = globals()["settings"]
	virts = settings.getvirtuals("/")
	virts_p = settings.get_virts_p("/")
	if len(myslash)>2:
		# this is illegal case.
		mysplit=[]
		mykey=mycpv
	elif len(myslash)==2:
		if mysplit:
			mykey=myslash[0]+"/"+mysplit[0]
		else:
			mykey=mycpv
		if mydb and virts and mykey in virts:
			writemsg("mydb.__class__: %s\n" % (mydb.__class__), 1)
			if hasattr(mydb, "cp_list"):
				if not mydb.cp_list(mykey, use_cache=use_cache):
					writemsg("virts[%s]: %s\n" % (str(mykey),virts[mykey]), 1)
					mykey_orig = mykey[:]
					for vkey in virts[mykey]:
						if mydb.cp_list(vkey,use_cache=use_cache):
							mykey = vkey
							writemsg("virts chosen: %s\n" % (mykey), 1)
							break
					if mykey == mykey_orig:
						mykey=virts[mykey][0]
						writemsg("virts defaulted: %s\n" % (mykey), 1)
			#we only perform virtual expansion if we are passed a dbapi
	else:
		#specific cpv, no category, ie. "foo-1.0"
		if mysplit:
			myp=mysplit[0]
		else:
			# "foo" ?
			myp=mycpv
		mykey=None
		matches=[]
		if mydb and hasattr(mydb, "categories"):
			for x in mydb.categories:
				if mydb.cp_list(x+"/"+myp,use_cache=use_cache):
					matches.append(x+"/"+myp)
		if len(matches) > 1:
			virtual_name_collision = False
			if len(matches) == 2:
				for x in matches:
					if not x.startswith("virtual/"):
						# Assume that the non-virtual is desired.  This helps
						# avoid the ValueError for invalid deps that come from
						# installed packages (during reverse blocker detection,
						# for example).
						mykey = x
					else:
						virtual_name_collision = True
			if not virtual_name_collision:
				raise ValueError, matches
		elif matches:
			mykey=matches[0]

		if not mykey and not isinstance(mydb, list):
			if virts_p.has_key(myp):
				mykey=virts_p[myp][0]
			#again, we only perform virtual expansion if we have a dbapi (not a list)
		if not mykey:
			mykey="null/"+myp
	if mysplit:
		if mysplit[2]=="r0":
			return mykey+"-"+mysplit[1]
		else:
			return mykey+"-"+mysplit[1]+"-"+mysplit[2]
	else:
		return mykey

def getmaskingreason(mycpv, metadata=None, settings=None, portdb=None, return_location=False):
	from portage.util import grablines
	if settings is None:
		settings = globals()["settings"]
	if portdb is None:
		portdb = globals()["portdb"]
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(izip(db_keys, portdb.aux_get(mycpv, db_keys)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
	if metadata is None:
		# Can't access SLOT due to corruption.
		cpv_slot_list = [mycpv]
	else:
		cpv_slot_list = ["%s:%s" % (mycpv, metadata["SLOT"])]
	mycp=mysplit[0]+"/"+mysplit[1]

	# XXX- This is a temporary duplicate of code from the config constructor.
	locations = [os.path.join(settings["PORTDIR"], "profiles")]
	locations.extend(settings.profiles)
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(normalize_path(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH.lstrip(os.path.sep)))
	locations.reverse()
	pmasklists = [(x, grablines(os.path.join(x, "package.mask"), recursive=1)) for x in locations]

	if settings.pmaskdict.has_key(mycp):
		for x in settings.pmaskdict[mycp]:
			if match_from_list(x, cpv_slot_list):
				comment = ""
				l = "\n"
				comment_valid = -1
				for pmask in pmasklists:
					pmask_filename = os.path.join(pmask[0], "package.mask")
					for i in xrange(len(pmask[1])):
						l = pmask[1][i].strip()
						if l == "":
							comment = ""
							comment_valid = -1
						elif l[0] == "#":
							comment += (l+"\n")
							comment_valid = i + 1
						elif l == x:
							if comment_valid != i:
								comment = ""
							if return_location:
								return (comment, pmask_filename)
							else:
								return comment
						elif comment_valid != -1:
							# Apparently this comment applies to muliple masks, so
							# it remains valid until a blank line is encountered.
							comment_valid += 1
	if return_location:
		return (None, None)
	else:
		return None

def getmaskingstatus(mycpv, settings=None, portdb=None):
	if settings is None:
		settings = config(clone=globals()["settings"])
	if portdb is None:
		portdb = globals()["portdb"]

	metadata = None
	installed = False
	if not isinstance(mycpv, basestring):
		# emerge passed in a Package instance
		pkg = mycpv
		mycpv = pkg.cpv
		metadata = pkg.metadata
		installed = pkg.installed

	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(izip(db_keys, portdb.aux_get(mycpv, db_keys)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
			return ["corruption"]
		if "?" in metadata["LICENSE"]:
			settings.setcpv(p, mydb=metadata)
			metadata["USE"] = settings["PORTAGE_USE"]
		else:
			metadata["USE"] = ""
	mycp=mysplit[0]+"/"+mysplit[1]

	rValue = []

	# profile checking
	if settings.getProfileMaskAtom(mycpv, metadata):
		rValue.append("profile")

	# package.mask checking
	if settings.getMaskAtom(mycpv, metadata):
		rValue.append("package.mask")

	# keywords checking
	eapi = metadata["EAPI"]
	mygroups = metadata["KEYWORDS"]
	licenses = metadata["LICENSE"]
	slot = metadata["SLOT"]
	if eapi.startswith("-"):
		eapi = eapi[1:]
	if not eapi_is_supported(eapi):
		return ["EAPI %s" % eapi]
	egroups = settings.configdict["backupenv"].get(
		"ACCEPT_KEYWORDS", "").split()
	mygroups = mygroups.split()
	pgroups = settings["ACCEPT_KEYWORDS"].split()
	myarch = settings["ARCH"]
	if pgroups and myarch not in pgroups:
		"""For operating systems other than Linux, ARCH is not necessarily a
		valid keyword."""
		myarch = pgroups[0].lstrip("~")

	cp = dep_getkey(mycpv)
	pkgdict = settings.pkeywordsdict.get(cp)
	matches = False
	if pkgdict:
		cpv_slot_list = ["%s:%s" % (mycpv, metadata["SLOT"])]
		for atom, pkgkeywords in pkgdict.iteritems():
			if match_from_list(atom, cpv_slot_list):
				matches = True
				pgroups.extend(pkgkeywords)
	if matches or egroups:
		pgroups.extend(egroups)
		inc_pgroups = set()
		for x in pgroups:
			if x.startswith("-"):
				if x == "-*":
					inc_pgroups.clear()
				else:
					inc_pgroups.discard(x[1:])
			else:
				inc_pgroups.add(x)
		pgroups = inc_pgroups
		del inc_pgroups

	kmask = "missing"

	for keyword in pgroups:
		if keyword in mygroups:
			kmask=None

	if kmask:
		fallback = None
		for gp in mygroups:
			if gp=="*":
				kmask=None
				break
			elif gp=="-"+myarch and myarch in pgroups:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch and myarch in pgroups:
				kmask="~"+myarch
				break

	# Assume that the user doesn't want to be bothered about
	# KEYWORDS of packages that are already installed.
	if kmask and not installed:
		rValue.append(kmask+" keyword")

	try:
		missing_licenses = settings.getMissingLicenses(mycpv, metadata)
		if missing_licenses:
			allowed_tokens = set(["||", "(", ")"])
			allowed_tokens.update(missing_licenses)
			license_split = licenses.split()
			license_split = [x for x in license_split \
				if x in allowed_tokens]
			msg = license_split[:]
			msg.append("license(s)")
			rValue.append(" ".join(msg))
	except portage.exception.InvalidDependString, e:
		rValue.append("LICENSE: "+str(e))

	return rValue


auxdbkeys=[
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE',      'CDEPEND',
	'PDEPEND',   'PROVIDE', 'EAPI',
	'UNUSED_01', 'UNUSED_02', 'UNUSED_03', 'UNUSED_04',
	'UNUSED_05', 'UNUSED_06', 'UNUSED_07',
	]
auxdbkeylen=len(auxdbkeys)

from portage.dbapi import dbapi
from portage.dbapi.virtual import fakedbapi
from portage.dbapi.bintree import bindbapi, binarytree
from portage.dbapi.vartree import vardbapi, vartree, dblink
from portage.dbapi.porttree import close_portdbapi_caches, portdbapi, portagetree

class FetchlistDict(UserDict.DictMixin):
	"""This provide a mapping interface to retrieve fetch lists.  It's used
	to allow portage.manifest.Manifest to access fetch lists via a standard
	mapping interface rather than use the dbapi directly."""
	def __init__(self, pkgdir, settings, mydbapi):
		"""pkgdir is a directory containing ebuilds and settings is passed into
		portdbapi.getfetchlist for __getitem__ calls."""
		self.pkgdir = pkgdir
		self.cp = os.sep.join(pkgdir.split(os.sep)[-2:])
		self.settings = settings
		self.mytree = os.path.realpath(os.path.dirname(os.path.dirname(pkgdir)))
		self.portdb = mydbapi
	def __getitem__(self, pkg_key):
		"""Returns the complete fetch list for a given package."""
		return self.portdb.getfetchlist(pkg_key, mysettings=self.settings,
			all=True, mytree=self.mytree)[1]
	def __contains__(self):
		return pkg_key in self.keys()
	def has_key(self, pkg_key):
		"""Returns true if the given package exists within pkgdir."""
		return pkg_key in self
	def keys(self):
		"""Returns keys for all packages within pkgdir"""
		return self.portdb.cp_list(self.cp, mytree=self.mytree)

def pkgmerge(mytbz2, myroot, mysettings, mydbapi=None, vartree=None, prev_mtimes=None):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""
	global db
	if mydbapi is None:
		mydbapi = db[myroot]["bintree"].dbapi
	if vartree is None:
		vartree = db[myroot]["vartree"]
	if mytbz2[-5:]!=".tbz2":
		print "!!! Not a .tbz2 file"
		return 1

	tbz2_lock = None
	builddir_lock = None
	catdir_lock = None
	mycat = None
	mypkg = None
	did_merge_phase = False
	success = False
	try:
		""" Don't lock the tbz2 file because the filesytem could be readonly or
		shared by a cluster."""
		#tbz2_lock = portage.locks.lockfile(mytbz2, wantnewlockfile=1)

		mypkg = os.path.basename(mytbz2)[:-5]
		xptbz2 = portage.xpak.tbz2(mytbz2)
		mycat = xptbz2.getfile("CATEGORY")
		if not mycat:
			writemsg("!!! CATEGORY info missing from info chunk, aborting...\n",
				noiselevel=-1)
			return 1
		mycat = mycat.strip()

		# These are the same directories that would be used at build time.
		builddir = os.path.join(
			mysettings["PORTAGE_TMPDIR"], "portage", mycat, mypkg)
		catdir = os.path.dirname(builddir)
		pkgloc = os.path.join(builddir, "image")
		infloc = os.path.join(builddir, "build-info")
		myebuild = os.path.join(
			infloc, os.path.basename(mytbz2)[:-4] + "ebuild")
		portage.util.ensure_dirs(os.path.dirname(catdir),
			uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		catdir_lock = portage.locks.lockdir(catdir)
		portage.util.ensure_dirs(catdir,
			uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		builddir_lock = portage.locks.lockdir(builddir)
		try:
			portage.locks.unlockdir(catdir_lock)
		finally:
			catdir_lock = None
		try:
			shutil.rmtree(builddir)
		except (IOError, OSError), e:
			if e.errno != errno.ENOENT:
				raise
			del e
		for mydir in (builddir, pkgloc, infloc):
			portage.util.ensure_dirs(mydir, uid=portage_uid,
				gid=portage_gid, mode=0755)
		writemsg_stdout(">>> Extracting info\n")
		xptbz2.unpackinfo(infloc)
		mysettings.setcpv(mycat + "/" + mypkg, mydb=mydbapi)
		# Store the md5sum in the vdb.
		fp = open(os.path.join(infloc, "BINPKGMD5"), "w")
		fp.write(str(portage.checksum.perform_md5(mytbz2))+"\n")
		fp.close()

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		mysettings["PORTAGE_BINPKG_FILE"] = mytbz2
		mysettings.backup_changes("PORTAGE_BINPKG_FILE")
		debug = mysettings.get("PORTAGE_DEBUG", "") == "1"

		# Eventually we'd like to pass in the saved ebuild env here.
		retval = doebuild(myebuild, "setup", myroot, mysettings, debug=debug,
			tree="bintree", mydbapi=mydbapi, vartree=vartree)
		if retval != os.EX_OK:
			writemsg("!!! Setup failed: %s\n" % retval, noiselevel=-1)
			return retval

		writemsg_stdout(">>> Extracting %s\n" % mypkg)
		retval = portage.process.spawn_bash(
			"bzip2 -dqc -- '%s' | tar -xp -C '%s' -f -" % (mytbz2, pkgloc),
			env=mysettings.environ())
		if retval != os.EX_OK:
			writemsg("!!! Error Extracting '%s'\n" % mytbz2, noiselevel=-1)
			return retval
		#portage.locks.unlockfile(tbz2_lock)
		#tbz2_lock = None

		mylink = dblink(mycat, mypkg, myroot, mysettings, vartree=vartree,
			treetype="bintree")
		retval = mylink.merge(pkgloc, infloc, myroot, myebuild, cleanup=0,
			mydbapi=mydbapi, prev_mtimes=prev_mtimes)
		did_merge_phase = True
		success = retval == os.EX_OK
		return retval
	finally:
		mysettings.pop("PORTAGE_BINPKG_FILE", None)
		if tbz2_lock:
			portage.locks.unlockfile(tbz2_lock)
		if builddir_lock:
			if not did_merge_phase:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				from portage.elog import elog_process
				elog_process(mycat + "/" + mypkg, mysettings)
			try:
				if success:
					shutil.rmtree(builddir)
			except (IOError, OSError), e:
				if e.errno != errno.ENOENT:
					raise
				del e
			portage.locks.unlockdir(builddir_lock)
			try:
				if not catdir_lock:
					# Lock catdir for removal if empty.
					catdir_lock = portage.locks.lockdir(catdir)
			finally:
				if catdir_lock:
					try:
						os.rmdir(catdir)
					except OSError, e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					portage.locks.unlockdir(catdir_lock)

def deprecated_profile_check():
	if not os.access(DEPRECATED_PROFILE_FILE, os.R_OK):
		return False
	deprecatedfile = open(DEPRECATED_PROFILE_FILE, "r")
	dcontent = deprecatedfile.readlines()
	deprecatedfile.close()
	newprofile = dcontent[0]
	writemsg(red("\n!!! Your current profile is deprecated and not supported anymore.\n"),
		noiselevel=-1)
	writemsg(red("!!! Please upgrade to the following profile if possible:\n"),
		noiselevel=-1)
	writemsg(8*" "+green(newprofile)+"\n", noiselevel=-1)
	if len(dcontent) > 1:
		writemsg("To upgrade do the following steps:\n", noiselevel=-1)
		for myline in dcontent[1:]:
			writemsg(myline, noiselevel=-1)
		writemsg("\n\n", noiselevel=-1)
	return True

# gets virtual package settings
def getvirtuals(myroot):
	global settings
	writemsg("--- DEPRECATED call to getvirtual\n")
	return settings.getvirtuals(myroot)

def commit_mtimedb(mydict=None, filename=None):
	if mydict is None:
		global mtimedb
		if "mtimedb" not in globals() or mtimedb is None:
			return
		mtimedb.commit()
		return
	if filename is None:
		global mtimedbfile
		filename = mtimedbfile
	mydict["version"] = VERSION
	d = {} # for full backward compat, pickle it as a plain dict object.
	d.update(mydict)
	try:
		f = atomic_ofstream(filename)
		cPickle.dump(d, f, -1)
		f.close()
		portage.util.apply_secpass_permissions(filename, uid=uid, gid=portage_gid, mode=0664)
	except (IOError, OSError), e:
		pass

def portageexit():
	global uid,portage_gid,portdb,db
	if secpass and not os.environ.has_key("SANDBOX_ACTIVE"):
		close_portdbapi_caches()
		commit_mtimedb()

atexit_register(portageexit)

def _global_updates(trees, prev_mtimes):
	"""
	Perform new global updates if they exist in $PORTDIR/profiles/updates/.

	@param trees: A dictionary containing portage trees.
	@type trees: dict
	@param prev_mtimes: A dictionary containing mtimes of files located in
		$PORTDIR/profiles/updates/.
	@type prev_mtimes: dict
	@rtype: None or List
	@return: None if no were no updates, otherwise a list of update commands
		that have been performed.
	"""
	# only do this if we're root and not running repoman/ebuild digest
	global secpass
	if secpass < 2 or "SANDBOX_ACTIVE" in os.environ:
		return
	mysettings = trees["/"]["vartree"].settings
	updpath = os.path.join(mysettings["PORTDIR"], "profiles", "updates")

	try:
		if mysettings["PORTAGE_CALLER"] == "fixpackages":
			update_data = grab_updates(updpath)
		else:
			update_data = grab_updates(updpath, prev_mtimes)
	except portage.exception.DirectoryNotFound:
		writemsg("--- 'profiles/updates' is empty or " + \
			"not available. Empty portage tree?\n", noiselevel=1)
		return
	myupd = None
	if len(update_data) > 0:
		do_upgrade_packagesmessage = 0
		myupd = []
		timestamps = {}
		for mykey, mystat, mycontent in update_data:
			writemsg_stdout("\n\n")
			writemsg_stdout(green("Performing Global Updates: ")+bold(mykey)+"\n")
			writemsg_stdout("(Could take a couple of minutes if you have a lot of binary packages.)\n")
			writemsg_stdout("  "+bold(".")+"='update pass'  "+bold("*")+"='binary update'  "+bold("@")+"='/var/db move'\n"+"  "+bold("s")+"='/var/db SLOT move' "+bold("S")+"='binary SLOT move' "+bold("p")+"='update /etc/portage/package.*'\n")
			valid_updates, errors = parse_updates(mycontent)
			myupd.extend(valid_updates)
			writemsg_stdout(len(valid_updates) * "." + "\n")
			if len(errors) == 0:
				# Update our internal mtime since we
				# processed all of our directives.
				timestamps[mykey] = long(mystat.st_mtime)
			else:
				for msg in errors:
					writemsg("%s\n" % msg, noiselevel=-1)

		update_config_files("/",
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split(),
			myupd)

		trees["/"]["bintree"] = binarytree("/", mysettings["PKGDIR"],
			settings=mysettings)
		vardb = trees["/"]["vartree"].dbapi
		bindb = trees["/"]["bintree"].dbapi
		if not os.access(bindb.bintree.pkgdir, os.W_OK):
			bindb = None
		for update_cmd in myupd:
			if update_cmd[0] == "move":
				moves = vardb.move_ent(update_cmd)
				if moves:
					writemsg_stdout(moves * "@")
				if bindb:
					moves = bindb.move_ent(update_cmd)
					if moves:
						writemsg_stdout(moves * "%")
			elif update_cmd[0] == "slotmove":
				moves = vardb.move_slot_ent(update_cmd)
				if moves:
					writemsg_stdout(moves * "s")
				if bindb:
					moves = bindb.move_slot_ent(update_cmd)
					if moves:
						writemsg_stdout(moves * "S")

		# The above global updates proceed quickly, so they
		# are considered a single mtimedb transaction.
		if len(timestamps) > 0:
			# We do not update the mtime in the mtimedb
			# until after _all_ of the above updates have
			# been processed because the mtimedb will
			# automatically commit when killed by ctrl C.
			for mykey, mtime in timestamps.iteritems():
				prev_mtimes[mykey] = mtime

		# We gotta do the brute force updates for these now.
		if mysettings["PORTAGE_CALLER"] == "fixpackages" or \
		"fixpackages" in mysettings.features:
			def onProgress(maxval, curval):
				writemsg_stdout("*")
			vardb.update_ents(myupd, onProgress=onProgress)
			if bindb:
				bindb.update_ents(myupd, onProgress=onProgress)
		else:
			do_upgrade_packagesmessage = 1

		# Update progress above is indicated by characters written to stdout so
		# we print a couple new lines here to separate the progress output from
		# what follows.
		print
		print

		if do_upgrade_packagesmessage and bindb and \
			bindb.cpv_all():
			writemsg_stdout(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the")
			writemsg_stdout("\n    tbz2's in the packages directory. "+bold("Note: This can take a very long time."))
			writemsg_stdout("\n")
	if myupd:
		return myupd

#continue setting up other trees

class MtimeDB(dict):
	def __init__(self, filename):
		dict.__init__(self)
		self.filename = filename
		self._load(filename)

	def _load(self, filename):
		try:
			f = open(filename)
			mypickle = cPickle.Unpickler(f)
			mypickle.find_global = None
			d = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, cPickle.UnpicklingError):
			d = {}

		if "old" in d:
			d["updates"] = d["old"]
			del d["old"]
		if "cur" in d:
			del d["cur"]

		d.setdefault("starttime", 0)
		d.setdefault("version", "")
		for k in ("info", "ldpath", "updates"):
			d.setdefault(k, {})

		mtimedbkeys = set(("info", "ldpath", "resume", "resume_backup",
			"starttime", "updates", "version"))

		for k in d.keys():
			if k not in mtimedbkeys:
				writemsg("Deleting invalid mtimedb key: %s\n" % str(k))
				del d[k]
		self.update(d)
		self._clean_data = copy.deepcopy(d)

	def commit(self):
		if not self.filename:
			return
		d = {}
		d.update(self)
		# Only commit if the internal state has changed.
		if d != self._clean_data:
			commit_mtimedb(mydict=d, filename=self.filename)
			self._clean_data = copy.deepcopy(d)

def create_trees(config_root=None, target_root=None, trees=None):
	if trees is None:
		trees = {}
	else:
		# clean up any existing portdbapi instances
		for myroot in trees:
			portdb = trees[myroot]["porttree"].dbapi
			portdb.close_caches()
			portdbapi.portdbapi_instances.remove(portdb)
			del trees[myroot]["porttree"], myroot, portdb

	settings = config(config_root=config_root, target_root=target_root,
		config_incrementals=portage.const.INCREMENTALS)
	settings.lock()

	myroots = [(settings["ROOT"], settings)]
	if settings["ROOT"] != "/":
		settings = config(config_root=None, target_root=None,
			config_incrementals=portage.const.INCREMENTALS)
		# When ROOT != "/" we only want overrides from the calling
		# environment to apply to the config that's associated
		# with ROOT != "/", so we wipe out the "backupenv" for the
		# config that is associated with ROOT == "/" and regenerate
		# it's incrementals.
		# Preserve backupenv values that are initialized in the config
		# constructor. Also, preserve XARGS since it is set by the
		# portage.data module.

		backupenv_whitelist = settings._environ_whitelist
		backupenv = settings.configdict["backupenv"]
		env_d = settings.configdict["env.d"]
		for k, v in os.environ.iteritems():
			if k in backupenv_whitelist:
				continue
			if k in env_d or \
				v == backupenv.get(k):
				backupenv.pop(k, None)
		settings.regenerate()
		settings.lock()
		myroots.append((settings["ROOT"], settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, None))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals, myroot)
		trees[myroot].addLazySingleton(
			"vartree", vartree, myroot, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, myroot, settings=mysettings)
		trees[myroot].addLazySingleton("bintree",
			binarytree, myroot, mysettings["PKGDIR"], settings=mysettings)
	return trees

# Initialization of legacy globals.  No functions/classes below this point
# please!  When the above functions and classes become independent of the
# below global variables, it will be possible to make the below code
# conditional on a backward compatibility flag (backward compatibility could
# be disabled via an environment variable, for example).  This will enable new
# code that is aware of this flag to import portage without the unnecessary
# overhead (and other issues!) of initializing the legacy globals.

def init_legacy_globals():
	global db, settings, root, portdb, selinux_enabled, mtimedbfile, mtimedb, \
	archlist, features, groups, pkglines, thirdpartymirrors, usedefaults, \
	profiledir, flushmtimedb

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(022)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, "/")

	global _initializing_globals
	_initializing_globals = True
	db = create_trees(**kwargs)
	del _initializing_globals

	settings = db["/"]["vartree"].settings
	portdb = db["/"]["porttree"].dbapi

	for myroot in db:
		if myroot != "/":
			settings = db[myroot]["vartree"].settings
			portdb = db[myroot]["porttree"].dbapi
			break

	root = settings["ROOT"]

	mtimedbfile = os.path.join("/", CACHE_PATH.lstrip(os.path.sep), "mtimedb")
	mtimedb = MtimeDB(mtimedbfile)

	# ========================================================================
	# COMPATIBILITY
	# These attributes should not be used
	# within Portage under any circumstances.
	# ========================================================================
	archlist    = settings.archlist()
	features    = settings.features
	groups      = settings["ACCEPT_KEYWORDS"].split()
	pkglines    = settings.packages
	selinux_enabled   = settings.selinux_enabled()
	thirdpartymirrors = settings.thirdpartymirrors()
	usedefaults       = settings.use_defs
	profiledir  = None
	if os.path.isdir(PROFILE_PATH):
		profiledir = PROFILE_PATH
	def flushmtimedb(record):
		writemsg("portage.flushmtimedb() is DEPRECATED\n")
	# ========================================================================
	# COMPATIBILITY
	# These attributes should not be used
	# within Portage under any circumstances.
	# ========================================================================

# WARNING!
# The PORTAGE_LEGACY_GLOBALS environment variable is reserved for internal
# use within Portage.  External use of this variable is unsupported because
# it is experimental and it's behavior is likely to change.
if "PORTAGE_LEGACY_GLOBALS" not in os.environ:
	init_legacy_globals()

# Clear the cache
dircache={}

# ============================================================================
# ============================================================================

