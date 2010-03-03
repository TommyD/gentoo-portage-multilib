# portage.py -- core Portage functionality
# Copyright 1998-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

VERSION="$Rev$"[6:-2] + "-svn"

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

try:
	import sys
	import codecs
	import errno
	if not hasattr(errno, 'ESTALE'):
		# ESTALE may not be defined on some systems, such as interix.
		errno.ESTALE = -1
	import re
	import types
	try:
		import cPickle as pickle
	except ImportError:
		import pickle

	try:
		from subprocess import getstatusoutput as subprocess_getstatusoutput
	except ImportError:
		from commands import getstatusoutput as subprocess_getstatusoutput

	try:
		from io import StringIO
	except ImportError:
		# Needed for python-2.6 with USE=build since
		# io imports threading which imports thread
		# which is unavailable.
		from StringIO import StringIO

	import platform

	# Temporarily delete these imports, to ensure that only the
	# wrapped versions are imported by portage internals.
	import os
	del os
	import shutil
	del shutil

except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. These are internal modules for\n")
	sys.stderr.write("!!! python and failure here indicates that you have a problem with python\n")
	sys.stderr.write("!!! itself and thus portage is not able to continue processing.\n\n")

	sys.stderr.write("!!! You might consider starting python with verbose flags to see what has\n")
	sys.stderr.write("!!! gone wrong. Here is the information we got for this exception:\n")
	sys.stderr.write("    "+str(e)+"\n\n");
	raise

try:

	try:
		from collections import OrderedDict
	except ImportError:
		from portage.cache.mappings import OrderedDict

	from portage.cache.cache_errors import CacheError
	import portage.proxy.lazyimport
	import portage.proxy as proxy
	proxy.lazyimport.lazyimport(globals(),
		'portage.checksum',
		'portage.checksum:perform_checksum,perform_md5,prelink_capable',
		'portage.cvstree',
		'portage.data',
		'portage.data:lchown,ostype,portage_gid,portage_uid,secpass,' + \
			'uid,userland,userpriv_groups,wheelgid',
		'portage.dbapi',
		'portage.dbapi.bintree:bindbapi,binarytree',
		'portage.dbapi.cpv_expand:cpv_expand',
		'portage.dbapi.dep_expand:dep_expand',
		'portage.dbapi.porttree:close_portdbapi_caches,FetchlistDict,' + \
			'portagetree,portdbapi',
		'portage.dbapi.vartree:dblink,merge,unmerge,vardbapi,vartree',
		'portage.dbapi.virtual:fakedbapi',
		'portage.dep',
		'portage.dep:best_match_to_list,dep_getcpv,dep_getkey,' + \
			'flatten,get_operator,isjustname,isspecific,isvalidatom,' + \
			'match_from_list,match_to_list',
		'portage.dep.dep_check:dep_check,dep_eval,dep_wordreduce,dep_zapdeps',
		'portage.eclass_cache',
		'portage.env.loaders',
		'portage.exception',
		'portage.getbinpkg',
		'portage.locks',
		'portage.locks:lockdir,lockfile,unlockdir,unlockfile',
		'portage.mail',
		'portage.manifest:Manifest',
		'portage.output',
		'portage.output:bold,colorize',
		'portage.package.ebuild.doebuild:doebuild,' + \
			'doebuild_environment,spawn,spawnebuild',
		'portage.package.ebuild.config:autouse,best_from_dict,' + \
			'check_config_instance,config',
		'portage.package.ebuild.deprecated_profile_check:' + \
			'deprecated_profile_check',
		'portage.package.ebuild.digestcheck:digestcheck',
		'portage.package.ebuild.digestgen:digestgen',
		'portage.package.ebuild.fetch:fetch',
		'portage.package.ebuild.getmaskingreason:getmaskingreason',
		'portage.package.ebuild.getmaskingstatus:getmaskingstatus',
		'portage.package.ebuild.prepare_build_dirs:prepare_build_dirs',
		'portage.process',
		'portage.process:atexit_register,run_exitfuncs',
		'portage.update:dep_transform,fixdbentries,grab_updates,' + \
			'parse_updates,update_config_files,update_dbentries,' + \
			'update_dbentry',
		'portage.util',
		'portage.util:atomic_ofstream,apply_secpass_permissions,' + \
			'apply_recursive_permissions,dump_traceback,getconfig,' + \
			'grabdict,grabdict_package,grabfile,grabfile_package,' + \
			'map_dictlist_vals,new_protect_filename,normalize_path,' + \
			'pickle_read,pickle_write,stack_dictlist,stack_dicts,' + \
			'stack_lists,unique_array,varexpand,writedict,writemsg,' + \
			'writemsg_stdout,write_atomic',
		'portage.util.digraph:digraph',
		'portage.util.env_update:env_update',
		'portage.util.ExtractKernelVersion:ExtractKernelVersion',
		'portage.util.listdir:cacheddir,listdir',
		'portage.util.movefile:movefile',
		'portage.util.mtimedb:MtimeDB',
		'portage.versions',
		'portage.versions:best,catpkgsplit,catsplit,cpv_getkey,' + \
			'cpv_getkey@getCPFromCPV,endversion_keys,' + \
			'suffix_value@endversion,pkgcmp,pkgsplit,vercmp,ververify',
		'portage.xpak',
		'portage._deprecated:commit_mtimedb,dep_virtual,' + \
			'digestParseFile,getvirtuals,pkgmerge',
	)

	import portage.const
	from portage.const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
		USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
		PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
		EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
		MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
		DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
		INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
		INCREMENTALS, EAPI, MISC_SH_BINARY, REPO_NAME_LOC, REPO_NAME_FILE

except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the\n")
	sys.stderr.write("!!! portage tree under '/usr/portage/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int

# Assume utf_8 fs encoding everywhere except in merge code, where the
# user's locale is respected.
_encodings = {
	'content'                : 'utf_8',
	'fs'                     : 'utf_8',
	'merge'                  : sys.getfilesystemencoding(),
	'repo.content'           : 'utf_8',
	'stdio'                  : 'utf_8',
}

# This can happen if python is built with USE=build (stage 1).
if _encodings['merge'] is None:
	_encodings['merge'] = 'ascii'

if sys.hexversion >= 0x3000000:
	def _unicode_encode(s, encoding=_encodings['content'], errors='backslashreplace'):
		if isinstance(s, str):
			s = s.encode(encoding, errors)
		return s

	def _unicode_decode(s, encoding=_encodings['content'], errors='replace'):
		if isinstance(s, bytes):
			s = str(s, encoding=encoding, errors=errors)
		return s
else:
	def _unicode_encode(s, encoding=_encodings['content'], errors='backslashreplace'):
		if isinstance(s, unicode):
			s = s.encode(encoding, errors)
		return s

	def _unicode_decode(s, encoding=_encodings['content'], errors='replace'):
		if isinstance(s, bytes):
			s = unicode(s, encoding=encoding, errors=errors)
		return s

class _unicode_func_wrapper(object):
	"""
	Wraps a function, converts arguments from unicode to bytes,
	and return values to unicode from bytes. Function calls
	will raise UnicodeEncodeError if an argument fails to be
	encoded with the required encoding. Return values that
	are single strings are decoded with errors='replace'. Return 
	values that are lists of strings are decoded with errors='strict'
	and elements that fail to be decoded are omitted from the returned
	list.
	"""
	__slots__ = ('_func', '_encoding')

	def __init__(self, func, encoding=_encodings['fs']):
		self._func = func
		self._encoding = encoding

	def __call__(self, *args, **kwargs):

		encoding = self._encoding
		wrapped_args = [_unicode_encode(x, encoding=encoding, errors='strict')
			for x in args]
		if kwargs:
			wrapped_kwargs = dict(
				(k, _unicode_encode(v, encoding=encoding, errors='strict'))
				for k, v in kwargs.items())
		else:
			wrapped_kwargs = {}

		rval = self._func(*wrapped_args, **wrapped_kwargs)

		if isinstance(rval, (list, tuple)):
			decoded_rval = []
			for x in rval:
				try:
					x = _unicode_decode(x, encoding=encoding, errors='strict')
				except UnicodeDecodeError:
					pass
				else:
					decoded_rval.append(x)

			if isinstance(rval, tuple):
				rval = tuple(decoded_rval)
			else:
				rval = decoded_rval
		else:
			rval = _unicode_decode(rval, encoding=encoding, errors='replace')

		return rval

class _unicode_module_wrapper(object):
	"""
	Wraps a module and wraps all functions with _unicode_func_wrapper.
	"""
	__slots__ = ('_mod', '_encoding', '_overrides', '_cache')

	def __init__(self, mod, encoding=_encodings['fs'], overrides=None, cache=True):
		object.__setattr__(self, '_mod', mod)
		object.__setattr__(self, '_encoding', encoding)
		object.__setattr__(self, '_overrides', overrides)
		if cache:
			cache = {}
		else:
			cache = None
		object.__setattr__(self, '_cache', cache)

	def __getattribute__(self, attr):
		cache = object.__getattribute__(self, '_cache')
		if cache is not None:
			result = cache.get(attr)
			if result is not None:
				return result
		result = getattr(object.__getattribute__(self, '_mod'), attr)
		encoding = object.__getattribute__(self, '_encoding')
		overrides = object.__getattribute__(self, '_overrides')
		override = None
		if overrides is not None:
			override = overrides.get(id(result))
		if override is not None:
			result = override
		elif isinstance(result, type):
			pass
		elif type(result) is types.ModuleType:
			result = _unicode_module_wrapper(result,
				encoding=encoding, overrides=overrides)
		elif hasattr(result, '__call__'):
			result = _unicode_func_wrapper(result, encoding=encoding)
		if cache is not None:
			cache[attr] = result
		return result

import os as _os
_os_overrides = {
	id(_os.fdopen)        : _os.fdopen,
	id(_os.popen)         : _os.popen,
	id(_os.read)          : _os.read,
	id(_os.system)        : _os.system,
}

if hasattr(_os, 'statvfs'):
	_os_overrides[id(_os.statvfs)] = _os.statvfs

os = _unicode_module_wrapper(_os, overrides=_os_overrides,
	encoding=_encodings['fs'])
_os_merge = _unicode_module_wrapper(_os,
	encoding=_encodings['merge'], overrides=_os_overrides)

import shutil as _shutil
shutil = _unicode_module_wrapper(_shutil, encoding=_encodings['fs'])

# Imports below this point rely on the above unicode wrapper definitions.
try:
	import portage._selinux
	selinux = _unicode_module_wrapper(_selinux,
		encoding=_encodings['fs'])
	_selinux_merge = _unicode_module_wrapper(_selinux,
		encoding=_encodings['merge'])
except (ImportError, OSError) as e:
	if isinstance(e, OSError):
		sys.stderr.write("!!! SELinux not loaded: %s\n" % str(e))
	del e
	_selinux = None
	selinux = None
	_selinux_merge = None

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================

def _ensure_default_encoding():

	default_encoding = sys.getdefaultencoding().lower().replace('-', '_')
	filesystem_encoding = _encodings['merge'].lower().replace('-', '_')
	required_encodings = set(['ascii', 'utf_8'])
	required_encodings.add(default_encoding)
	required_encodings.add(filesystem_encoding)
	missing_encodings = set()
	for codec_name in required_encodings:
		try:
			codecs.lookup(codec_name)
		except LookupError:
			missing_encodings.add(codec_name)

	if not missing_encodings:
		return

	from portage import _ensure_encodings
	_ensure_encodings._setup_encodings(default_encoding,
		filesystem_encoding, missing_encodings)

# Do this ASAP since writemsg() might not work without it.
_ensure_default_encoding()

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

bsd_chflags = None

if platform.system() in ('FreeBSD',):

	class bsd_chflags(object):

		@classmethod
		def chflags(cls, path, flags, opts=""):
			cmd = 'chflags %s %o %s' % (opts, flags, _shell_quote(path))
			status, output = subprocess_getstatusoutput(cmd)
			if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
				return
			# Try to generate an ENOENT error if appropriate.
			if 'h' in opts:
				_os_merge.lstat(path)
			else:
				_os_merge.stat(path)
			# Make sure the binary exists.
			if not portage.process.find_binary('chflags'):
				raise portage.exception.CommandNotFound('chflags')
			# Now we're not sure exactly why it failed or what
			# the real errno was, so just report EPERM.
			e = OSError(errno.EPERM, output)
			e.errno = errno.EPERM
			e.filename = path
			e.message = output
			raise e

		@classmethod
		def lchflags(cls, path, flags):
			return cls.chflags(path, flags, opts='-h')

def load_mod(name):
	modname = ".".join(name.split(".")[:-1])
	mod = __import__(modname)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

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

_doebuild_manifest_exempt_depend = 0

_testing_eapis = frozenset()
_deprecated_eapis = frozenset(["3_pre2", "3_pre1", "2_pre3", "2_pre2", "2_pre1"])

def _eapi_is_deprecated(eapi):
	return eapi in _deprecated_eapis

def eapi_is_supported(eapi):
	if not isinstance(eapi, basestring):
		# Only call str() when necessary since with python2 it
		# can trigger UnicodeEncodeError if EAPI is corrupt.
		eapi = str(eapi)
	eapi = eapi.strip()

	if _eapi_is_deprecated(eapi):
		return True

	if eapi in _testing_eapis:
		return True

	try:
		eapi = int(eapi)
	except ValueError:
		eapi = -1
	if eapi < 0:
		return False
	return eapi <= portage.const.EAPI

# Generally, it's best not to assume that cache entries for unsupported EAPIs
# can be validated. However, the current package manager specification does not
# guarantee that the EAPI can be parsed without sourcing the ebuild, so
# it's too costly to discard existing cache entries for unsupported EAPIs.
# Therefore, by default, assume that cache entries for unsupported EAPIs can be
# validated. If FEATURES=parse-eapi-* is enabled, this assumption is discarded
# since the EAPI can be determined without the incurring the cost of sourcing
# the ebuild.
_validate_cache_for_unsupported_eapis = True

_parse_eapi_ebuild_head_re = re.compile(r'^EAPI=[\'"]?([^\'"#]*)')
_parse_eapi_ebuild_head_max_lines = 30

def _parse_eapi_ebuild_head(f):
	count = 0
	for line in f:
		m = _parse_eapi_ebuild_head_re.match(line)
		if m is not None:
			return m.group(1).strip()
		count += 1
		if count >= _parse_eapi_ebuild_head_max_lines:
			break
	return '0'

# True when FEATURES=parse-eapi-glep-55 is enabled.
_glep_55_enabled = False

_split_ebuild_name_glep55_re = re.compile(r'^(.*)\.ebuild(-([^.]+))?$')

def _split_ebuild_name_glep55(name):
	"""
	@returns: (pkg-ver-rev, eapi)
	"""
	m = _split_ebuild_name_glep55_re.match(name)
	if m is None:
		return (None, None)
	return (m.group(1), m.group(3))

def _movefile(src, dest, **kwargs):
	"""Calls movefile and raises a PortageException if an error occurs."""
	if movefile(src, dest, **kwargs) is None:
		raise portage.exception.PortageException(
			"mv '%s' '%s'" % (src, dest))

auxdbkeys = (
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE', 'UNUSED_00',
	'PDEPEND',   'PROVIDE', 'EAPI',
	'PROPERTIES', 'DEFINED_PHASES', 'UNUSED_05', 'UNUSED_04',
	'UNUSED_03', 'UNUSED_02', 'UNUSED_01',
)
auxdbkeylen=len(auxdbkeys)

def portageexit():
	if data.secpass > 1 and os.environ.get("SANDBOX_ON") != "1":
		close_portdbapi_caches()
		try:
			mtimedb
		except NameError:
			pass
		else:
			mtimedb.commit()

atexit_register(portageexit)

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

		# When ROOT != "/" we only want overrides from the calling
		# environment to apply to the config that's associated
		# with ROOT != "/", so pass a nearly empty dict for the env parameter.
		clean_env = {}
		for k in ('PATH', 'TERM'):
			v = settings.get(k)
			if v is not None:
				clean_env[k] = v
		settings = config(config_root=None, target_root="/", env=clean_env)
		settings.lock()
		myroots.append((settings["ROOT"], settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, {}))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals, myroot)
		trees[myroot].addLazySingleton(
			"vartree", vartree, myroot, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, myroot, settings=mysettings)
		trees[myroot].addLazySingleton("bintree",
			binarytree, myroot, mysettings["PKGDIR"], settings=mysettings)
	return trees

class _LegacyGlobalProxy(proxy.objectproxy.ObjectProxy):

	__slots__ = ('_name',)

	def __init__(self, name):
		proxy.objectproxy.ObjectProxy.__init__(self)
		object.__setattr__(self, '_name', name)

	def _get_target(self):
		name = object.__getattribute__(self, '_name')
		from portage._legacy_globals import _get_legacy_global
		return _get_legacy_global(name)

_legacy_global_var_names = ("archlist", "db", "features",
	"groups", "mtimedb", "mtimedbfile", "pkglines",
	"portdb", "profiledir", "root", "selinux_enabled",
	"settings", "thirdpartymirrors", "usedefaults")

for k in _legacy_global_var_names:
	globals()[k] = _LegacyGlobalProxy(k)
del k

_legacy_globals_constructed = set()

def _disable_legacy_globals():
	"""
	This deletes the ObjectProxy instances that are used
	for lazy initialization of legacy global variables.
	The purpose of deleting them is to prevent new code
	from referencing these deprecated variables.
	"""
	global _legacy_global_var_names
	for k in _legacy_global_var_names:
		globals().pop(k, None)
