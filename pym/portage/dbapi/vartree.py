# Copyright 1998-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ["PreservedLibsRegistry", "LinkageMap",
	"vardbapi", "vartree", "dblink"] + \
	["write_contents", "tar_contents"]

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.checksum:_perform_md5_merge@perform_md5',
	'portage.dbapi.dep_expand:dep_expand',
	'portage.dep:dep_getkey,isjustname,flatten,match_from_list,' + \
	 	'use_reduce,paren_reduce,_slot_re',
	'portage.elog:elog_process',
	'portage.locks:lockdir,unlockdir',
	'portage.output:bold,colorize',
	'portage.package.ebuild.doebuild:doebuild,doebuild_environment,' + \
	 	'_spawn_misc_sh',
	'portage.package.ebuild.prepare_build_dirs:prepare_build_dirs',
	'portage.update:fixdbentries',
	'portage.util:apply_secpass_permissions,ConfigProtect,ensure_dirs,' + \
		'writemsg,writemsg_level,write_atomic,atomic_ofstream,writedict,' + \
		'grabfile,grabdict,normalize_path,new_protect_filename,getlibpaths',
	'portage.util.digraph:digraph',
	'portage.util.env_update:env_update',
	'portage.util.listdir:dircache,listdir',
	'portage.versions:best,catpkgsplit,catsplit,cpv_getkey,pkgcmp,' + \
		'_pkgsplit@pkgsplit',
)

from portage.const import CACHE_PATH, CONFIG_MEMORY_FILE, \
	PORTAGE_PACKAGE_ATOM, PRIVATE_PATH, VDB_PATH
from portage.data import portage_gid, portage_uid, secpass
from portage.dbapi import dbapi
from portage.exception import CommandNotFound, \
	InvalidData, InvalidPackageName, \
	FileNotFound, PermissionDenied, UnsupportedAPIException
from portage.localization import _
from portage.util.movefile import movefile

from portage import abssymlink, _movefile, bsd_chflags

# This is a special version of the os module, wrapped for unicode support.
from portage import os
from portage import _encodings
from portage import _os_merge
from portage import _selinux_merge
from portage import _unicode_decode
from portage import _unicode_encode

from portage.cache.mappings import slot_dict_class

import codecs
from collections import deque
import re, shutil, stat, errno, copy, subprocess
import logging
import os as _os
import stat
import sys
import tempfile
import time
import warnings

try:
	import cPickle as pickle
except ImportError:
	import pickle

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int

class PreservedLibsRegistry(object):
	""" This class handles the tracking of preserved library objects """
	def __init__(self, root, filename, autocommit=True):
		""" 
			@param root: root used to check existence of paths in pruneNonExisting
		    @type root: String
			@param filename: absolute path for saving the preserved libs records
		    @type filename: String
			@param autocommit: determines if the file is written after every update
			@type autocommit: Boolean
		"""
		self._root = root
		self._filename = filename
		self._autocommit = autocommit
		self.load()
		self.pruneNonExisting()

	def load(self):
		""" Reload the registry data from file """
		self._data = None
		try:
			self._data = pickle.load(
				open(_unicode_encode(self._filename,
					encoding=_encodings['fs'], errors='strict'), 'rb'))
		except (ValueError, pickle.UnpicklingError) as e:
			writemsg_level(_("!!! Error loading '%s': %s\n") % \
				(self._filename, e), level=logging.ERROR, noiselevel=-1)
		except (EOFError, IOError) as e:
			if isinstance(e, EOFError) or e.errno == errno.ENOENT:
				pass
			elif e.errno == PermissionDenied.errno:
				raise PermissionDenied(self._filename)
			else:
				raise
		if self._data is None:
			self._data = {}
		self._data_orig = self._data.copy()
	def store(self):
		""" Store the registry data to file. No need to call this if autocommit
		    was enabled.
		"""
		if os.environ.get("SANDBOX_ON") == "1" or \
			self._data == self._data_orig:
			return
		try:
			f = atomic_ofstream(self._filename, 'wb')
			pickle.dump(self._data, f, protocol=2)
			f.close()
		except EnvironmentError as e:
			if e.errno != PermissionDenied.errno:
				writemsg("!!! %s %s\n" % (e, self._filename), noiselevel=-1)
		else:
			self._data_orig = self._data.copy()

	def register(self, cpv, slot, counter, paths):
		""" Register new objects in the registry. If there is a record with the
			same packagename (internally derived from cpv) and slot it is 
			overwritten with the new data.
			@param cpv: package instance that owns the objects
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
			@param counter: vdb counter value for the package instace
			@type counter: Integer
			@param paths: absolute paths of objects that got preserved during an update
			@type paths: List
		"""
		cp = "/".join(catpkgsplit(cpv)[:2])
		cps = cp+":"+slot
		if len(paths) == 0 and cps in self._data \
				and self._data[cps][0] == cpv and int(self._data[cps][1]) == int(counter):
			del self._data[cps]
		elif len(paths) > 0:
			self._data[cps] = (cpv, counter, paths)
		if self._autocommit:
			self.store()
	
	def unregister(self, cpv, slot, counter):
		""" Remove a previous registration of preserved objects for the given package.
			@param cpv: package instance whose records should be removed
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
		"""
		self.register(cpv, slot, counter, [])
	
	def pruneNonExisting(self):
		""" Remove all records for objects that no longer exist on the filesystem. """

		os = _os_merge

		for cps in list(self._data):
			cpv, counter, paths = self._data[cps]
			paths = [f for f in paths \
				if os.path.exists(os.path.join(self._root, f.lstrip(os.sep)))]
			if len(paths) > 0:
				self._data[cps] = (cpv, counter, paths)
			else:
				del self._data[cps]
		if self._autocommit:
			self.store()
	
	def hasEntries(self):
		""" Check if this registry contains any records. """
		return len(self._data) > 0
	
	def getPreservedLibs(self):
		""" Return a mapping of packages->preserved objects.
			@returns mapping of package instances to preserved objects
			@rtype Dict cpv->list-of-paths
		"""
		rValue = {}
		for cps in self._data:
			rValue[self._data[cps][0]] = self._data[cps][2]
		return rValue

class LinkageMap(object):

	"""Models dynamic linker dependencies."""

	_needed_aux_key = "NEEDED.ELF.2"
	_soname_map_class = slot_dict_class(
		("consumers", "providers"), prefix="")

	def __init__(self, vardbapi):
		self._dbapi = vardbapi
		self._root = self._dbapi.root
		self._libs = {}
		self._obj_properties = {}
		self._obj_key_cache = {}
		self._defpath = set()
		self._path_key_cache = {}

	def _clear_cache(self):
		self._libs.clear()
		self._obj_properties.clear()
		self._obj_key_cache.clear()
		self._defpath.clear()
		self._path_key_cache.clear()

	def _path_key(self, path):
		key = self._path_key_cache.get(path)
		if key is None:
			key = self._ObjectKey(path, self._root)
			self._path_key_cache[path] = key
		return key

	def _obj_key(self, path):
		key = self._obj_key_cache.get(path)
		if key is None:
			key = self._ObjectKey(path, self._root)
			self._obj_key_cache[path] = key
		return key

	class _ObjectKey(object):

		"""Helper class used as _obj_properties keys for objects."""

		__slots__ = ("__weakref__", "_key")

		def __init__(self, obj, root):
			"""
			This takes a path to an object.

			@param object: path to a file
			@type object: string (example: '/usr/bin/bar')

			"""
			self._key = self._generate_object_key(obj, root)

		def __hash__(self):
			return hash(self._key)

		def __eq__(self, other):
			return self._key == other._key

		def _generate_object_key(self, obj, root):
			"""
			Generate object key for a given object.

			@param object: path to a file
			@type object: string (example: '/usr/bin/bar')
			@rtype: 2-tuple of types (long, int) if object exists. string if
				object does not exist.
			@return:
				1. 2-tuple of object's inode and device from a stat call, if object
					exists.
				2. realpath of object if object does not exist.

			"""

			os = _os_merge

			try:
				_unicode_encode(obj,
					encoding=_encodings['merge'], errors='strict')
			except UnicodeEncodeError:
				# The package appears to have been merged with a 
				# different value of sys.getfilesystemencoding(),
				# so fall back to utf_8 if appropriate.
				try:
					_unicode_encode(obj,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeEncodeError:
					pass
				else:
					os = portage.os

			abs_path = os.path.join(root, obj.lstrip(os.sep))
			try:
				object_stat = os.stat(abs_path)
			except OSError:
				# Use the realpath as the key if the file does not exists on the
				# filesystem.
				return os.path.realpath(abs_path)
			# Return a tuple of the device and inode.
			return (object_stat.st_dev, object_stat.st_ino)

		def file_exists(self):
			"""
			Determine if the file for this key exists on the filesystem.

			@rtype: Boolean
			@return:
				1. True if the file exists.
				2. False if the file does not exist or is a broken symlink.

			"""
			return isinstance(self._key, tuple)

	class _LibGraphNode(_ObjectKey):
		__slots__ = ("alt_paths",)

		def __init__(self, obj, root):
			LinkageMap._ObjectKey.__init__(self, obj, root)
			self.alt_paths = set()

		def __str__(self):
			return str(sorted(self.alt_paths))

	def rebuild(self, exclude_pkgs=None, include_file=None):
		"""
		Raises CommandNotFound if there are preserved libs
		and the scanelf binary is not available.
		"""

		os = _os_merge
		root = self._root
		root_len = len(root) - 1
		self._clear_cache()
		self._defpath.update(getlibpaths(self._root))
		libs = self._libs
		obj_key_cache = self._obj_key_cache
		obj_properties = self._obj_properties

		lines = []

		# Data from include_file is processed first so that it
		# overrides any data from previously installed files.
		if include_file is not None:
			lines += grabfile(include_file)

		aux_keys = [self._needed_aux_key]
		for cpv in self._dbapi.cpv_all():
			if exclude_pkgs is not None and cpv in exclude_pkgs:
				continue
			lines += self._dbapi.aux_get(cpv, aux_keys)[0].split('\n')
		# Cache NEEDED.* files avoid doing excessive IO for every rebuild.
		self._dbapi.flush_cache()

		# have to call scanelf for preserved libs here as they aren't 
		# registered in NEEDED.ELF.2 files
		plibs = set()
		if self._dbapi.plib_registry and self._dbapi.plib_registry.getPreservedLibs():
			args = ["/usr/bin/scanelf", "-qF", "%a;%F;%S;%r;%n"]
			for items in self._dbapi.plib_registry.getPreservedLibs().values():
				plibs.update(items)
				args.extend(os.path.join(root, x.lstrip("." + os.sep)) \
					for x in items)
			try:
				proc = subprocess.Popen(args, stdout=subprocess.PIPE)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				raise CommandNotFound(args[0])
			else:
				for l in proc.stdout:
					try:
						l = _unicode_decode(l,
							encoding=_encodings['content'], errors='strict')
					except UnicodeDecodeError:
						l = _unicode_decode(l,
							encoding=_encodings['content'], errors='replace')
						writemsg_level(_("\nError decoding characters " \
							"returned from scanelf: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
					l = l[3:].rstrip("\n")
					if not l:
						continue
					fields = l.split(";")
					if len(fields) < 5:
						writemsg_level(_("\nWrong number of fields " \
							"returned from scanelf: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
						continue
					fields[1] = fields[1][root_len:]
					plibs.discard(fields[1])
					lines.append(";".join(fields))
				proc.wait()

		if plibs:
			# Preserved libraries that did not appear in the scanelf output.
			# This is known to happen with statically linked libraries.
			# Generate dummy lines for these, so we can assume that every
			# preserved library has an entry in self._obj_properties. This
			# is important in order to prevent findConsumers from raising
			# an unwanted KeyError.
			for x in plibs:
				lines.append(";".join(['', x, '', '', '']))

		for l in lines:
			l = l.rstrip("\n")
			if not l:
				continue
			fields = l.split(";")
			if len(fields) < 5:
				writemsg_level(_("\nWrong number of fields " \
					"in %s: %s\n\n") % (self._needed_aux_key, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			soname = fields[2]
			path = set([normalize_path(x) \
				for x in filter(None, fields[3].replace(
				"${ORIGIN}", os.path.dirname(obj)).replace(
				"$ORIGIN", os.path.dirname(obj)).split(":"))])
			needed = [x for x in fields[4].split(",") if x]

			obj_key = self._obj_key(obj)
			indexed = True
			myprops = obj_properties.get(obj_key)
			if myprops is None:
				indexed = False
				myprops = (arch, needed, path, soname, set())
				obj_properties[obj_key] = myprops
			# All object paths are added into the obj_properties tuple.
			myprops[4].add(obj)

			# Don't index the same file more that once since only one
			# set of data can be correct and therefore mixing data
			# may corrupt the index (include_file overrides previously
			# installed).
			if indexed:
				continue

			arch_map = libs.get(arch)
			if arch_map is None:
				arch_map = {}
				libs[arch] = arch_map
			if soname:
				soname_map = arch_map.get(soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=set(), consumers=set())
					arch_map[soname] = soname_map
				soname_map.providers.add(obj_key)
			for needed_soname in needed:
				soname_map = arch_map.get(needed_soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=set(), consumers=set())
					arch_map[needed_soname] = soname_map
				soname_map.consumers.add(obj_key)

	def listBrokenBinaries(self, debug=False):
		"""
		Find binaries and their needed sonames, which have no providers.

		@param debug: Boolean to enable debug output
		@type debug: Boolean
		@rtype: dict (example: {'/usr/bin/foo': set(['libbar.so'])})
		@return: The return value is an object -> set-of-sonames mapping, where
			object is a broken binary and the set consists of sonames needed by
			object that have no corresponding libraries to fulfill the dependency.

		"""

		os = _os_merge

		class _LibraryCache(object):

			"""
			Caches properties associated with paths.

			The purpose of this class is to prevent multiple instances of
			_ObjectKey for the same paths.

			"""

			def __init__(cache_self):
				cache_self.cache = {}

			def get(cache_self, obj):
				"""
				Caches and returns properties associated with an object.

				@param obj: absolute path (can be symlink)
				@type obj: string (example: '/usr/lib/libfoo.so')
				@rtype: 4-tuple with types
					(string or None, string or None, 2-tuple, Boolean)
				@return: 4-tuple with the following components:
					1. arch as a string or None if it does not exist,
					2. soname as a string or None if it does not exist,
					3. obj_key as 2-tuple,
					4. Boolean representing whether the object exists.
					(example: ('libfoo.so.1', (123L, 456L), True))

				"""
				if obj in cache_self.cache:
					return cache_self.cache[obj]
				else:
					obj_key = self._obj_key(obj)
					# Check that the library exists on the filesystem.
					if obj_key.file_exists():
						# Get the arch and soname from LinkageMap._obj_properties if
						# it exists. Otherwise, None.
						arch, _needed, _path, soname, _objs = \
								self._obj_properties.get(obj_key, (None,)*5)
						return cache_self.cache.setdefault(obj, \
								(arch, soname, obj_key, True))
					else:
						return cache_self.cache.setdefault(obj, \
								(None, None, obj_key, False))

		rValue = {}
		cache = _LibraryCache()
		providers = self.listProviders()

		# Iterate over all obj_keys and their providers.
		for obj_key, sonames in providers.items():
			arch, _needed, path, _soname, objs = self._obj_properties[obj_key]
			path = path.union(self._defpath)
			# Iterate over each needed soname and the set of library paths that
			# fulfill the soname to determine if the dependency is broken.
			for soname, libraries in sonames.items():
				# validLibraries is used to store libraries, which satisfy soname,
				# so if no valid libraries are found, the soname is not satisfied
				# for obj_key.  If unsatisfied, objects associated with obj_key
				# must be emerged.
				validLibraries = set()
				# It could be the case that the library to satisfy the soname is
				# not in the obj's runpath, but a symlink to the library is (eg
				# libnvidia-tls.so.1 in nvidia-drivers).  Also, since LinkageMap
				# does not catalog symlinks, broken or missing symlinks may go
				# unnoticed.  As a result of these cases, check that a file with
				# the same name as the soname exists in obj's runpath.
				# XXX If we catalog symlinks in LinkageMap, this could be improved.
				for directory in path:
					cachedArch, cachedSoname, cachedKey, cachedExists = \
							cache.get(os.path.join(directory, soname))
					# Check that this library provides the needed soname.  Doing
					# this, however, will cause consumers of libraries missing
					# sonames to be unnecessarily emerged. (eg libmix.so)
					if cachedSoname == soname and cachedArch == arch:
						validLibraries.add(cachedKey)
						if debug and cachedKey not in \
								set(map(self._obj_key_cache.get, libraries)):
							# XXX This is most often due to soname symlinks not in
							# a library's directory.  We could catalog symlinks in
							# LinkageMap to avoid checking for this edge case here.
							writemsg(
								_("Found provider outside of findProviders:") + \
								(" %s -> %s %s\n" % (os.path.join(directory, soname),
								self._obj_properties[cachedKey][4], libraries)),
								noiselevel=-1)
						# A valid library has been found, so there is no need to
						# continue.
						break
					if debug and cachedArch == arch and \
							cachedKey in self._obj_properties:
						writemsg((_("Broken symlink or missing/bad soname: " + \
							"%(dir_soname)s -> %(cachedKey)s " + \
							"with soname %(cachedSoname)s but expecting %(soname)s") % \
							{"dir_soname":os.path.join(directory, soname),
							"cachedKey": self._obj_properties[cachedKey],
							"cachedSoname": cachedSoname, "soname":soname}) + "\n",
							noiselevel=-1)
				# This conditional checks if there are no libraries to satisfy the
				# soname (empty set).
				if not validLibraries:
					for obj in objs:
						rValue.setdefault(obj, set()).add(soname)
					# If no valid libraries have been found by this point, then
					# there are no files named with the soname within obj's runpath,
					# but if there are libraries (from the providers mapping), it is
					# likely that soname symlinks or the actual libraries are
					# missing or broken.  Thus those libraries are added to rValue
					# in order to emerge corrupt library packages.
					for lib in libraries:
						rValue.setdefault(lib, set()).add(soname)
						if debug:
							if not os.path.isfile(lib):
								writemsg(_("Missing library:") + " %s\n" % (lib,),
									noiselevel=-1)
							else:
								writemsg(_("Possibly missing symlink:") + \
									"%s\n" % (os.path.join(os.path.dirname(lib), soname)),
									noiselevel=-1)
		return rValue

	def listProviders(self):
		"""
		Find the providers for all object keys in LinkageMap.

		@rtype: dict (example:
			{(123L, 456L): {'libbar.so': set(['/lib/libbar.so.1.5'])}})
		@return: The return value is an object key -> providers mapping, where
			providers is a mapping of soname -> set-of-library-paths returned
			from the findProviders method.

		"""
		rValue = {}
		if not self._libs:
			self.rebuild()
		# Iterate over all object keys within LinkageMap.
		for obj_key in self._obj_properties:
			rValue.setdefault(obj_key, self.findProviders(obj_key))
		return rValue

	def isMasterLink(self, obj):
		"""
		Determine whether an object is a master link.

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/foo')
		@rtype: Boolean
		@return:
			1. True if obj is a master link
			2. False if obj is not a master link

		"""
		os = _os_merge
		basename = os.path.basename(obj)
		obj_key = self._obj_key(obj)
		if obj_key not in self._obj_properties:
			raise KeyError("%s (%s) not in object list" % (obj_key, obj))
		soname = self._obj_properties[obj_key][3]
		return (len(basename) < len(soname))

	def listLibraryObjects(self):
		"""
		Return a list of library objects.

		Known limitation: library objects lacking an soname are not included.

		@rtype: list of strings
		@return: list of paths to all providers

		"""
		rValue = []
		if not self._libs:
			self.rebuild()
		for arch_map in self._libs.values():
			for soname_map in arch_map.values():
				for obj_key in soname_map.providers:
					rValue.extend(self._obj_properties[obj_key][4])
		return rValue

	def getSoname(self, obj):
		"""
		Return the soname associated with an object.

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/bar')
		@rtype: string
		@return: soname as a string

		"""
		if not self._libs:
			self.rebuild()
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			return self._obj_properties[obj_key][3]
		if obj not in self._obj_key_cache:
			raise KeyError("%s not in object list" % obj)
		return self._obj_properties[self._obj_key_cache[obj]][3]

	def findProviders(self, obj):
		"""
		Find providers for an object or object key.

		This method may be called with a key from _obj_properties.

		In some cases, not all valid libraries are returned.  This may occur when
		an soname symlink referencing a library is in an object's runpath while
		the actual library is not.  We should consider cataloging symlinks within
		LinkageMap as this would avoid those cases and would be a better model of
		library dependencies (since the dynamic linker actually searches for
		files named with the soname in the runpaths).

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@rtype: dict (example: {'libbar.so': set(['/lib/libbar.so.1.5'])})
		@return: The return value is a soname -> set-of-library-paths, where
		set-of-library-paths satisfy soname.

		"""

		os = _os_merge

		rValue = {}

		if not self._libs:
			self.rebuild()

		# Determine the obj_key from the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
		else:
			obj_key = self._obj_key(obj)
			if obj_key not in self._obj_properties:
				raise KeyError("%s (%s) not in object list" % (obj_key, obj))

		arch, needed, path, _soname, _objs = self._obj_properties[obj_key]
		path_keys = set(self._path_key(x) for x in path.union(self._defpath))
		for soname in needed:
			rValue[soname] = set()
			if arch not in self._libs or soname not in self._libs[arch]:
				continue
			# For each potential provider of the soname, add it to rValue if it
			# resides in the obj's runpath.
			for provider_key in self._libs[arch][soname].providers:
				providers = self._obj_properties[provider_key][4]
				for provider in providers:
					if self._path_key(os.path.dirname(provider)) in path_keys:
						rValue[soname].add(provider)
		return rValue

	def findConsumers(self, obj):
		"""
		Find consumers of an object or object key.

		This method may be called with a key from _obj_properties.  If this
		method is going to be called with an object key, to avoid not catching
		shadowed libraries, do not pass new _ObjectKey instances to this method.
		Instead pass the obj as a string.

		In some cases, not all consumers are returned.  This may occur when
		an soname symlink referencing a library is in an object's runpath while
		the actual library is not. For example, this problem is noticeable for
		binutils since it's libraries are added to the path via symlinks that
		are gemerated in the /usr/$CHOST/lib/ directory by binutils-config.
		Failure to recognize consumers of these symlinks makes preserve-libs
		fail to preserve binutils libs that are needed by these unrecognized
		consumers.

		Note that library consumption via dlopen (common for kde plugins) is
		currently undetected. However, it is possible to use the
		corresponding libtool archive (*.la) files to detect such consumers
		(revdep-rebuild is able to detect them).

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@rtype: set of strings (example: set(['/bin/foo', '/usr/bin/bar']))
		@return: The return value is a soname -> set-of-library-paths, where
		set-of-library-paths satisfy soname.

		"""

		os = _os_merge

		rValue = set()

		if not self._libs:
			self.rebuild()

		# Determine the obj_key and the set of objects matching the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			objs = self._obj_properties[obj_key][4]
		else:
			objs = set([obj])
			obj_key = self._obj_key(obj)
			if obj_key not in self._obj_properties:
				raise KeyError("%s (%s) not in object list" % (obj_key, obj))

		# If there is another version of this lib with the
		# same soname and the master link points to that
		# other version, this lib will be shadowed and won't
		# have any consumers.
		if not isinstance(obj, self._ObjectKey):
			soname = self._obj_properties[obj_key][3]
			master_link = os.path.join(self._root,
				os.path.dirname(obj).lstrip(os.path.sep), soname)
			try:
				master_st = os.stat(master_link)
				obj_st = os.stat(obj)
			except OSError:
				pass
			else:
				if (obj_st.st_dev, obj_st.st_ino) != \
					(master_st.st_dev, master_st.st_ino):
					return set()

		# Determine the directory(ies) from the set of objects.
		objs_dir_keys = set(self._path_key(os.path.dirname(x)) for x in objs)
		defpath_keys = set(self._path_key(x) for x in self._defpath)

		arch, _needed, _path, soname, _objs = self._obj_properties[obj_key]
		if arch in self._libs and soname in self._libs[arch]:
			# For each potential consumer, add it to rValue if an object from the
			# arguments resides in the consumer's runpath.
			for consumer_key in self._libs[arch][soname].consumers:
				_arch, _needed, path, _soname, consumer_objs = \
						self._obj_properties[consumer_key]
				path_keys = defpath_keys.union(self._path_key(x) for x in path)
				if objs_dir_keys.intersection(path_keys):
					rValue.update(consumer_objs)
		return rValue

class vardbapi(dbapi):

	_excluded_dirs = ["CVS", "lost+found"]
	_excluded_dirs = [re.escape(x) for x in _excluded_dirs]
	_excluded_dirs = re.compile(r'^(\..*|-MERGING-.*|' + \
		"|".join(_excluded_dirs) + r')$')

	_aux_cache_version        = "1"
	_owners_cache_version     = "1"

	# Number of uncached packages to trigger cache update, since
	# it's wasteful to update it for every vdb change.
	_aux_cache_threshold = 5

	_aux_cache_keys_re = re.compile(r'^NEEDED\..*$')
	_aux_multi_line_re = re.compile(r'^(CONTENTS|NEEDED\..*)$')

	def __init__(self, root, categories=None, settings=None, vartree=None):
		"""
		The categories parameter is unused since the dbapi class
		now has a categories property that is generated from the
		available packages.
		"""
		self.root = _unicode_decode(root,
			encoding=_encodings['content'], errors='strict')

		# Used by emerge to check whether any packages
		# have been added or removed.
		self._pkgs_changed = False

		#cache for category directory mtimes
		self.mtdircache = {}

		#cache for dependency checks
		self.matchcache = {}

		#cache for cp_list results
		self.cpcache = {}

		self.blockers = None
		if settings is None:
			from portage import settings
		self.settings = settings
		if vartree is None:
			from portage import db
			vartree = db[root]["vartree"]
		self.vartree = vartree
		self._aux_cache_keys = set(
			["BUILD_TIME", "CHOST", "COUNTER", "DEPEND", "DESCRIPTION",
			"EAPI", "HOMEPAGE", "IUSE", "KEYWORDS",
			"LICENSE", "PDEPEND", "PROPERTIES", "PROVIDE", "RDEPEND",
			"repository", "RESTRICT" , "SLOT", "USE"])
		self._aux_cache_obj = None
		self._aux_cache_filename = os.path.join(self.root,
			CACHE_PATH, "vdb_metadata.pickle")
		self._counter_path = os.path.join(root,
			CACHE_PATH, "counter")

		try:
			self.plib_registry = PreservedLibsRegistry(self.root,
				os.path.join(self.root, PRIVATE_PATH, "preserved_libs_registry"))
		except PermissionDenied:
			# apparently this user isn't allowed to access PRIVATE_PATH
			self.plib_registry = None

		self.linkmap = LinkageMap(self)
		self._owners = self._owners_db(self)

	def getpath(self, mykey, filename=None):
		# This is an optimized hotspot, so don't use unicode-wrapped
		# os module and don't use os.path.join().
		rValue = self.root + _os.sep + VDB_PATH + _os.sep + mykey
		if filename is not None:
			# If filename is always relative, we can do just
			# rValue += _os.sep + filename
			rValue = _os.path.join(rValue, filename)
		return rValue

	def _bump_mtime(self, cpv):
		"""
		This is called before an after any modifications, so that consumers
		can use directory mtimes to validate caches. See bug #290428.
		"""
		base = self.root + _os.sep + VDB_PATH
		cat = catsplit(cpv)[0]
		catdir = base + _os.sep + cat
		t = time.time()
		t = (t, t)
		try:
			for x in (catdir, base):
				os.utime(x, t)
		except OSError:
			os.makedirs(catdir)

	def cpv_exists(self, mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.getpath(mykey))

	def cpv_counter(self, mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		try:
			return long(self.aux_get(mycpv, ["COUNTER"])[0])
		except (KeyError, ValueError):
			pass
		writemsg_level(_("portage: COUNTER for %s was corrupted; " \
			"resetting to value of 0\n") % (mycpv,),
			level=logging.ERROR, noiselevel=-1)
		return 0

	def cpv_inject(self, mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		os.makedirs(self.getpath(mycpv))
		counter = self.counter_tick(self.root, mycpv=mycpv)
		# write local package counter so that emerge clean does the right thing
		write_atomic(self.getpath(mycpv, filename="COUNTER"), str(counter))

	def isInjected(self, mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.getpath(mycpv, filename="INJECTED")):
				return True
			if not os.path.exists(self.getpath(mycpv, filename="CONTENTS")):
				return True
		return False

	def move_ent(self, mylist):
		origcp = mylist[1]
		newcp = mylist[2]

		# sanity check
		for atom in (origcp, newcp):
			if not isjustname(atom):
				raise InvalidPackageName(str(atom))
		origmatches = self.match(origcp, use_cache=0)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			mycpv_cp = cpv_getkey(mycpv)
			if mycpv_cp != origcp:
				# Ignore PROVIDE virtual match.
				continue
			mynewcpv = mycpv.replace(mycpv_cp, str(newcp), 1)
			mynewcat = catsplit(newcp)[0]
			origpath = self.getpath(mycpv)
			if not os.path.exists(origpath):
				continue
			moves += 1
			if not os.path.exists(self.getpath(mynewcat)):
				#create the directory
				os.makedirs(self.getpath(mynewcat))
			newpath = self.getpath(mynewcpv)
			if os.path.exists(newpath):
				#dest already exists; keep this puppy where it is.
				continue
			_movefile(origpath, newpath, mysettings=self.settings)
			self._clear_pkg_cache(self._dblink(mycpv))
			self._clear_pkg_cache(self._dblink(mynewcpv))

			# We need to rename the ebuild now.
			old_pf = catsplit(mycpv)[1]
			new_pf = catsplit(mynewcpv)[1]
			if new_pf != old_pf:
				try:
					os.rename(os.path.join(newpath, old_pf + ".ebuild"),
						os.path.join(newpath, new_pf + ".ebuild"))
				except EnvironmentError as e:
					if e.errno != errno.ENOENT:
						raise
					del e
			write_atomic(os.path.join(newpath, "PF"), new_pf+"\n")
			write_atomic(os.path.join(newpath, "CATEGORY"), mynewcat+"\n")
			fixdbentries([mylist], newpath)
		return moves

	def cp_list(self, mycp, use_cache=1):
		mysplit=catsplit(mycp)
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat = os.stat(self.getpath(mysplit[0])).st_mtime
		except OSError:
			mystat = 0
		if use_cache and mycp in self.cpcache:
			cpc = self.cpcache[mycp]
			if cpc[0] == mystat:
				return cpc[1][:]
		cat_dir = self.getpath(mysplit[0])
		try:
			dir_list = os.listdir(cat_dir)
		except EnvironmentError as e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(cat_dir)
			del e
			dir_list = []

		returnme = []
		for x in dir_list:
			if self._excluded_dirs.match(x) is not None:
				continue
			ps = pkgsplit(x)
			if not ps:
				self.invalidentry(os.path.join(self.getpath(mysplit[0]), x))
				continue
			if len(mysplit) > 1:
				if ps[0] == mysplit[1]:
					returnme.append(mysplit[0]+"/"+x)
		self._cpv_sort_ascending(returnme)
		if use_cache:
			self.cpcache[mycp] = [mystat, returnme[:]]
		elif mycp in self.cpcache:
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self, use_cache=1):
		"""
		Set use_cache=0 to bypass the portage.cachedir() cache in cases
		when the accuracy of mtime staleness checks should not be trusted
		(generally this is only necessary in critical sections that
		involve merge or unmerge of packages).
		"""
		returnme = []
		basepath = os.path.join(self.root, VDB_PATH) + os.path.sep

		if use_cache:
			from portage import listdir
		else:
			def listdir(p, **kwargs):
				try:
					return [x for x in os.listdir(p) \
						if os.path.isdir(os.path.join(p, x))]
				except EnvironmentError as e:
					if e.errno == PermissionDenied.errno:
						raise PermissionDenied(p)
					del e
					return []

		for x in listdir(basepath, EmptyOnError=1, ignorecvs=1, dirsonly=1):
			if self._excluded_dirs.match(x) is not None:
				continue
			if not self._category_re.match(x):
				continue
			for y in listdir(basepath + x, EmptyOnError=1, dirsonly=1):
				if self._excluded_dirs.match(y) is not None:
					continue
				subpath = x + "/" + y
				# -MERGING- should never be a cpv, nor should files.
				try:
					if catpkgsplit(subpath) is None:
						self.invalidentry(self.getpath(subpath))
						continue
				except InvalidData:
					self.invalidentry(self.getpath(subpath))
					continue
				returnme.append(subpath)

		return returnme

	def cp_all(self, use_cache=1):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			try:
				mysplit = catpkgsplit(y)
			except InvalidData:
				self.invalidentry(self.getpath(y))
				continue
			if not mysplit:
				self.invalidentry(self.getpath(y))
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return list(d)

	def checkblockers(self, origdep):
		pass

	def _clear_cache(self):
		self.mtdircache.clear()
		self.matchcache.clear()
		self.cpcache.clear()
		self._aux_cache_obj = None

	def _add(self, pkg_dblink):
		self._pkgs_changed = True
		self._clear_pkg_cache(pkg_dblink)

	def _remove(self, pkg_dblink):
		self._pkgs_changed = True
		self._clear_pkg_cache(pkg_dblink)

	def _clear_pkg_cache(self, pkg_dblink):
		# Due to 1 second mtime granularity in <python-2.5, mtime checks
		# are not always sufficient to invalidate vardbapi caches. Therefore,
		# the caches need to be actively invalidated here.
		self.mtdircache.pop(pkg_dblink.cat, None)
		self.matchcache.pop(pkg_dblink.cat, None)
		self.cpcache.pop(pkg_dblink.mysplit[0], None)
		dircache.pop(pkg_dblink.dbcatdir, None)

	def match(self, origdep, use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		mykey = dep_getkey(mydep)
		mycat = catsplit(mykey)[0]
		if not use_cache:
			if mycat in self.matchcache:
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			return list(self._iter_match(mydep,
				self.cp_list(mydep.cp, use_cache=use_cache)))
		try:
			curmtime = os.stat(os.path.join(self.root, VDB_PATH, mycat)).st_mtime
		except (IOError, OSError):
			curmtime=0

		if mycat not in self.matchcache or \
			self.mtdircache[mycat] != curmtime:
			# clear cache entry
			self.mtdircache[mycat] = curmtime
			self.matchcache[mycat] = {}
		if mydep not in self.matchcache[mycat]:
			mymatch = list(self._iter_match(mydep,
				self.cp_list(mydep.cp, use_cache=use_cache)))
			self.matchcache[mycat][mydep] = mymatch
		return self.matchcache[mycat][mydep][:]

	def findname(self, mycpv):
		return self.getpath(str(mycpv), filename=catsplit(mycpv)[1]+".ebuild")

	def flush_cache(self):
		"""If the current user has permission and the internal aux_get cache has
		been updated, save it to disk and mark it unmodified.  This is called
		by emerge after it has loaded the full vdb for use in dependency
		calculations.  Currently, the cache is only written if the user has
		superuser privileges (since that's required to obtain a lock), but all
		users have read access and benefit from faster metadata lookups (as
		long as at least part of the cache is still valid)."""
		if self._aux_cache is not None and \
			len(self._aux_cache["modified"]) >= self._aux_cache_threshold and \
			secpass >= 2:
			self._owners.populate() # index any unindexed contents
			valid_nodes = set(self.cpv_all())
			for cpv in list(self._aux_cache["packages"]):
				if cpv not in valid_nodes:
					del self._aux_cache["packages"][cpv]
			del self._aux_cache["modified"]
			try:
				f = atomic_ofstream(self._aux_cache_filename, 'wb')
				pickle.dump(self._aux_cache, f, protocol=2)
				f.close()
				apply_secpass_permissions(
					self._aux_cache_filename, gid=portage_gid, mode=0o644)
			except (IOError, OSError) as e:
				pass
			self._aux_cache["modified"] = set()

	@property
	def _aux_cache(self):
		if self._aux_cache_obj is None:
			self._aux_cache_init()
		return self._aux_cache_obj

	def _aux_cache_init(self):
		aux_cache = None
		open_kwargs = {}
		if sys.hexversion >= 0x3000000:
			# Buffered io triggers extreme performance issues in
			# Unpickler.load() (problem observed with python-3.0.1).
			# Unfortunately, performance is still poor relative to
			# python-2.x, but buffering makes it much worse.
			open_kwargs["buffering"] = 0
		try:
			f = open(_unicode_encode(self._aux_cache_filename,
				encoding=_encodings['fs'], errors='strict'),
				mode='rb', **open_kwargs)
			mypickle = pickle.Unpickler(f)
			try:
				mypickle.find_global = None
			except AttributeError:
				# TODO: If py3k, override Unpickler.find_class().
				pass
			aux_cache = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, ValueError, pickle.UnpicklingError) as e:
			if isinstance(e, pickle.UnpicklingError):
				writemsg(_("!!! Error loading '%s': %s\n") % \
					(self._aux_cache_filename, str(e)), noiselevel=-1)
			del e

		if not aux_cache or \
			not isinstance(aux_cache, dict) or \
			aux_cache.get("version") != self._aux_cache_version or \
			not aux_cache.get("packages"):
			aux_cache = {"version": self._aux_cache_version}
			aux_cache["packages"] = {}

		owners = aux_cache.get("owners")
		if owners is not None:
			if not isinstance(owners, dict):
				owners = None
			elif "version" not in owners:
				owners = None
			elif owners["version"] != self._owners_cache_version:
				owners = None
			elif "base_names" not in owners:
				owners = None
			elif not isinstance(owners["base_names"], dict):
				owners = None

		if owners is None:
			owners = {
				"base_names" : {},
				"version"    : self._owners_cache_version
			}
			aux_cache["owners"] = owners

		aux_cache["modified"] = set()
		self._aux_cache_obj = aux_cache

	def aux_get(self, mycpv, wants):
		"""This automatically caches selected keys that are frequently needed
		by emerge for dependency calculations.  The cached metadata is
		considered valid if the mtime of the package directory has not changed
		since the data was cached.  The cache is stored in a pickled dict
		object with the following format:

		{version:"1", "packages":{cpv1:(mtime,{k1,v1, k2,v2, ...}), cpv2...}}

		If an error occurs while loading the cache pickle or the version is
		unrecognized, the cache will simple be recreated from scratch (it is
		completely disposable).
		"""
		cache_these_wants = self._aux_cache_keys.intersection(wants)
		for x in wants:
			if self._aux_cache_keys_re.match(x) is not None:
				cache_these_wants.add(x)

		if not cache_these_wants:
			return self._aux_get(mycpv, wants)

		cache_these = set(self._aux_cache_keys)
		cache_these.update(cache_these_wants)

		mydir = self.getpath(mycpv)
		mydir_stat = None
		try:
			mydir_stat = os.stat(mydir)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			raise KeyError(mycpv)
		mydir_mtime = mydir_stat[stat.ST_MTIME]
		pkg_data = self._aux_cache["packages"].get(mycpv)
		pull_me = cache_these.union(wants)
		mydata = {"_mtime_" : mydir_mtime}
		cache_valid = False
		cache_incomplete = False
		cache_mtime = None
		metadata = None
		if pkg_data is not None:
			if not isinstance(pkg_data, tuple) or len(pkg_data) != 2:
				pkg_data = None
			else:
				cache_mtime, metadata = pkg_data
				if not isinstance(cache_mtime, (long, int)) or \
					not isinstance(metadata, dict):
					pkg_data = None

		if pkg_data:
			cache_mtime, metadata = pkg_data
			cache_valid = cache_mtime == mydir_mtime
		if cache_valid:
			# Migrate old metadata to unicode.
			for k, v in metadata.items():
				metadata[k] = _unicode_decode(v,
					encoding=_encodings['repo.content'], errors='replace')

			mydata.update(metadata)
			pull_me.difference_update(mydata)

		if pull_me:
			# pull any needed data and cache it
			aux_keys = list(pull_me)
			for k, v in zip(aux_keys,
				self._aux_get(mycpv, aux_keys, st=mydir_stat)):
				mydata[k] = v
			if not cache_valid or cache_these.difference(metadata):
				cache_data = {}
				if cache_valid and metadata:
					cache_data.update(metadata)
				for aux_key in cache_these:
					cache_data[aux_key] = mydata[aux_key]
				self._aux_cache["packages"][mycpv] = (mydir_mtime, cache_data)
				self._aux_cache["modified"].add(mycpv)

		if _slot_re.match(mydata['SLOT']) is None:
			# Empty or invalid slot triggers InvalidAtom exceptions when
			# generating slot atoms for packages, so translate it to '0' here.
			mydata['SLOT'] = _unicode_decode('0')

		return [mydata[x] for x in wants]

	def _aux_get(self, mycpv, wants, st=None):
		mydir = self.getpath(mycpv)
		if st is None:
			try:
				st = os.stat(mydir)
			except OSError as e:
				if e.errno == errno.ENOENT:
					raise KeyError(mycpv)
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(mydir)
				else:
					raise
		if not stat.S_ISDIR(st.st_mode):
			raise KeyError(mycpv)
		results = []
		for x in wants:
			if x == "_mtime_":
				results.append(st[stat.ST_MTIME])
				continue
			try:
				myf = codecs.open(
					_unicode_encode(os.path.join(mydir, x),
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace')
				try:
					myd = myf.read()
				finally:
					myf.close()
				# Preserve \n for metadata that is known to
				# contain multiple lines.
				if self._aux_multi_line_re.match(x) is None:
					myd = " ".join(myd.split())
			except IOError:
				myd = _unicode_decode('')
			if x == "EAPI" and not myd:
				results.append(_unicode_decode('0'))
			else:
				results.append(myd)
		return results

	def aux_update(self, cpv, values):
		self._bump_mtime(cpv)
		cat, pkg = catsplit(cpv)
		mylink = dblink(cat, pkg, self.root, self.settings,
		treetype="vartree", vartree=self.vartree)
		if not mylink.exists():
			raise KeyError(cpv)
		self._clear_pkg_cache(mylink)
		for k, v in values.items():
			if v:
				mylink.setfile(k, v)
			else:
				try:
					os.unlink(os.path.join(self.getpath(cpv), k))
				except EnvironmentError:
					pass
		self._bump_mtime(cpv)

	def counter_tick(self, myroot, mycpv=None):
		return self.counter_tick_core(myroot, incrementing=1, mycpv=mycpv)

	def get_counter_tick_core(self, myroot, mycpv=None):
		"""
		Use this method to retrieve the counter instead
		of having to trust the value of a global counter
		file that can lead to invalid COUNTER
		generation. When cache is valid, the package COUNTER
		files are not read and we rely on the timestamp of
		the package directory to validate cache. The stat
		calls should only take a short time, so performance
		is sufficient without having to rely on a potentially
		corrupt global counter file.

		The global counter file located at
		$CACHE_PATH/counter serves to record the
		counter of the last installed package and
		it also corresponds to the total number of
		installation actions that have occurred in
		the history of this package database.
		"""
		cp_list = self.cp_list
		max_counter = 0
		for cp in self.cp_all():
			for cpv in cp_list(cp):
				try:
					counter = int(self.aux_get(cpv, ["COUNTER"])[0])
				except (KeyError, OverflowError, ValueError):
					continue
				if counter > max_counter:
					max_counter = counter

		new_vdb = False
		counter = -1
		try:
			cfile = codecs.open(
				_unicode_encode(self._counter_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
		except EnvironmentError as e:
			new_vdb = not bool(self.cpv_all())
			if not new_vdb:
				writemsg(_("!!! Unable to read COUNTER file: '%s'\n") % \
					self._counter_path, noiselevel=-1)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
			del e
		else:
			try:
				try:
					counter = long(cfile.readline().strip())
				finally:
					cfile.close()
			except (OverflowError, ValueError) as e:
				writemsg(_("!!! COUNTER file is corrupt: '%s'\n") % \
					self._counter_path, noiselevel=-1)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				del e

		# We must ensure that we return a counter
		# value that is at least as large as the
		# highest one from the installed packages,
		# since having a corrupt value that is too low
		# can trigger incorrect AUTOCLEAN behavior due
		# to newly installed packages having lower
		# COUNTERs than the previous version in the
		# same slot.
		if counter > max_counter:
			max_counter = counter

		if counter < 0 and not new_vdb:
			writemsg(_("!!! Initializing COUNTER to " \
				"value of %d\n") % max_counter, noiselevel=-1)

		return max_counter + 1

	def counter_tick_core(self, myroot, incrementing=1, mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		counter = self.get_counter_tick_core(myroot, mycpv=mycpv) - 1
		if incrementing:
			#increment counter
			counter += 1
			# update new global counter file
			write_atomic(self._counter_path, str(counter))
		return counter

	def _dblink(self, cpv):
		category, pf = catsplit(cpv)
		return dblink(category, pf, self.root,
			self.settings, vartree=self.vartree, treetype="vartree")

	def removeFromContents(self, pkg, paths, relative_paths=True):
		"""
		@param pkg: cpv for an installed package
		@type pkg: string
		@param paths: paths of files to remove from contents
		@type paths: iterable
		"""
		if not hasattr(pkg, "getcontents"):
			pkg = self._dblink(pkg)
		root = self.root
		root_len = len(root) - 1
		new_contents = pkg.getcontents().copy()
		removed = 0

		for filename in paths:
			filename = _unicode_decode(filename,
				encoding=_encodings['content'], errors='strict')
			filename = normalize_path(filename)
			if relative_paths:
				relative_filename = filename
			else:
				relative_filename = filename[root_len:]
			contents_key = pkg._match_contents(relative_filename, root)
			if contents_key:
				del new_contents[contents_key]
				removed += 1

		if removed:
			self._bump_mtime(pkg.mycpv)
			f = atomic_ofstream(os.path.join(pkg.dbdir, "CONTENTS"))
			write_contents(new_contents, root, f)
			f.close()
			self._bump_mtime(pkg.mycpv)
			pkg._clear_contents_cache()

	class _owners_cache(object):
		"""
		This class maintains an hash table that serves to index package
		contents by mapping the basename of file to a list of possible
		packages that own it. This is used to optimize owner lookups
		by narrowing the search down to a smaller number of packages.
		"""
		try:
			from hashlib import md5 as _new_hash
		except ImportError:
			from md5 import new as _new_hash

		_hash_bits = 16
		_hex_chars = int(_hash_bits / 4)

		def __init__(self, vardb):
			self._vardb = vardb

		def add(self, cpv):
			root_len = len(self._vardb.root)
			contents = self._vardb._dblink(cpv).getcontents()
			pkg_hash = self._hash_pkg(cpv)
			if not contents:
				# Empty path is a code used to represent empty contents.
				self._add_path("", pkg_hash)
			for x in contents:
				self._add_path(x[root_len:], pkg_hash)
			self._vardb._aux_cache["modified"].add(cpv)

		def _add_path(self, path, pkg_hash):
			"""
			Empty path is a code that represents empty contents.
			"""
			if path:
				name = os.path.basename(path.rstrip(os.path.sep))
				if not name:
					return
			else:
				name = path
			name_hash = self._hash_str(name)
			base_names = self._vardb._aux_cache["owners"]["base_names"]
			pkgs = base_names.get(name_hash)
			if pkgs is None:
				pkgs = {}
				base_names[name_hash] = pkgs
			pkgs[pkg_hash] = None

		def _hash_str(self, s):
			h = self._new_hash()
			# Always use a constant utf_8 encoding here, since
			# the "default" encoding can change.
			h.update(_unicode_encode(s,
				encoding=_encodings['repo.content'],
				errors='backslashreplace'))
			h = h.hexdigest()
			h = h[-self._hex_chars:]
			h = int(h, 16)
			return h

		def _hash_pkg(self, cpv):
			counter, mtime = self._vardb.aux_get(
				cpv, ["COUNTER", "_mtime_"])
			try:
				counter = int(counter)
			except ValueError:
				counter = 0
			return (cpv, counter, mtime)

	class _owners_db(object):

		def __init__(self, vardb):
			self._vardb = vardb

		def populate(self):
			self._populate()

		def _populate(self):
			owners_cache = vardbapi._owners_cache(self._vardb)
			cached_hashes = set()
			base_names = self._vardb._aux_cache["owners"]["base_names"]

			# Take inventory of all cached package hashes.
			for name, hash_values in list(base_names.items()):
				if not isinstance(hash_values, dict):
					del base_names[name]
					continue
				cached_hashes.update(hash_values)

			# Create sets of valid package hashes and uncached packages.
			uncached_pkgs = set()
			hash_pkg = owners_cache._hash_pkg
			valid_pkg_hashes = set()
			for cpv in self._vardb.cpv_all():
				hash_value = hash_pkg(cpv)
				valid_pkg_hashes.add(hash_value)
				if hash_value not in cached_hashes:
					uncached_pkgs.add(cpv)

			# Cache any missing packages.
			for cpv in uncached_pkgs:
				owners_cache.add(cpv)

			# Delete any stale cache.
			stale_hashes = cached_hashes.difference(valid_pkg_hashes)
			if stale_hashes:
				for base_name_hash, bucket in list(base_names.items()):
					for hash_value in stale_hashes.intersection(bucket):
						del bucket[hash_value]
					if not bucket:
						del base_names[base_name_hash]

			return owners_cache

		def get_owners(self, path_iter):
			"""
			@return the owners as a dblink -> set(files) mapping.
			"""
			owners = {}
			for owner, f in self.iter_owners(path_iter):
				owned_files = owners.get(owner)
				if owned_files is None:
					owned_files = set()
					owners[owner] = owned_files
				owned_files.add(f)
			return owners

		def getFileOwnerMap(self, path_iter):
			owners = self.get_owners(path_iter)
			file_owners = {}
			for pkg_dblink, files in owners.items():
				for f in files:
					owner_set = file_owners.get(f)
					if owner_set is None:
						owner_set = set()
						file_owners[f] = owner_set
					owner_set.add(pkg_dblink)
			return file_owners

		def iter_owners(self, path_iter):
			"""
			Iterate over tuples of (dblink, path). In order to avoid
			consuming too many resources for too much time, resources
			are only allocated for the duration of a given iter_owners()
			call. Therefore, to maximize reuse of resources when searching
			for multiple files, it's best to search for them all in a single
			call.
			"""

			owners_cache = self._populate()

			vardb = self._vardb
			root = vardb.root
			hash_pkg = owners_cache._hash_pkg
			hash_str = owners_cache._hash_str
			base_names = self._vardb._aux_cache["owners"]["base_names"]

			dblink_cache = {}
			dblink_fifo = deque()

			def dblink(cpv):
				x = dblink_cache.get(cpv)
				if x is None:
					if len(dblink_fifo) >= 100:
						# Ensure that we don't run out of memory.
						del dblink_cache[dblink_fifo.popleft().mycpv]
					x = self._vardb._dblink(cpv)
					dblink_cache[cpv] = x
					dblink_fifo.append(x)
				return x

			for path in path_iter:
				is_basename = os.sep != path[:1]
				if is_basename:
					name = path
				else:
					name = os.path.basename(path.rstrip(os.path.sep))

				if not name:
					continue

				name_hash = hash_str(name)
				pkgs = base_names.get(name_hash)
				if pkgs is not None:
					for hash_value in pkgs:
						if not isinstance(hash_value, tuple) or \
							len(hash_value) != 3:
							continue
						cpv, counter, mtime = hash_value
						if not isinstance(cpv, basestring):
							continue
						try:
							current_hash = hash_pkg(cpv)
						except KeyError:
							continue

						if current_hash != hash_value:
							continue

						if is_basename:
							for p in dblink(cpv).getcontents():
								if os.path.basename(p) == name:
									yield dblink(cpv), p[len(root):]
						else:
							if dblink(cpv).isowner(path, root):
								yield dblink(cpv), path

class vartree(object):
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self, root="/", virtual=None, clone=None, categories=None,
		settings=None):
		if clone:
			writemsg("vartree.__init__(): deprecated " + \
				"use of clone parameter\n", noiselevel=-1)
			self.root = clone.root[:]
			self.dbapi = copy.deepcopy(clone.dbapi)
			self.populated = 1
			from portage import config
			self.settings = config(clone=clone.settings)
		else:
			self.root = root[:]
			if settings is None:
				from portage import settings
			self.settings = settings
			if categories is None:
				categories = settings.categories
			self.dbapi = vardbapi(self.root, categories=categories,
				settings=settings, vartree=self)
			self.populated = 1

	def getpath(self, mykey, filename=None):
		return self.dbapi.getpath(mykey, filename=filename)

	def zap(self, mycpv):
		return

	def inject(self, mycpv):
		return

	def get_provide(self, mycpv):
		myprovides = []
		mylines = None
		try:
			mylines, myuse = self.dbapi.aux_get(mycpv, ["PROVIDE", "USE"])
			if mylines:
				myuse = myuse.split()
				mylines = flatten(use_reduce(paren_reduce(mylines), uselist=myuse))
				for myprovide in mylines:
					mys = catpkgsplit(myprovide)
					if not mys:
						mys = myprovide.split("/")
					myprovides += [mys[0] + "/" + mys[1]]
			return myprovides
		except SystemExit as e:
			raise
		except Exception as e:
			mydir = os.path.join(self.root, VDB_PATH, mycpv)
			writemsg(_("\nParse Error reading PROVIDE and USE in '%s'\n") % mydir,
				noiselevel=-1)
			if mylines:
				writemsg(_("Possibly Invalid: '%s'\n") % str(mylines),
					noiselevel=-1)
			writemsg(_("Exception: %s\n\n") % str(e), noiselevel=-1)
			return []

	def get_all_provides(self):
		myprovides = {}
		for node in self.getallcpv():
			for mykey in self.get_provide(node):
				if mykey in myprovides:
					myprovides[mykey] += [node]
				else:
					myprovides[mykey] = [node]
		return myprovides

	def dep_bestmatch(self, mydep, use_cache=1):
		"compatibility method -- all matches, not just visible ones"
		#mymatch=best(match(dep_expand(mydep,self.dbapi),self.dbapi))
		mymatch = best(self.dbapi.match(
			dep_expand(mydep, mydb=self.dbapi, settings=self.settings),
			use_cache=use_cache))
		if mymatch is None:
			return ""
		else:
			return mymatch

	def dep_match(self, mydep, use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch = match(mydep,self.dbapi)
		mymatch = self.dbapi.match(mydep, use_cache=use_cache)
		if mymatch is None:
			return []
		else:
			return mymatch

	def exists_specific(self, cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallcpv(self):
		"""temporary function, probably to be renamed --- Gets a list of all
		category/package-versions installed on the system."""
		return self.dbapi.cpv_all()

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def getebuildpath(self, fullpackage):
		cat, package = catsplit(fullpackage)
		return self.getpath(fullpackage, filename=package+".ebuild")

	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			return self.dbapi.aux_get(mycatpkg, ["SLOT"])[0]
		except KeyError:
			return ""

	def populate(self):
		self.populated=1

class dblink(object):
	"""
	This class provides an interface to the installed package database
	At present this is implemented as a text backend in /var/db/pkg.
	"""

	import re
	_normalize_needed = re.compile(r'.*//.*|^[^/]|.+/$|(^|.*/)\.\.?(/.*|$)')
	_contents_split_counts = {
		"dev": 2,
		"dir": 2,
		"fif": 2,
		"obj": 4,
		"sym": 5
	}

	# When looping over files for merge/unmerge, temporarily yield to the
	# scheduler each time this many files are processed.
	_file_merge_yield_interval = 20

	def __init__(self, cat, pkg, myroot, mysettings, treetype=None,
		vartree=None, blockers=None, scheduler=None):
		"""
		Creates a DBlink object for a given CPV.
		The given CPV may not be present in the database already.
		
		@param cat: Category
		@type cat: String
		@param pkg: Package (PV)
		@type pkg: String
		@param myroot: Typically ${ROOT}
		@type myroot: String (Path)
		@param mysettings: Typically portage.config
		@type mysettings: An instance of portage.config
		@param treetype: one of ['porttree','bintree','vartree']
		@type treetype: String
		@param vartree: an instance of vartree corresponding to myroot.
		@type vartree: vartree
		"""
		
		self.cat = cat
		self.pkg = pkg
		self.mycpv = self.cat + "/" + self.pkg
		self.mysplit = list(catpkgsplit(self.mycpv)[1:])
		self.mysplit[0] = "%s/%s" % (self.cat, self.mysplit[0])
		self.treetype = treetype
		if vartree is None:
			from portage import db
			vartree = db[myroot]["vartree"]
		self.vartree = vartree
		self._blockers = blockers
		self._scheduler = scheduler

		self.dbroot = normalize_path(os.path.join(myroot, VDB_PATH))
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir = self.dbpkgdir

		self._lock_vdb = None

		self.settings = mysettings
		self._verbose = self.settings.get("PORTAGE_VERBOSE") == "1"

		self.myroot=myroot
		protect_obj = ConfigProtect(myroot,
			portage.util.shlex_split(mysettings.get("CONFIG_PROTECT", "")),
			portage.util.shlex_split(
			mysettings.get("CONFIG_PROTECT_MASK", "")))
		self.updateprotect = protect_obj.updateprotect
		self.isprotected = protect_obj.isprotected
		self._installed_instance = None
		self.contentscache = None
		self._contents_inodes = None
		self._contents_basenames = None
		self._linkmap_broken = False
		self._md5_merge_map = {}
		self._hash_key = (self.myroot, self.mycpv)

	def __hash__(self):
		return hash(self._hash_key)

	def __eq__(self, other):
		return isinstance(other, dblink) and \
			self._hash_key == other._hash_key

	def lockdb(self):
		if self._lock_vdb:
			raise AssertionError("Lock already held.")
		# At least the parent needs to exist for the lock file.
		ensure_dirs(self.dbroot)
		self._lock_vdb = lockdir(self.dbroot)

	def unlockdb(self):
		if self._lock_vdb:
			unlockdir(self._lock_vdb)
			self._lock_vdb = None

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir

	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)

	def delete(self):
		"""
		Remove this entry from the database
		"""
		if not os.path.exists(self.dbdir):
			return

		# Check validity of self.dbdir before attempting to remove it.
		if not self.dbdir.startswith(self.dbroot):
			writemsg(_("portage.dblink.delete(): invalid dbdir: %s\n") % \
				self.dbdir, noiselevel=-1)
			return

		shutil.rmtree(self.dbdir)
		# If empty, remove parent category directory.
		try:
			os.rmdir(os.path.dirname(self.dbdir))
		except OSError:
			pass
		self.vartree.dbapi._remove(self)

	def clearcontents(self):
		"""
		For a given db entry (self), erase the CONTENTS values.
		"""
		if os.path.exists(self.dbdir+"/CONTENTS"):
			os.unlink(self.dbdir+"/CONTENTS")

	def _clear_contents_cache(self):
		self.contentscache = None
		self._contents_inodes = None
		self._contents_basenames = None

	def getcontents(self):
		"""
		Get the installed files of a given package (aka what that package installed)
		"""
		contents_file = os.path.join(self.dbdir, "CONTENTS")
		if self.contentscache is not None:
			return self.contentscache
		pkgfiles = {}
		try:
			myc = codecs.open(_unicode_encode(contents_file,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
		except EnvironmentError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			self.contentscache = pkgfiles
			return pkgfiles
		mylines = myc.readlines()
		myc.close()
		null_byte = "\0"
		normalize_needed = self._normalize_needed
		contents_split_counts = self._contents_split_counts
		myroot = self.myroot
		if myroot == os.path.sep:
			myroot = None
		pos = 0
		errors = []
		for pos, line in enumerate(mylines):
			if null_byte in line:
				# Null bytes are a common indication of corruption.
				errors.append((pos + 1, _("Null byte found in CONTENTS entry")))
				continue
			line = line.rstrip("\n")
			# Split on " " so that even file paths that
			# end with spaces can be handled.
			mydat = line.split(" ")
			entry_type = mydat[0] # empty string if line is empty
			correct_split_count = contents_split_counts.get(entry_type)
			if correct_split_count and len(mydat) > correct_split_count:
				# Apparently file paths contain spaces, so reassemble
				# the split have the correct_split_count.
				newsplit = [entry_type]
				spaces_total = len(mydat) - correct_split_count
				if entry_type == "sym":
					try:
						splitter = mydat.index("->", 2, len(mydat) - 2)
					except ValueError:
						errors.append((pos + 1, _("Unrecognized CONTENTS entry")))
						continue
					spaces_in_path = splitter - 2
					spaces_in_target = spaces_total - spaces_in_path
					newsplit.append(" ".join(mydat[1:splitter]))
					newsplit.append("->")
					target_end = splitter + spaces_in_target + 2
					newsplit.append(" ".join(mydat[splitter + 1:target_end]))
					newsplit.extend(mydat[target_end:])
				else:
					path_end = spaces_total + 2
					newsplit.append(" ".join(mydat[1:path_end]))
					newsplit.extend(mydat[path_end:])
				mydat = newsplit

			# we do this so we can remove from non-root filesystems
			# (use the ROOT var to allow maintenance on other partitions)
			try:
				if normalize_needed.match(mydat[1]):
					mydat[1] = normalize_path(mydat[1])
					if not mydat[1].startswith(os.path.sep):
						mydat[1] = os.path.sep + mydat[1]
				if myroot:
					mydat[1] = os.path.join(myroot, mydat[1].lstrip(os.path.sep))
				if mydat[0] == "obj":
					#format: type, mtime, md5sum
					pkgfiles[mydat[1]] = [mydat[0], mydat[3], mydat[2]]
				elif mydat[0] == "dir":
					#format: type
					pkgfiles[mydat[1]] = [mydat[0]]
				elif mydat[0] == "sym":
					#format: type, mtime, dest
					pkgfiles[mydat[1]] = [mydat[0], mydat[4], mydat[3]]
				elif mydat[0] == "dev":
					#format: type
					pkgfiles[mydat[1]] = [mydat[0]]
				elif mydat[0]=="fif":
					#format: type
					pkgfiles[mydat[1]] = [mydat[0]]
				else:
					errors.append((pos + 1, _("Unrecognized CONTENTS entry")))
			except (KeyError, IndexError):
				errors.append((pos + 1, _("Unrecognized CONTENTS entry")))
		if errors:
			writemsg(_("!!! Parse error in '%s'\n") % contents_file, noiselevel=-1)
			for pos, e in errors:
				writemsg(_("!!!   line %d: %s\n") % (pos, e), noiselevel=-1)
		self.contentscache = pkgfiles
		return pkgfiles

	def unmerge(self, pkgfiles=None, trimworld=1, cleanup=1,
		ldpath_mtimes=None, others_in_slot=None):
		"""
		Calls prerm
		Unmerges a given package (CPV)
		calls postrm
		calls cleanrm
		calls env_update
		
		@param pkgfiles: files to unmerge (generally self.getcontents() )
		@type pkgfiles: Dictionary
		@param trimworld: Remove CPV from world file if True, not if False
		@type trimworld: Boolean
		@param cleanup: cleanup to pass to doebuild (see doebuild)
		@type cleanup: Boolean
		@param ldpath_mtimes: mtimes to pass to env_update (see env_update)
		@type ldpath_mtimes: Dictionary
		@param others_in_slot: all dblink instances in this slot, excluding self
		@type others_in_slot: list
		@rtype: Integer
		@returns:
		1. os.EX_OK if everything went well.
		2. return code of the failed phase (for prerm, postrm, cleanrm)
		
		Notes:
		The caller must ensure that lockdb() and unlockdb() are called
		before and after this method.
		"""
		self.vartree.dbapi._bump_mtime(self.mycpv)
		showMessage = self._display_merge
		if self.vartree.dbapi._categories is not None:
			self.vartree.dbapi._categories = None
		# When others_in_slot is supplied, the security check has already been
		# done for this slot, so it shouldn't be repeated until the next
		# replacement or unmerge operation.
		if others_in_slot is None:
			slot = self.vartree.dbapi.aux_get(self.mycpv, ["SLOT"])[0]
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (portage.cpv_getkey(self.mycpv), slot))
			others_in_slot = []
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					self.vartree.root, self.settings, vartree=self.vartree,
					treetype="vartree"))

			retval = self._security_check([self] + others_in_slot)
			if retval:
				return retval

		contents = self.getcontents()
		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath = None
		ebuild_phase = "prerm"
		log_path = None
		mystuff = os.listdir(self.dbdir)
		for x in mystuff:
			if x.endswith(".ebuild"):
				myebuildpath = os.path.join(self.dbdir, self.pkg + ".ebuild")
				if x[:-7] != self.pkg:
					# Clean up after vardbapi.move_ent() breakage in
					# portage versions before 2.1.2
					os.rename(os.path.join(self.dbdir, x), myebuildpath)
					write_atomic(os.path.join(self.dbdir, "PF"), self.pkg+"\n")
				break

		self.settings.setcpv(self.mycpv, mydb=self.vartree.dbapi)
		if myebuildpath:
			try:
				doebuild_environment(myebuildpath, "prerm", self.myroot,
					self.settings, 0, 0, self.vartree.dbapi)
			except UnsupportedAPIException as e:
				# Sometimes this happens due to corruption of the EAPI file.
				writemsg(_("!!! FAILED prerm: %s\n") % \
					os.path.join(self.dbdir, "EAPI"), noiselevel=-1)
				writemsg("%s\n" % str(e), noiselevel=-1)
				myebuildpath = None
			else:
				catdir = os.path.dirname(self.settings["PORTAGE_BUILDDIR"])
				ensure_dirs(os.path.dirname(catdir), uid=portage_uid,
					gid=portage_gid, mode=0o70, mask=0)

		builddir_lock = None
		catdir_lock = None
		scheduler = self._scheduler
		retval = -1
		failures = 0
		try:
			if myebuildpath:
				catdir_lock = lockdir(catdir)
				ensure_dirs(catdir,
					uid=portage_uid, gid=portage_gid,
					mode=0o70, mask=0)
				builddir_lock = lockdir(
					self.settings["PORTAGE_BUILDDIR"])
				try:
					unlockdir(catdir_lock)
				finally:
					catdir_lock = None

				prepare_build_dirs(self.myroot, self.settings, 1)
				log_path = self.settings.get("PORTAGE_LOG_FILE")

				if scheduler is None:
					retval = doebuild(myebuildpath, ebuild_phase, self.myroot,
						self.settings, cleanup=cleanup, use_cache=0,
						mydbapi=self.vartree.dbapi, tree=self.treetype,
						vartree=self.vartree)
				else:
					retval = scheduler.dblinkEbuildPhase(
						self, self.vartree.dbapi, myebuildpath, ebuild_phase)

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					failures += 1
					writemsg(_("!!! FAILED prerm: %s\n") % retval, noiselevel=-1)

			self._unmerge_pkgfiles(pkgfiles, others_in_slot)
			self._clear_contents_cache()

			# Remove the registration of preserved libs for this pkg instance
			plib_registry = self.vartree.dbapi.plib_registry
			plib_registry.unregister(self.mycpv, self.settings["SLOT"],
				self.vartree.dbapi.cpv_counter(self.mycpv))

			if myebuildpath:
				ebuild_phase = "postrm"
				if scheduler is None:
					retval = doebuild(myebuildpath, ebuild_phase, self.myroot,
						self.settings, use_cache=0, tree=self.treetype,
						mydbapi=self.vartree.dbapi, vartree=self.vartree)
				else:
					retval = scheduler.dblinkEbuildPhase(
						self, self.vartree.dbapi, myebuildpath, ebuild_phase)

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					failures += 1
					writemsg(_("!!! FAILED postrm: %s\n") % retval, noiselevel=-1)

			# Skip this if another package in the same slot has just been
			# merged on top of this package, since the other package has
			# already called LinkageMap.rebuild() and passed it's NEEDED file
			# in as an argument.
			if not others_in_slot:
				self._linkmap_rebuild(exclude_pkgs=(self.mycpv,))

			# remove preserved libraries that don't have any consumers left
			cpv_lib_map = self._find_unused_preserved_libs()
			if cpv_lib_map:
				self._remove_preserved_libs(cpv_lib_map)
				for cpv, removed in cpv_lib_map.items():
					if not self.vartree.dbapi.cpv_exists(cpv):
						for dblnk in others_in_slot:
							if dblnk.mycpv == cpv:
								# This one just got merged so it doesn't
								# register with cpv_exists() yet.
								self.vartree.dbapi.removeFromContents(
									dblnk, removed)
								break
						continue
					self.vartree.dbapi.removeFromContents(cpv, removed)
			else:
				# Prune any preserved libs that may have
				# been unmerged with this package.
				self.vartree.dbapi.plib_registry.pruneNonExisting()

		finally:
			self.vartree.dbapi._bump_mtime(self.mycpv)
			if builddir_lock:
				try:
					if myebuildpath:
						if retval != os.EX_OK:
							msg_lines = []
							msg = _("The '%(ebuild_phase)s' "
							"phase of the '%(cpv)s' package "
							"has failed with exit value %(retval)s.") % \
							{"ebuild_phase":ebuild_phase, "cpv":self.mycpv,
							"retval":retval}
							from textwrap import wrap
							msg_lines.extend(wrap(msg, 72))
							msg_lines.append("")

							ebuild_name = os.path.basename(myebuildpath)
							ebuild_dir = os.path.dirname(myebuildpath)
							msg = _("The problem occurred while executing "
							"the ebuild file named '%(ebuild_name)s' "
							"located in the '%(ebuild_dir)s' directory. "
							"If necessary, manually remove "
							"the environment.bz2 file and/or the "
							"ebuild file located in that directory.") % \
							{"ebuild_name":ebuild_name, "ebuild_dir":ebuild_dir}
							msg_lines.extend(wrap(msg, 72))
							msg_lines.append("")

							msg = _("Removal "
							"of the environment.bz2 file is "
							"preferred since it may allow the "
							"removal phases to execute successfully. "
							"The ebuild will be "
							"sourced and the eclasses "
							"from the current portage tree will be used "
							"when necessary. Removal of "
							"the ebuild file will cause the "
							"pkg_prerm() and pkg_postrm() removal "
							"phases to be skipped entirely.")
							msg_lines.extend(wrap(msg, 72))

							self._eerror(ebuild_phase, msg_lines)

						# process logs created during pre/postrm
						elog_process(self.mycpv, self.settings)
						if retval == os.EX_OK:
							if scheduler is None:
								doebuild(myebuildpath, "cleanrm", self.myroot,
									self.settings, tree="vartree",
									mydbapi=self.vartree.dbapi,
									vartree=self.vartree)
							else:
								scheduler.dblinkEbuildPhase(
									self, self.vartree.dbapi,
									myebuildpath, "cleanrm")
				finally:
					unlockdir(builddir_lock)
			try:
				if myebuildpath and not catdir_lock:
					# Lock catdir for removal if empty.
					catdir_lock = lockdir(catdir)
			finally:
				if catdir_lock:
					try:
						os.rmdir(catdir)
					except OSError as e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					unlockdir(catdir_lock)

		if log_path is not None:

			if not failures and 'unmerge-logs' not in self.settings.features:
				try:
					os.unlink(log_path)
				except OSError:
					pass

			try:
				st = os.stat(log_path)
			except OSError:
				pass
			else:
				if st.st_size == 0:
					try:
						os.unlink(log_path)
					except OSError:
						pass

		if log_path is not None and os.path.exists(log_path):
			# Restore this since it gets lost somewhere above and it
			# needs to be set for _display_merge() to be able to log.
			# Note that the log isn't necessarily supposed to exist
			# since if PORT_LOGDIR is unset then it's a temp file
			# so it gets cleaned above.
			self.settings["PORTAGE_LOG_FILE"] = log_path
		else:
			self.settings.pop("PORTAGE_LOG_FILE", None)

		env_update(target_root=self.myroot, prev_mtimes=ldpath_mtimes,
			contents=contents, env=self.settings.environ(),
			writemsg_level=self._display_merge)
		return os.EX_OK

	def _display_merge(self, msg, level=0, noiselevel=0):
		if not self._verbose and noiselevel >= 0 and level < logging.WARN:
			return
		if self._scheduler is not None:
			self._scheduler.dblinkDisplayMerge(self, msg,
				level=level, noiselevel=noiselevel)
			return
		writemsg_level(msg, level=level, noiselevel=noiselevel)

	def _unmerge_pkgfiles(self, pkgfiles, others_in_slot):
		"""
		
		Unmerges the contents of a package from the liveFS
		Removes the VDB entry for self
		
		@param pkgfiles: typically self.getcontents()
		@type pkgfiles: Dictionary { filename: [ 'type', '?', 'md5sum' ] }
		@param others_in_slot: all dblink instances in this slot, excluding self
		@type others_in_slot: list
		@rtype: None
		"""

		os = _os_merge
		perf_md5 = perform_md5
		showMessage = self._display_merge
		scheduler = self._scheduler

		if not pkgfiles:
			showMessage(_("No package files given... Grabbing a set.\n"))
			pkgfiles = self.getcontents()

		if others_in_slot is None:
			others_in_slot = []
			slot = self.vartree.dbapi.aux_get(self.mycpv, ["SLOT"])[0]
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (portage.cpv_getkey(self.mycpv), slot))
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					self.vartree.root, self.settings,
					vartree=self.vartree, treetype="vartree"))

		dest_root = normalize_path(self.vartree.root).rstrip(os.path.sep) + \
			os.path.sep
		dest_root_len = len(dest_root) - 1

		conf_mem_file = os.path.join(dest_root, CONFIG_MEMORY_FILE)
		cfgfiledict = grabdict(conf_mem_file)
		stale_confmem = []

		unmerge_orphans = "unmerge-orphans" in self.settings.features

		if pkgfiles:
			self.updateprotect()
			mykeys = list(pkgfiles)
			mykeys.sort()
			mykeys.reverse()

			#process symlinks second-to-last, directories last.
			mydirs = []
			ignored_unlink_errnos = (
				errno.EBUSY, errno.ENOENT,
				errno.ENOTDIR, errno.EISDIR)
			ignored_rmdir_errnos = (
				errno.EEXIST, errno.ENOTEMPTY,
				errno.EBUSY, errno.ENOENT,
				errno.ENOTDIR, errno.EISDIR)
			modprotect = os.path.join(self.vartree.root, "lib/modules/")

			def unlink(file_name, lstatobj):
				if bsd_chflags:
					if lstatobj.st_flags != 0:
						bsd_chflags.lchflags(file_name, 0)
					parent_name = os.path.dirname(file_name)
					# Use normal stat/chflags for the parent since we want to
					# follow any symlinks to the real parent directory.
					pflags = os.stat(parent_name).st_flags
					if pflags != 0:
						bsd_chflags.chflags(parent_name, 0)
				try:
					if not stat.S_ISLNK(lstatobj.st_mode):
						# Remove permissions to ensure that any hardlinks to
						# suid/sgid files are rendered harmless.
						os.chmod(file_name, 0)
					os.unlink(file_name)
				except OSError as ose:
					# If the chmod or unlink fails, you are in trouble.
					# With Prefix this can be because the file is owned
					# by someone else (a screwup by root?), on a normal
					# system maybe filesystem corruption.  In any case,
					# if we backtrace and die here, we leave the system
					# in a totally undefined state, hence we just bleed
					# like hell and continue to hopefully finish all our
					# administrative and pkg_postinst stuff.
					self._eerror("postrm", 
						["Could not chmod or unlink '%s': %s" % \
						(file_name, ose)])
				finally:
					if bsd_chflags and pflags != 0:
						# Restore the parent flags we saved before unlinking
						bsd_chflags.chflags(parent_name, pflags)

			def show_unmerge(zing, desc, file_type, file_name):
					showMessage("%s %s %s %s\n" % \
						(zing, desc.ljust(8), file_type, file_name))

			unmerge_desc = {}
			unmerge_desc["cfgpro"] = _("cfgpro")
			unmerge_desc["replaced"] = _("replaced")
			unmerge_desc["!dir"] = _("!dir")
			unmerge_desc["!empty"] = _("!empty")
			unmerge_desc["!fif"] = _("!fif")
			unmerge_desc["!found"] = _("!found")
			unmerge_desc["!md5"] = _("!md5")
			unmerge_desc["!mtime"] = _("!mtime")
			unmerge_desc["!obj"] = _("!obj")
			unmerge_desc["!sym"] = _("!sym")

			for i, objkey in enumerate(mykeys):

				if scheduler is not None and \
					0 == i % self._file_merge_yield_interval:
					scheduler.scheduleYield()

				obj = normalize_path(objkey)
				if os is _os_merge:
					try:
						_unicode_encode(obj,
							encoding=_encodings['merge'], errors='strict')
					except UnicodeEncodeError:
						# The package appears to have been merged with a 
						# different value of sys.getfilesystemencoding(),
						# so fall back to utf_8 if appropriate.
						try:
							_unicode_encode(obj,
								encoding=_encodings['fs'], errors='strict')
						except UnicodeEncodeError:
							pass
						else:
							os = portage.os
							perf_md5 = portage.checksum.perform_md5

				file_data = pkgfiles[objkey]
				file_type = file_data[0]
				statobj = None
				try:
					statobj = os.stat(obj)
				except OSError:
					pass
				lstatobj = None
				try:
					lstatobj = os.lstat(obj)
				except (OSError, AttributeError):
					pass
				islink = lstatobj is not None and stat.S_ISLNK(lstatobj.st_mode)
				if lstatobj is None:
						show_unmerge("---", unmerge_desc["!found"], file_type, obj)
						continue
				if obj.startswith(dest_root):
					relative_path = obj[dest_root_len:]
					is_owned = False
					for dblnk in others_in_slot:
						if dblnk.isowner(relative_path, dest_root):
							is_owned = True
							break
					if is_owned:
						# A new instance of this package claims the file, so
						# don't unmerge it.
						show_unmerge("---", unmerge_desc["replaced"], file_type, obj)
						continue
					elif relative_path in cfgfiledict:
						stale_confmem.append(relative_path)
				# next line includes a tweak to protect modules from being unmerged,
				# but we don't protect modules from being overwritten if they are
				# upgraded. We effectively only want one half of the config protection
				# functionality for /lib/modules. For portage-ng both capabilities
				# should be able to be independently specified.
				# TODO: For rebuilds, re-parent previous modules to the new
				# installed instance (so they are not orphans). For normal
				# uninstall (not rebuild/reinstall), remove the modules along
				# with all other files (leave no orphans).
				if obj.startswith(modprotect):
					show_unmerge("---", unmerge_desc["cfgpro"], file_type, obj)
					continue

				# Don't unlink symlinks to directories here since that can
				# remove /lib and /usr/lib symlinks.
				if unmerge_orphans and \
					lstatobj and not stat.S_ISDIR(lstatobj.st_mode) and \
					not (islink and statobj and stat.S_ISDIR(statobj.st_mode)) and \
					not self.isprotected(obj):
					try:
						unlink(obj, lstatobj)
					except EnvironmentError as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
					continue

				lmtime = str(lstatobj[stat.ST_MTIME])
				if (pkgfiles[objkey][0] not in ("dir", "fif", "dev")) and (lmtime != pkgfiles[objkey][1]):
					show_unmerge("---", unmerge_desc["!mtime"], file_type, obj)
					continue

				if pkgfiles[objkey][0] == "dir":
					if lstatobj is None or not stat.S_ISDIR(lstatobj.st_mode):
						show_unmerge("---", unmerge_desc["!dir"], file_type, obj)
						continue
					mydirs.append(obj)
				elif pkgfiles[objkey][0] == "sym":
					if not islink:
						show_unmerge("---", unmerge_desc["!sym"], file_type, obj)
						continue
					# Go ahead and unlink symlinks to directories here when
					# they're actually recorded as symlinks in the contents.
					# Normally, symlinks such as /lib -> lib64 are not recorded
					# as symlinks in the contents of a package.  If a package
					# installs something into ${D}/lib/, it is recorded in the
					# contents as a directory even if it happens to correspond
					# to a symlink when it's merged to the live filesystem.
					try:
						unlink(obj, lstatobj)
						show_unmerge("<<<", "", file_type, obj)
					except (OSError, IOError) as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
						show_unmerge("!!!", "", file_type, obj)
				elif pkgfiles[objkey][0] == "obj":
					if statobj is None or not stat.S_ISREG(statobj.st_mode):
						show_unmerge("---", unmerge_desc["!obj"], file_type, obj)
						continue
					mymd5 = None
					try:
						mymd5 = perf_md5(obj, calc_prelink=1)
					except FileNotFound as e:
						# the file has disappeared between now and our stat call
						show_unmerge("---", unmerge_desc["!obj"], file_type, obj)
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != pkgfiles[objkey][2].lower():
						show_unmerge("---", unmerge_desc["!md5"], file_type, obj)
						continue
					try:
						unlink(obj, lstatobj)
					except (OSError, IOError) as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
				elif pkgfiles[objkey][0] == "fif":
					if not stat.S_ISFIFO(lstatobj[stat.ST_MODE]):
						show_unmerge("---", unmerge_desc["!fif"], file_type, obj)
						continue
					show_unmerge("---", "", file_type, obj)
				elif pkgfiles[objkey][0] == "dev":
					show_unmerge("---", "", file_type, obj)

			mydirs.sort()
			mydirs.reverse()

			for obj in mydirs:
				try:
					if bsd_chflags:
						lstatobj = os.lstat(obj)
						if lstatobj.st_flags != 0:
							bsd_chflags.lchflags(obj, 0)
						parent_name = os.path.dirname(obj)
						# Use normal stat/chflags for the parent since we want to
						# follow any symlinks to the real parent directory.
						pflags = os.stat(parent_name).st_flags
						if pflags != 0:
							bsd_chflags.chflags(parent_name, 0)
					try:
						os.rmdir(obj)
					finally:
						if bsd_chflags and pflags != 0:
							# Restore the parent flags we saved before unlinking
							bsd_chflags.chflags(parent_name, pflags)
					show_unmerge("<<<", "", "dir", obj)
				except EnvironmentError as e:
					if e.errno not in ignored_rmdir_errnos:
						raise
					if e.errno != errno.ENOENT:
						show_unmerge("---", unmerge_desc["!empty"], "dir", obj)
					del e

		# Remove stale entries from config memory.
		if stale_confmem:
			for filename in stale_confmem:
				del cfgfiledict[filename]
			writedict(cfgfiledict, conf_mem_file)

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

	def isowner(self, filename, destroot):
		""" 
		Check if a file belongs to this package. This may
		result in a stat call for the parent directory of
		every installed file, since the inode numbers are
		used to work around the problem of ambiguous paths
		caused by symlinked directories. The results of
		stat calls are cached to optimize multiple calls
		to this method.

		@param filename:
		@type filename:
		@param destroot:
		@type destroot:
		@rtype: Boolean
		@returns:
		1. True if this package owns the file.
		2. False if this package does not own the file.
		"""
		return bool(self._match_contents(filename, destroot))

	def _match_contents(self, filename, destroot):
		"""
		The matching contents entry is returned, which is useful
		since the path may differ from the one given by the caller,
		due to symlinks.

		@rtype: String
		@return: the contents entry corresponding to the given path, or False
			if the file is not owned by this package.
		"""

		filename = _unicode_decode(filename,
			encoding=_encodings['content'], errors='strict')

		destroot = _unicode_decode(destroot,
			encoding=_encodings['content'], errors='strict')

		# The given filename argument might have a different encoding than the
		# the filenames contained in the contents, so use separate wrapped os
		# modules for each. The basename is more likely to contain non-ascii
		# characters than the directory path, so use os_filename_arg for all
		# operations involving the basename of the filename arg.
		os_filename_arg = _os_merge
		os = _os_merge

		try:
			_unicode_encode(filename,
				encoding=_encodings['merge'], errors='strict')
		except UnicodeEncodeError:
			# The package appears to have been merged with a
			# different value of sys.getfilesystemencoding(),
			# so fall back to utf_8 if appropriate.
			try:
				_unicode_encode(filename,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeEncodeError:
				pass
			else:
				os_filename_arg = portage.os

		destfile = normalize_path(
			os_filename_arg.path.join(destroot,
			filename.lstrip(os_filename_arg.path.sep)))

		pkgfiles = self.getcontents()
		if pkgfiles and destfile in pkgfiles:
			return destfile
		if pkgfiles:
			basename = os_filename_arg.path.basename(destfile)
			if self._contents_basenames is None:

				try:
					for x in pkgfiles:
						_unicode_encode(x,
							encoding=_encodings['merge'],
							errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						for x in pkgfiles:
							_unicode_encode(x,
								encoding=_encodings['fs'],
								errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

				self._contents_basenames = set(
					os.path.basename(x) for x in pkgfiles)
			if basename not in self._contents_basenames:
				# This is a shortcut that, in most cases, allows us to
				# eliminate this package as an owner without the need
				# to examine inode numbers of parent directories.
				return False

			# Use stat rather than lstat since we want to follow
			# any symlinks to the real parent directory.
			parent_path = os_filename_arg.path.dirname(destfile)
			try:
				parent_stat = os_filename_arg.stat(parent_path)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				return False
			if self._contents_inodes is None:

				if os is _os_merge:
					try:
						for x in pkgfiles:
							_unicode_encode(x,
								encoding=_encodings['merge'],
								errors='strict')
					except UnicodeEncodeError:
						# The package appears to have been merged with a 
						# different value of sys.getfilesystemencoding(),
						# so fall back to utf_8 if appropriate.
						try:
							for x in pkgfiles:
								_unicode_encode(x,
									encoding=_encodings['fs'],
									errors='strict')
						except UnicodeEncodeError:
							pass
						else:
							os = portage.os

				self._contents_inodes = {}
				parent_paths = set()
				for x in pkgfiles:
					p_path = os.path.dirname(x)
					if p_path in parent_paths:
						continue
					parent_paths.add(p_path)
					try:
						s = os.stat(p_path)
					except OSError:
						pass
					else:
						inode_key = (s.st_dev, s.st_ino)
						# Use lists of paths in case multiple
						# paths reference the same inode.
						p_path_list = self._contents_inodes.get(inode_key)
						if p_path_list is None:
							p_path_list = []
							self._contents_inodes[inode_key] = p_path_list
						if p_path not in p_path_list:
							p_path_list.append(p_path)

			p_path_list = self._contents_inodes.get(
				(parent_stat.st_dev, parent_stat.st_ino))
			if p_path_list:
				for p_path in p_path_list:
					x = os_filename_arg.path.join(p_path, basename)
					if x in pkgfiles:
						return x

		return False

	def _linkmap_rebuild(self, **kwargs):
		if self._linkmap_broken:
			return
		try:
			self.vartree.dbapi.linkmap.rebuild(**kwargs)
		except CommandNotFound as e:
			self._linkmap_broken = True
			self._display_merge(_("!!! Disabling preserve-libs " \
				"due to error: Command Not Found: %s\n") % (e,),
				level=logging.ERROR, noiselevel=-1)

	def _find_libs_to_preserve(self):
		"""
		Get set of relative paths for libraries to be preserved. The file
		paths are selected from self._installed_instance.getcontents().
		"""
		if self._linkmap_broken or not \
			(self._installed_instance is not None and \
			"preserve-libs" in self.settings.features):
			return None

		os = _os_merge
		linkmap = self.vartree.dbapi.linkmap
		installed_instance = self._installed_instance
		old_contents = installed_instance.getcontents()
		root = self.myroot
		root_len = len(root) - 1
		lib_graph = digraph()
		path_node_map = {}

		def path_to_node(path):
			node = path_node_map.get(path)
			if node is None:
				node = LinkageMap._LibGraphNode(path, root)
				alt_path_node = lib_graph.get(node)
				if alt_path_node is not None:
					node = alt_path_node
				node.alt_paths.add(path)
				path_node_map[path] = node
			return node

		consumer_map = {}
		provider_nodes = set()
		# Create provider nodes and add them to the graph.
		for f_abs in old_contents:

			if os is _os_merge:
				try:
					_unicode_encode(f_abs,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a 
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						_unicode_encode(f_abs,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

			f = f_abs[root_len:]
			if self.isowner(f, root):
				continue
			try:
				consumers = linkmap.findConsumers(f)
			except KeyError:
				continue
			if not consumers:
				continue
			provider_node = path_to_node(f)
			lib_graph.add(provider_node, None)
			provider_nodes.add(provider_node)
			consumer_map[provider_node] = consumers

		# Create consumer nodes and add them to the graph.
		# Note that consumers can also be providers.
		for provider_node, consumers in consumer_map.items():
			for c in consumers:
				if self.isowner(c, root):
					continue
				consumer_node = path_to_node(c)
				if installed_instance.isowner(c, root) and \
					consumer_node not in provider_nodes:
					# This is not a provider, so it will be uninstalled.
					continue
				lib_graph.add(provider_node, consumer_node)

		# Locate nodes which should be preserved. They consist of all
		# providers that are reachable from consumers that are not
		# providers themselves.
		preserve_nodes = set()
		for consumer_node in lib_graph.root_nodes():
			if consumer_node in provider_nodes:
				continue
			# Preserve all providers that are reachable from this consumer.
			node_stack = lib_graph.child_nodes(consumer_node)
			while node_stack:
				provider_node = node_stack.pop()
				if provider_node in preserve_nodes:
					continue
				preserve_nodes.add(provider_node)
				node_stack.extend(lib_graph.child_nodes(provider_node))

		preserve_paths = set()
		for preserve_node in preserve_nodes:
			# Make sure that at least one of the paths is not a symlink.
			# This prevents symlinks from being erroneously preserved by
			# themselves when the old instance installed symlinks that
			# the new instance does not install.
			have_lib = False
			for f in preserve_node.alt_paths:
				f_abs = os.path.join(root, f.lstrip(os.sep))
				try:
					if stat.S_ISREG(os.lstat(f_abs).st_mode):
						have_lib = True
						break
				except OSError:
					continue

			if have_lib:
				preserve_paths.update(preserve_node.alt_paths)

		return preserve_paths

	def _add_preserve_libs_to_contents(self, preserve_paths):
		"""
		Preserve libs returned from _find_libs_to_preserve().
		"""

		if not preserve_paths:
			return

		os = _os_merge
		showMessage = self._display_merge
		root = self.myroot

		# Copy contents entries from the old package to the new one.
		new_contents = self.getcontents().copy()
		old_contents = self._installed_instance.getcontents()
		for f in sorted(preserve_paths):
			f = _unicode_decode(f,
				encoding=_encodings['content'], errors='strict')
			f_abs = os.path.join(root, f.lstrip(os.sep))
			contents_entry = old_contents.get(f_abs)
			if contents_entry is None:
				# This will probably never happen, but it might if one of the
				# paths returned from findConsumers() refers to one of the libs
				# that should be preserved yet the path is not listed in the
				# contents. Such a path might belong to some other package, so
				# it shouldn't be preserved here.
				showMessage(_("!!! File '%s' will not be preserved "
					"due to missing contents entry\n") % (f_abs,),
					level=logging.ERROR, noiselevel=-1)
				preserve_paths.remove(f)
				continue
			new_contents[f_abs] = contents_entry
			obj_type = contents_entry[0]
			showMessage(_(">>> needed    %s %s\n") % (obj_type, f_abs),
				noiselevel=-1)
			# Add parent directories to contents if necessary.
			parent_dir = os.path.dirname(f_abs)
			while len(parent_dir) > len(root):
				new_contents[parent_dir] = ["dir"]
				prev = parent_dir
				parent_dir = os.path.dirname(parent_dir)
				if prev == parent_dir:
					break
		outfile = atomic_ofstream(os.path.join(self.dbtmpdir, "CONTENTS"))
		write_contents(new_contents, root, outfile)
		outfile.close()
		self._clear_contents_cache()

	def _find_unused_preserved_libs(self):
		"""
		Find preserved libraries that don't have any consumers left.
		"""

		if self._linkmap_broken:
			return {}

		# Since preserved libraries can be consumers of other preserved
		# libraries, use a graph to track consumer relationships.
		plib_dict = self.vartree.dbapi.plib_registry.getPreservedLibs()
		lib_graph = digraph()
		preserved_nodes = set()
		preserved_paths = set()
		path_cpv_map = {}
		path_node_map = {}
		root = self.myroot

		def path_to_node(path):
			node = path_node_map.get(path)
			if node is None:
				node = LinkageMap._LibGraphNode(path, root)
				alt_path_node = lib_graph.get(node)
				if alt_path_node is not None:
					node = alt_path_node
				node.alt_paths.add(path)
				path_node_map[path] = node
			return node

		linkmap = self.vartree.dbapi.linkmap
		for cpv, plibs in plib_dict.items():
			for f in plibs:
				path_cpv_map[f] = cpv
				preserved_node = path_to_node(f)
				if not preserved_node.file_exists():
					continue
				lib_graph.add(preserved_node, None)
				preserved_paths.add(f)
				preserved_nodes.add(preserved_node)
				for c in self.vartree.dbapi.linkmap.findConsumers(f):
					consumer_node = path_to_node(c)
					if not consumer_node.file_exists():
						continue
					# Note that consumers may also be providers.
					lib_graph.add(preserved_node, consumer_node)

		# Eliminate consumers having providers with the same soname as an
		# installed library that is not preserved. This eliminates
		# libraries that are erroneously preserved due to a move from one
		# directory to another.
		provider_cache = {}
		for preserved_node in preserved_nodes:
			soname = linkmap.getSoname(preserved_node)
			for consumer_node in lib_graph.parent_nodes(preserved_node):
				if consumer_node in preserved_nodes:
					continue
				providers = provider_cache.get(consumer_node)
				if providers is None:
					providers = linkmap.findProviders(consumer_node)
					provider_cache[consumer_node] = providers
				providers = providers.get(soname)
				if providers is None:
					continue
				for provider in providers:
					if provider in preserved_paths:
						continue
					provider_node = path_to_node(provider)
					if not provider_node.file_exists():
						continue
					if provider_node in preserved_nodes:
						continue
					# An alternative provider seems to be
					# installed, so drop this edge.
					lib_graph.remove_edge(preserved_node, consumer_node)
					break

		cpv_lib_map = {}
		while not lib_graph.empty():
			root_nodes = preserved_nodes.intersection(lib_graph.root_nodes())
			if not root_nodes:
				break
			lib_graph.difference_update(root_nodes)
			unlink_list = set()
			for node in root_nodes:
				unlink_list.update(node.alt_paths)
			unlink_list = sorted(unlink_list)
			for obj in unlink_list:
				cpv = path_cpv_map.get(obj)
				if cpv is None:
					# This means that a symlink is in the preserved libs
					# registry, but the actual lib it points to is not.
					self._display_merge(_("!!! symlink to lib is preserved, "
						"but not the lib itself:\n!!! '%s'\n") % (obj,),
						level=logging.ERROR, noiselevel=-1)
					continue
				removed = cpv_lib_map.get(cpv)
				if removed is None:
					removed = set()
					cpv_lib_map[cpv] = removed
				removed.add(obj)

		return cpv_lib_map

	def _remove_preserved_libs(self, cpv_lib_map):
		"""
		Remove files returned from _find_unused_preserved_libs().
		"""

		os = _os_merge

		files_to_remove = set()
		for files in cpv_lib_map.values():
			files_to_remove.update(files)
		files_to_remove = sorted(files_to_remove)
		showMessage = self._display_merge
		root = self.myroot

		parent_dirs = set()
		for obj in files_to_remove:
			obj = os.path.join(root, obj.lstrip(os.sep))
			parent_dirs.add(os.path.dirname(obj))
			if os.path.islink(obj):
				obj_type = _("sym")
			else:
				obj_type = _("obj")
			try:
				os.unlink(obj)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
			else:
				showMessage(_("<<< !needed  %s %s\n") % (obj_type, obj),
					noiselevel=-1)

		# Remove empty parent directories if possible.
		while parent_dirs:
			x = parent_dirs.pop()
			while True:
				try:
					os.rmdir(x)
				except OSError:
					break
				prev = x
				x = os.path.dirname(x)
				if x == prev:
					break

		self.vartree.dbapi.plib_registry.pruneNonExisting()

	def _collision_protect(self, srcroot, destroot, mypkglist, mycontents):

			os = _os_merge

			collision_ignore = set([normalize_path(myignore) for myignore in \
				portage.util.shlex_split(
				self.settings.get("COLLISION_IGNORE", ""))])

			# For collisions with preserved libraries, the current package
			# will assume ownership and the libraries will be unregistered.
			plib_dict = self.vartree.dbapi.plib_registry.getPreservedLibs()
			plib_cpv_map = {}
			plib_paths = set()
			for cpv, paths in plib_dict.items():
				plib_paths.update(paths)
				for f in paths:
					plib_cpv_map[f] = cpv
			plib_inodes = self._lstat_inode_map(plib_paths)
			plib_collisions = {}

			showMessage = self._display_merge
			scheduler = self._scheduler
			stopmerge = False
			collisions = []
			destroot = normalize_path(destroot).rstrip(os.path.sep) + \
				os.path.sep
			showMessage(_(" %s checking %d files for package collisions\n") % \
				(colorize("GOOD", "*"), len(mycontents)))
			for i, f in enumerate(mycontents):
				if i % 1000 == 0 and i != 0:
					showMessage(_("%d files checked ...\n") % i)

				if scheduler is not None and \
					0 == i % self._file_merge_yield_interval:
					scheduler.scheduleYield()

				dest_path = normalize_path(
					os.path.join(destroot, f.lstrip(os.path.sep)))
				try:
					dest_lstat = os.lstat(dest_path)
				except EnvironmentError as e:
					if e.errno == errno.ENOENT:
						del e
						continue
					elif e.errno == errno.ENOTDIR:
						del e
						# A non-directory is in a location where this package
						# expects to have a directory.
						dest_lstat = None
						parent_path = dest_path
						while len(parent_path) > len(destroot):
							parent_path = os.path.dirname(parent_path)
							try:
								dest_lstat = os.lstat(parent_path)
								break
							except EnvironmentError as e:
								if e.errno != errno.ENOTDIR:
									raise
								del e
						if not dest_lstat:
							raise AssertionError(
								"unable to find non-directory " + \
								"parent for '%s'" % dest_path)
						dest_path = parent_path
						f = os.path.sep + dest_path[len(destroot):]
						if f in collisions:
							continue
					else:
						raise
				if f[0] != "/":
					f="/"+f

				plibs = plib_inodes.get((dest_lstat.st_dev, dest_lstat.st_ino))
				if plibs:
					for path in plibs:
						cpv = plib_cpv_map[path]
						paths = plib_collisions.get(cpv)
						if paths is None:
							paths = set()
							plib_collisions[cpv] = paths
						paths.add(path)
					# The current package will assume ownership and the
					# libraries will be unregistered, so exclude this
					# path from the normal collisions.
					continue

				isowned = False
				full_path = os.path.join(destroot, f.lstrip(os.path.sep))
				for ver in mypkglist:
					if ver.isowner(f, destroot):
						isowned = True
						break
				if not isowned and self.isprotected(full_path):
					isowned = True
				if not isowned:
					stopmerge = True
					if collision_ignore:
						if f in collision_ignore:
							stopmerge = False
						else:
							for myignore in collision_ignore:
								if f.startswith(myignore + os.path.sep):
									stopmerge = False
									break
					if stopmerge:
						collisions.append(f)
			return collisions, plib_collisions

	def _lstat_inode_map(self, path_iter):
		"""
		Use lstat to create a map of the form:
		  {(st_dev, st_ino) : set([path1, path2, ...])}
		Multiple paths may reference the same inode due to hardlinks.
		All lstat() calls are relative to self.myroot.
		"""

		os = _os_merge

		root = self.myroot
		inode_map = {}
		for f in path_iter:
			path = os.path.join(root, f.lstrip(os.sep))
			try:
				st = os.lstat(path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ENOTDIR):
					raise
				del e
				continue
			key = (st.st_dev, st.st_ino)
			paths = inode_map.get(key)
			if paths is None:
				paths = set()
				inode_map[key] = paths
			paths.add(f)
		return inode_map

	def _security_check(self, installed_instances):
		if not installed_instances:
			return 0

		os = _os_merge

		showMessage = self._display_merge
		scheduler = self._scheduler

		file_paths = set()
		for dblnk in installed_instances:
			file_paths.update(dblnk.getcontents())
		inode_map = {}
		real_paths = set()
		for i, path in enumerate(file_paths):

			if scheduler is not None and \
				0 == i % self._file_merge_yield_interval:
				scheduler.scheduleYield()

			if os is _os_merge:
				try:
					_unicode_encode(path,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a 
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						_unicode_encode(path,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

			try:
				s = os.lstat(path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ENOTDIR):
					raise
				del e
				continue
			if not stat.S_ISREG(s.st_mode):
				continue
			path = os.path.realpath(path)
			if path in real_paths:
				continue
			real_paths.add(path)
			if s.st_nlink > 1 and \
				s.st_mode & (stat.S_ISUID | stat.S_ISGID):
				k = (s.st_dev, s.st_ino)
				inode_map.setdefault(k, []).append((path, s))
		suspicious_hardlinks = []
		for path_list in inode_map.values():
			path, s = path_list[0]
			if len(path_list) == s.st_nlink:
				# All hardlinks seem to be owned by this package.
				continue
			suspicious_hardlinks.append(path_list)
		if not suspicious_hardlinks:
			return 0

		msg = []
		msg.append(_("suid/sgid file(s) "
			"with suspicious hardlink(s):"))
		msg.append("")
		for path_list in suspicious_hardlinks:
			for path, s in path_list:
				msg.append("\t%s" % path)
		msg.append("")
		msg.append(_("See the Gentoo Security Handbook " 
			"guide for advice on how to proceed."))

		self._eerror("preinst", msg)

		return 1

	def _eqawarn(self, phase, lines):
		from portage.elog.messages import eqawarn as _eqawarn
		if self._scheduler is None:
			for l in lines:
				_eqawarn(l, phase=phase, key=self.settings.mycpv)
		else:
			self._scheduler.dblinkElog(self,
				phase, _eqawarn, lines)

	def _eerror(self, phase, lines):
		from portage.elog.messages import eerror as _eerror
		if self._scheduler is None:
			for l in lines:
				_eerror(l, phase=phase, key=self.settings.mycpv)
		else:
			self._scheduler.dblinkElog(self,
				phase, _eerror, lines)

	def treewalk(self, srcroot, destroot, inforoot, myebuild, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		"""
		
		This function does the following:
		
		calls self._preserve_libs if FEATURES=preserve-libs
		calls self._collision_protect if FEATURES=collision-protect
		calls doebuild(mydo=pkg_preinst)
		Merges the package to the livefs
		unmerges old version (if required)
		calls doebuild(mydo=pkg_postinst)
		calls env_update
		calls elog_process
		
		@param srcroot: Typically this is ${D}
		@type srcroot: String (Path)
		@param destroot: Path to merge to (usually ${ROOT})
		@type destroot: String (Path)
		@param inforoot: root of the vardb entry ?
		@type inforoot: String (Path)
		@param myebuild: path to the ebuild that we are processing
		@type myebuild: String (Path)
		@param mydbapi: dbapi which is handed to doebuild.
		@type mydbapi: portdbapi instance
		@param prev_mtimes: { Filename:mtime } mapping for env_update
		@type prev_mtimes: Dictionary
		@rtype: Boolean
		@returns:
		1. 0 on success
		2. 1 on failure
		
		secondhand is a list of symlinks that have been skipped due to their target
		not existing; we will merge these symlinks at a later time.
		"""

		os = _os_merge

		srcroot = _unicode_decode(srcroot,
			encoding=_encodings['content'], errors='strict')
		destroot = _unicode_decode(destroot,
			encoding=_encodings['content'], errors='strict')
		inforoot = _unicode_decode(inforoot,
			encoding=_encodings['content'], errors='strict')
		myebuild = _unicode_decode(myebuild,
			encoding=_encodings['content'], errors='strict')

		showMessage = self._display_merge
		scheduler = self._scheduler

		srcroot = normalize_path(srcroot).rstrip(os.path.sep) + os.path.sep
		destroot = normalize_path(destroot).rstrip(os.path.sep) + os.path.sep

		if not os.path.isdir(srcroot):
			showMessage(_("!!! Directory Not Found: D='%s'\n") % srcroot,
				level=logging.ERROR, noiselevel=-1)
			return 1

		slot = ''
		for var_name in ('CHOST', 'SLOT'):
			if var_name == 'CHOST' and self.cat == 'virtual':
				try:
					os.unlink(os.path.join(inforoot, var_name))
				except OSError:
					pass
				continue

			try:
				val = codecs.open(_unicode_encode(
					os.path.join(inforoot, var_name),
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace').readline().strip()
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				val = ''

			if var_name == 'SLOT':
				slot = val

				if not slot.strip():
					slot = self.settings.get(var_name, '')
					if not slot.strip():
						showMessage(_("!!! SLOT is undefined\n"),
							level=logging.ERROR, noiselevel=-1)
						return 1
					write_atomic(os.path.join(inforoot, var_name), slot + '\n')

			if val != self.settings.get(var_name, ''):
				self._eqawarn('preinst',
					[_("QA Notice: Expected %(var_name)s='%(expected_value)s', got '%(actual_value)s'\n") % \
					{"var_name":var_name, "expected_value":self.settings.get(var_name, ''), "actual_value":val}])

		def eerror(lines):
			self._eerror("preinst", lines)

		if not os.path.exists(self.dbcatdir):
			os.makedirs(self.dbcatdir)

		otherversions = []
		for v in self.vartree.dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		cp = self.mysplit[0]
		slot_atom = "%s:%s" % (cp, slot)

		# filter any old-style virtual matches
		slot_matches = [cpv for cpv in self.vartree.dbapi.match(slot_atom) \
			if cpv_getkey(cpv) == cp]

		if self.mycpv not in slot_matches and \
			self.vartree.dbapi.cpv_exists(self.mycpv):
			# handle multislot or unapplied slotmove
			slot_matches.append(self.mycpv)

		others_in_slot = []
		from portage import config
		for cur_cpv in slot_matches:
			# Clone the config in case one of these has to be unmerged since
			# we need it to have private ${T} etc... for things like elog.
			others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
				self.vartree.root, config(clone=self.settings),
				vartree=self.vartree, treetype="vartree",
				scheduler=self._scheduler))

		retval = self._security_check(others_in_slot)
		if retval:
			return retval

		if slot_matches:
			# Used by self.isprotected().
			max_dblnk = None
			max_counter = -1
			for dblnk in others_in_slot:
				cur_counter = self.vartree.dbapi.cpv_counter(dblnk.mycpv)
				if cur_counter > max_counter:
					max_counter = cur_counter
					max_dblnk = dblnk
			self._installed_instance = max_dblnk

		# We check for unicode encoding issues after src_install. However,
		# the check must be repeated here for binary packages (it's
		# inexpensive since we call os.walk() here anyway).
		unicode_errors = []

		while True:

			unicode_error = False

			myfilelist = []
			mylinklist = []
			paths_with_newlines = []
			srcroot_len = len(srcroot)
			def onerror(e):
				raise
			for parent, dirs, files in os.walk(srcroot, onerror=onerror):
				try:
					parent = _unicode_decode(parent,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeDecodeError:
					new_parent = _unicode_decode(parent,
						encoding=_encodings['merge'], errors='replace')
					new_parent = _unicode_encode(new_parent,
						encoding=_encodings['merge'], errors='backslashreplace')
					new_parent = _unicode_decode(new_parent,
						encoding=_encodings['merge'], errors='replace')
					os.rename(parent, new_parent)
					unicode_error = True
					unicode_errors.append(new_parent[srcroot_len:])
					break

				for fname in files:
					try:
						fname = _unicode_decode(fname,
							encoding=_encodings['merge'], errors='strict')
					except UnicodeDecodeError:
						fpath = portage._os.path.join(
							parent.encode(_encodings['merge']), fname)
						new_fname = _unicode_decode(fname,
							encoding=_encodings['merge'], errors='replace')
						new_fname = _unicode_encode(new_fname,
							encoding=_encodings['merge'], errors='backslashreplace')
						new_fname = _unicode_decode(new_fname,
							encoding=_encodings['merge'], errors='replace')
						new_fpath = os.path.join(parent, new_fname)
						os.rename(fpath, new_fpath)
						unicode_error = True
						unicode_errors.append(new_fpath[srcroot_len:])
						fname = new_fname
						fpath = new_fpath
					else:
						fpath = os.path.join(parent, fname)

					relative_path = fpath[srcroot_len:]

					if "\n" in relative_path:
						paths_with_newlines.append(relative_path)

					file_mode = os.lstat(fpath).st_mode
					if stat.S_ISREG(file_mode):
						myfilelist.append(relative_path)
					elif stat.S_ISLNK(file_mode):
						# Note: os.walk puts symlinks to directories in the "dirs"
						# list and it does not traverse them since that could lead
						# to an infinite recursion loop.
						mylinklist.append(relative_path)

				if unicode_error:
					break

			if not unicode_error:
				break

		if unicode_errors:
			eerror(portage._merge_unicode_error(unicode_errors))

		if paths_with_newlines:
			msg = []
			msg.append(_("This package installs one or more files containing a newline (\\n) character:"))
			msg.append("")
			paths_with_newlines.sort()
			for f in paths_with_newlines:
				msg.append("\t/%s" % (f.replace("\n", "\\n")))
			msg.append("")
			msg.append(_("package %s NOT merged") % self.mycpv)
			msg.append("")
			eerror(msg)
			return 1

		# If there are no files to merge, and an installed package in the same
		# slot has files, it probably means that something went wrong.
		if self.settings.get("PORTAGE_PACKAGE_EMPTY_ABORT") == "1" and \
			not myfilelist and not mylinklist and others_in_slot:
			installed_files = None
			for other_dblink in others_in_slot:
				installed_files = other_dblink.getcontents()
				if not installed_files:
					continue
				from textwrap import wrap
				wrap_width = 72
				msg = []
				d = {
					"new_cpv":self.mycpv,
					"old_cpv":other_dblink.mycpv
				}
				msg.extend(wrap(_("The '%(new_cpv)s' package will not install "
					"any files, but the currently installed '%(old_cpv)s'"
					" package has the following files: ") % d, wrap_width))
				msg.append("")
				msg.extend(sorted(installed_files))
				msg.append("")
				msg.append(_("package %s NOT merged") % self.mycpv)
				msg.append("")
				msg.extend(wrap(
					_("Manually run `emerge --unmerge =%s` if you "
					"really want to remove the above files. Set "
					"PORTAGE_PACKAGE_EMPTY_ABORT=\"0\" in "
					"/etc/make.conf if you do not want to "
					"abort in cases like this.") % other_dblink.mycpv,
					wrap_width))
				eerror(msg)
			if installed_files:
				return 1

		# check for package collisions
		blockers = None
		if self._blockers is not None:
			# This is only supposed to be called when
			# the vdb is locked, like it is here.
			blockers = self._blockers()
		if blockers is None:
			blockers = []
		collisions, plib_collisions = \
			self._collision_protect(srcroot, destroot,
			others_in_slot + blockers, myfilelist + mylinklist)

		# Make sure the ebuild environment is initialized and that ${T}/elog
		# exists for logging of collision-protect eerror messages.
		if myebuild is None:
			myebuild = os.path.join(inforoot, self.pkg + ".ebuild")
		doebuild_environment(myebuild, "preinst", destroot,
			self.settings, 0, 0, mydbapi)
		prepare_build_dirs(destroot, self.settings, cleanup)

		if collisions:
			collision_protect = "collision-protect" in self.settings.features
			protect_owned = "protect-owned" in self.settings.features
			msg = _("This package will overwrite one or more files that"
			" may belong to other packages (see list below).")
			if not (collision_protect or protect_owned):
				msg += _(" Add either \"collision-protect\" or" 
				" \"protect-owned\" to FEATURES in"
				" make.conf if you would like the merge to abort"
				" in cases like this. See the make.conf man page for"
				" more information about these features.")
			if self.settings.get("PORTAGE_QUIET") != "1":
				msg += _(" You can use a command such as"
				" `portageq owners / <filename>` to identify the"
				" installed package that owns a file. If portageq"
				" reports that only one package owns a file then do NOT"
				" file a bug report. A bug report is only useful if it"
				" identifies at least two or more packages that are known"
				" to install the same file(s)."
				" If a collision occurs and you"
				" can not explain where the file came from then you"
				" should simply ignore the collision since there is not"
				" enough information to determine if a real problem"
				" exists. Please do NOT file a bug report at"
				" http://bugs.gentoo.org unless you report exactly which"
				" two packages install the same file(s). Once again,"
				" please do NOT file a bug report unless you have"
				" completely understood the above message.")

			self.settings["EBUILD_PHASE"] = "preinst"
			from textwrap import wrap
			msg = wrap(msg, 70)
			if collision_protect:
				msg.append("")
				msg.append(_("package %s NOT merged") % self.settings.mycpv)
			msg.append("")
			msg.append(_("Detected file collision(s):"))
			msg.append("")

			for f in collisions:
				msg.append("\t%s" % \
					os.path.join(destroot, f.lstrip(os.path.sep)))

			eerror(msg)

			msg = []
			msg.append("")
			msg.append(_("Searching all installed"
				" packages for file collisions..."))
			msg.append("")
			msg.append(_("Press Ctrl-C to Stop"))
			msg.append("")
			eerror(msg)

			owners = self.vartree.dbapi._owners.get_owners(collisions)
			self.vartree.dbapi.flush_cache()

			for pkg, owned_files in owners.items():
				cpv = pkg.mycpv
				msg = []
				msg.append("%s" % cpv)
				for f in sorted(owned_files):
					msg.append("\t%s" % os.path.join(destroot,
						f.lstrip(os.path.sep)))
				msg.append("")
				eerror(msg)

			if not owners:
				eerror([_("None of the installed"
					" packages claim the file(s)."), ""])

			# The explanation about the collision and how to solve
			# it may not be visible via a scrollback buffer, especially
			# if the number of file collisions is large. Therefore,
			# show a summary at the end.
			if collision_protect:
				msg = _("Package '%s' NOT merged due to file collisions.") % \
					self.settings.mycpv
			elif protect_owned and owners:
				msg = _("Package '%s' NOT merged due to file collisions.") % \
					self.settings.mycpv
			else:
				msg = _("Package '%s' merged despite file collisions.") % \
					self.settings.mycpv
			msg += _(" If necessary, refer to your elog "
				"messages for the whole content of the above message.")
			eerror(wrap(msg, 70))

			if collision_protect or (protect_owned and owners):
				return 1

		# The merge process may move files out of the image directory,
		# which causes invalidation of the .installed flag.
		try:
			os.unlink(os.path.join(
				os.path.dirname(normalize_path(srcroot)), ".installed"))
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e

		self.dbdir = self.dbtmpdir
		self.delete()
		ensure_dirs(self.dbtmpdir)

		# run preinst script
		if scheduler is None:
			showMessage(_(">>> Merging %(cpv)s to %(destroot)s\n") % {"cpv":self.mycpv, "destroot":destroot})
			a = doebuild(myebuild, "preinst", destroot, self.settings,
				use_cache=0, tree=self.treetype, mydbapi=mydbapi,
				vartree=self.vartree)
		else:
			a = scheduler.dblinkEbuildPhase(
				self, mydbapi, myebuild, "preinst")

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			showMessage(_("!!! FAILED preinst: ")+str(a)+"\n",
				level=logging.ERROR, noiselevel=-1)
			return a

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in os.listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# write local package counter for recording
		counter = self.vartree.dbapi.counter_tick(self.myroot, mycpv=self.mycpv)
		codecs.open(_unicode_encode(os.path.join(self.dbtmpdir, 'COUNTER'),
			encoding=_encodings['fs'], errors='strict'),
			'w', encoding=_encodings['repo.content'], errors='backslashreplace'
			).write(str(counter))

		# open CONTENTS file (possibly overwriting old one) for recording
		outfile = codecs.open(_unicode_encode(
			os.path.join(self.dbtmpdir, 'CONTENTS'),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace')

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		conf_mem_file = os.path.join(destroot, CONFIG_MEMORY_FILE)
		cfgfiledict = grabdict(conf_mem_file)
		cfgfiledict_orig = cfgfiledict.copy()
		if "NOCONFMEM" in self.settings:
			cfgfiledict["IGNORE"]=1
		else:
			cfgfiledict["IGNORE"]=0

		# Always behave like --noconfmem is enabled for downgrades
		# so that people who don't know about this option are less
		# likely to get confused when doing upgrade/downgrade cycles.
		pv_split = catpkgsplit(self.mycpv)[1:]
		for other in others_in_slot:
			if pkgcmp(pv_split, catpkgsplit(other.mycpv)[1:]) < 0:
				cfgfiledict["IGNORE"] = 1
				break

		# Don't bump mtimes on merge since some application require
		# preservation of timestamps.  This means that the unmerge phase must
		# check to see if file belongs to an installed instance in the same
		# slot.
		mymtime = None

		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		prevmask = os.umask(0)
		secondhand = []

		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		if self.mergeme(srcroot, destroot, outfile, secondhand, "", cfgfiledict, mymtime):
			return 1

		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen = 0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that
			# couldn't get merged will be added to thirdhand.

			thirdhand = []
			if self.mergeme(srcroot, destroot, outfile, thirdhand,
				secondhand, cfgfiledict, mymtime):
				return 1

			#swap hands
			lastlen = len(secondhand)

			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			if self.mergeme(srcroot, destroot, outfile, None,
				secondhand, cfgfiledict, mymtime):
				return 1
		self._md5_merge_map.clear()

		#restore umask
		os.umask(prevmask)

		#if we opened it, close it
		outfile.flush()
		outfile.close()

		# write out our collection of md5sums
		cfgfiledict.pop("IGNORE", None)
		if cfgfiledict != cfgfiledict_orig:
			ensure_dirs(os.path.dirname(conf_mem_file),
				gid=portage_gid, mode=0o2750, mask=0o2)
			writedict(cfgfiledict, conf_mem_file)

		# These caches are populated during collision-protect and the data
		# they contain is now invalid. It's very important to invalidate
		# the contents_inodes cache so that FEATURES=unmerge-orphans
		# doesn't unmerge anything that belongs to this package that has
		# just been merged.
		for dblnk in others_in_slot:
			dblnk._clear_contents_cache()
		self._clear_contents_cache()

		linkmap = self.vartree.dbapi.linkmap
		self._linkmap_rebuild(include_file=os.path.join(inforoot,
			linkmap._needed_aux_key))

		# Preserve old libs if they are still in use
		preserve_paths = self._find_libs_to_preserve()
		if preserve_paths:
			self._add_preserve_libs_to_contents(preserve_paths)

		# If portage is reinstalling itself, remove the old
		# version now since we want to use the temporary
		# PORTAGE_BIN_PATH that will be removed when we return.
		reinstall_self = False
		if self.myroot == "/" and \
			match_from_list(PORTAGE_PACKAGE_ATOM, [self.mycpv]):
			reinstall_self = True

		if scheduler is None:
			def emerge_log(msg):
				pass
		else:
			emerge_log = scheduler.dblinkEmergeLog

		autoclean = self.settings.get("AUTOCLEAN", "yes") == "yes"

		if autoclean:
			emerge_log(_(" >>> AUTOCLEAN: %s") % (slot_atom,))

		others_in_slot.append(self)  # self has just been merged
		for dblnk in list(others_in_slot):
			if dblnk is self:
				continue
			if not (autoclean or dblnk.mycpv == self.mycpv or reinstall_self):
				continue
			showMessage(_(">>> Safely unmerging already-installed instance...\n"))
			emerge_log(_(" === Unmerging... (%s)") % (dblnk.mycpv,))
			others_in_slot.remove(dblnk) # dblnk will unmerge itself now
			dblnk._linkmap_broken = self._linkmap_broken
			unmerge_rval = dblnk.unmerge(trimworld=0,
				ldpath_mtimes=prev_mtimes, others_in_slot=others_in_slot)

			if unmerge_rval == os.EX_OK:
				emerge_log(_(" >>> unmerge success: %s") % (dblnk.mycpv,))
			else:
				emerge_log(_(" !!! unmerge FAILURE: %s") % (dblnk.mycpv,))

			# TODO: Check status and abort if necessary.
			dblnk.delete()
			showMessage(_(">>> Original instance of package unmerged safely.\n"))

		if len(others_in_slot) > 1:
			showMessage(colorize("WARN", _("WARNING:"))
				+ _(" AUTOCLEAN is disabled.  This can cause serious"
				" problems due to overlapping packages.\n"),
				level=logging.WARN, noiselevel=-1)

		# We hold both directory locks.
		self.dbdir = self.dbpkgdir
		self.delete()
		_movefile(self.dbtmpdir, self.dbpkgdir, mysettings=self.settings)

		# keep track of the libs we preserved
		if preserve_paths:
			self.vartree.dbapi.plib_registry.register(self.mycpv,
				slot, counter, sorted(preserve_paths))

		# Check for file collisions with blocking packages
		# and remove any colliding files from their CONTENTS
		# since they now belong to this package.
		self._clear_contents_cache()
		contents = self.getcontents()
		destroot_len = len(destroot) - 1
		for blocker in blockers:
			self.vartree.dbapi.removeFromContents(blocker, iter(contents),
				relative_paths=False)

		# Unregister any preserved libs that this package has overwritten
		# and update the contents of the packages that owned them.
		plib_registry = self.vartree.dbapi.plib_registry
		plib_dict = plib_registry.getPreservedLibs()
		for cpv, paths in plib_collisions.items():
			if cpv not in plib_dict:
				continue
			if cpv == self.mycpv:
				continue
			try:
				slot, counter = self.vartree.dbapi.aux_get(
					cpv, ["SLOT", "COUNTER"])
			except KeyError:
				continue
			remaining = [f for f in plib_dict[cpv] if f not in paths]
			plib_registry.register(cpv, slot, counter, remaining)
			self.vartree.dbapi.removeFromContents(cpv, paths)

		self.vartree.dbapi._add(self)
		contents = self.getcontents()

		#do postinst script
		self.settings["PORTAGE_UPDATE_ENV"] = \
			os.path.join(self.dbpkgdir, "environment.bz2")
		self.settings.backup_changes("PORTAGE_UPDATE_ENV")
		try:
			if scheduler is None:
				a = doebuild(myebuild, "postinst", destroot, self.settings,
					use_cache=0, tree=self.treetype, mydbapi=mydbapi,
					vartree=self.vartree)
				if a == os.EX_OK:
					showMessage(_(">>> %s merged.\n") % self.mycpv)
			else:
				a = scheduler.dblinkEbuildPhase(
					self, mydbapi, myebuild, "postinst")
		finally:
			self.settings.pop("PORTAGE_UPDATE_ENV", None)

		if a != os.EX_OK:
			# It's stupid to bail out here, so keep going regardless of
			# phase return code.
			showMessage(_("!!! FAILED postinst: ")+str(a)+"\n",
				level=logging.ERROR, noiselevel=-1)

		downgrade = False
		for v in otherversions:
			if pkgcmp(catpkgsplit(self.pkg)[1:], catpkgsplit(v)[1:]) < 0:
				downgrade = True

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=(not downgrade),
			target_root=self.settings["ROOT"], prev_mtimes=prev_mtimes,
			contents=contents, env=self.settings.environ(),
			writemsg_level=self._display_merge)

		# For gcc upgrades, preserved libs have to be removed after the
		# the library path has been updated.
		self._linkmap_rebuild()
		cpv_lib_map = self._find_unused_preserved_libs()
		if cpv_lib_map:
			self._remove_preserved_libs(cpv_lib_map)
			for cpv, removed in cpv_lib_map.items():
				if not self.vartree.dbapi.cpv_exists(cpv):
					continue
				self.vartree.dbapi.removeFromContents(cpv, removed)

		return os.EX_OK

	def _new_backup_path(self, p):
		"""
		The works for any type path, such as a regular file, symlink,
		or directory. The parent directory is assumed to exist.
		The returned filename is of the form p + '.backup.' + x, where
		x guarantees that the returned path does not exist yet.
		"""
		os = _os_merge

		x = -1
		while True:
			x += 1
			backup_p = p + '.backup.' + str(x).rjust(4, '0')
			try:
				os.lstat(backup_p)
			except OSError:
				break

		return backup_p

	def mergeme(self, srcroot, destroot, outfile, secondhand, stufftomerge, cfgfiledict, thismtime):
		"""
		
		This function handles actual merging of the package contents to the livefs.
		It also handles config protection.
		
		@param srcroot: Where are we copying files from (usually ${D})
		@type srcroot: String (Path)
		@param destroot: Typically ${ROOT}
		@type destroot: String (Path)
		@param outfile: File to log operations to
		@type outfile: File Object
		@param secondhand: A set of items to merge in pass two (usually
		or symlinks that point to non-existing files that may get merged later)
		@type secondhand: List
		@param stufftomerge: Either a diretory to merge, or a list of items.
		@type stufftomerge: String or List
		@param cfgfiledict: { File:mtime } mapping for config_protected files
		@type cfgfiledict: Dictionary
		@param thismtime: The current time (typically long(time.time())
		@type thismtime: Long
		@rtype: None or Boolean
		@returns:
		1. True on failure
		2. None otherwise
		
		"""

		showMessage = self._display_merge
		writemsg = self._display_merge
		scheduler = self._scheduler

		os = _os_merge
		sep = os.sep
		join = os.path.join
		srcroot = normalize_path(srcroot).rstrip(sep) + sep
		destroot = normalize_path(destroot).rstrip(sep) + sep
		
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if isinstance(stufftomerge, basestring):
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist = os.listdir(join(srcroot, stufftomerge))
			offset = stufftomerge
		else:
			mergelist = stufftomerge
			offset = ""

		for i, x in enumerate(mergelist):

			if scheduler is not None and \
				0 == i % self._file_merge_yield_interval:
				scheduler.scheduleYield()

			mysrc = join(srcroot, offset, x)
			mydest = join(destroot, offset, x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest = join(sep, offset, x)
			# stat file once, test using S_* macros many times (faster that way)
			mystat = os.lstat(mysrc)
			mymode = mystat[stat.ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydstat = os.lstat(mydest)
				mydmode = mydstat.st_mode
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				#dest file doesn't exist
				mydstat = None
				mydmode = None

			if stat.S_ISLNK(mymode):
				# we are merging a symbolic link
				myabsto = abssymlink(mysrc)
				if myabsto.startswith(srcroot):
					myabsto = myabsto[len(srcroot):]
				myabsto = myabsto.lstrip(sep)
				myto = os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.startswith(self.settings["D"]):
						myto = myto[len(self.settings["D"]):]
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto = normalize_path(os.path.join(destroot, myabsto))
				if mydmode!=None:
					#destination exists
					if not stat.S_ISLNK(mydmode):
						if stat.S_ISDIR(mydmode):
							# directory in the way: we can't merge a symlink over a directory
							# we won't merge this, continue with next file...
							continue

						if os.path.exists(mysrc) and stat.S_ISDIR(os.stat(mysrc)[stat.ST_MODE]):
							# Kill file blocking installation of symlink to dir #71787
							pass
						elif self.isprotected(mydest):
							# Use md5 of the target in ${D} if it exists...
							try:
								newmd5 = perform_md5(join(srcroot, myabsto))
							except FileNotFound:
								# Maybe the target is merged already.
								try:
									newmd5 = perform_md5(myrealto)
								except FileNotFound:
									newmd5 = None
							mydest = new_protect_filename(mydest, newmd5=newmd5)

				# if secondhand is None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand != None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				mymtime = movefile(mysrc, mydest, newmtime=thismtime,
					sstat=mystat, mysettings=self.settings,
					encoding=_encodings['merge'])
				if mymtime != None:
					showMessage(">>> %s -> %s\n" % (mydest, myto))
					outfile.write("sym "+myrealdest+" -> "+myto+" "+str(mymtime)+"\n")
				else:
					showMessage(_("!!! Failed to move file.\n"),
						level=logging.ERROR, noiselevel=-1)
					showMessage("!!! %s -> %s\n" % (mydest, myto),
						level=logging.ERROR, noiselevel=-1)
					return 1
			elif stat.S_ISDIR(mymode):
				# we are merging a directory
				if mydmode != None:
					# destination exists

					if bsd_chflags:
						# Save then clear flags on dest.
						dflags = mydstat.st_flags
						if dflags != 0:
							bsd_chflags.lchflags(mydest, 0)

					if not os.access(mydest, os.W_OK):
						pkgstuff = pkgsplit(self.pkg)
						writemsg(_("\n!!! Cannot write to '%s'.\n") % mydest, noiselevel=-1)
						writemsg(_("!!! Please check permissions and directories for broken symlinks.\n"))
						writemsg(_("!!! You may start the merge process again by using ebuild:\n"))
						writemsg("!!! ebuild "+self.settings["PORTDIR"]+"/"+self.cat+"/"+pkgstuff[0]+"/"+self.pkg+".ebuild merge\n")
						writemsg(_("!!! And finish by running this: env-update\n\n"))
						return 1

					if stat.S_ISDIR(mydmode) or \
						(stat.S_ISLNK(mydmode) and os.path.isdir(mydest)):
						# a symlink to an existing directory will work for us; keep it:
						showMessage("--- %s/\n" % mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						backup_dest = self._new_backup_path(mydest)
						msg = []
						msg.append("")
						msg.append("Installation of a directory is blocked by a file:")
						msg.append("  '%s'" % mydest)
						msg.append("This file will be renamed to a different name:")
						msg.append("  '%s'" % backup_dest)
						msg.append("")
						self._eerror("preinst", msg)
						if movefile(mydest, backup_dest,
							mysettings=self.settings,
							encoding=_encodings['merge']) is None:
							return 1
						showMessage(_("bak %s %s.backup\n") % (mydest, mydest),
							level=logging.ERROR, noiselevel=-1)
						#now create our directory
						if self.settings.selinux_enabled():
							_selinux_merge.mkdir(mydest, mysrc)
						else:
							os.mkdir(mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
						os.chmod(mydest, mystat[0])
						os.chown(mydest, mystat[4], mystat[5])
						showMessage(">>> %s/\n" % mydest)
				else:
					#destination doesn't exist
					if self.settings.selinux_enabled():
						_selinux_merge.mkdir(mydest, mysrc)
					else:
						os.mkdir(mydest)
					os.chmod(mydest, mystat[0])
					os.chown(mydest, mystat[4], mystat[5])
					showMessage(">>> %s/\n" % mydest)
				outfile.write("dir "+myrealdest+"\n")
				# recurse and merge this directory
				if self.mergeme(srcroot, destroot, outfile, secondhand,
					join(offset, x), cfgfiledict, thismtime):
					return 1
			elif stat.S_ISREG(mymode):
				# we are merging a regular file
				mymd5 = perform_md5(mysrc, calc_prelink=1)
				# calculate config file protection stuff
				mydestdir = os.path.dirname(mydest)
				moveme = 1
				zing = "!!!"
				mymtime = None
				protected = self.isprotected(mydest)
				if mydmode != None:
					# destination file exists
					
					if stat.S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						newdest = self._new_backup_path(mydest)
						msg = []
						msg.append("")
						msg.append("Installation of a regular file is blocked by a directory:")
						msg.append("  '%s'" % mydest)
						msg.append("This file will be merged with a different name:")
						msg.append("  '%s'" % newdest)
						msg.append("")
						self._eerror("preinst", msg)
						mydest = newdest

					elif stat.S_ISREG(mydmode) or (stat.S_ISLNK(mydmode) and os.path.exists(mydest) and stat.S_ISREG(os.stat(mydest)[stat.ST_MODE])):
						# install of destination is blocked by an existing regular file,
						# or by a symlink to an existing regular file;
						# now, config file management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if protected:
							# we have a protection path; enable config file management.
							cfgprot = 0
							destmd5 = perform_md5(mydest, calc_prelink=1)
							if mymd5 == destmd5:
								#file already in place; simply update mtimes of destination
								moveme = 1
							else:
								if mymd5 == cfgfiledict.get(myrealdest, [None])[0]:
									""" An identical update has previously been
									merged.  Skip it unless the user has chosen
									--noconfmem."""
									moveme = cfgfiledict["IGNORE"]
									cfgprot = cfgfiledict["IGNORE"]
									if not moveme:
										zing = "---"
										mymtime = mystat[stat.ST_MTIME]
								else:
									moveme = 1
									cfgprot = 1
							if moveme:
								# Merging a new file, so update confmem.
								cfgfiledict[myrealdest] = [mymd5]
							elif destmd5 == cfgfiledict.get(myrealdest, [None])[0]:
								"""A previously remembered update has been
								accepted, so it is removed from confmem."""
								del cfgfiledict[myrealdest]

							if cfgprot:
								mydest = new_protect_filename(mydest, newmd5=mymd5)

				# whether config protection or not, we merge the new file the
				# same way.  Unless moveme=0 (blocking directory)
				if moveme:
					# Do not hardlink files unless they are in the same
					# directory, since otherwise tar may not be able to
					# extract a tarball of the resulting hardlinks due to
					# 'Invalid cross-device link' errors (depends on layout of
					# mount points). Also, don't hardlink zero-byte files since
					# it doesn't save any space, and don't hardlink
					# CONFIG_PROTECTed files since config files shouldn't be
					# hardlinked to eachother (for example, shadow installs
					# several identical config files inside /etc/pam.d/).
					parent_dir = os.path.dirname(myrealdest)
					hardlink_key = (parent_dir, mymd5, mystat.st_size,
						mystat.st_mode, mystat.st_uid, mystat.st_gid)

					hardlink_candidates = None
					if not protected and mystat.st_size != 0:
						hardlink_candidates = self._md5_merge_map.get(hardlink_key)
						if hardlink_candidates is None:
							hardlink_candidates = []
							self._md5_merge_map[hardlink_key] = hardlink_candidates

					mymtime = movefile(mysrc, mydest, newmtime=thismtime,
						sstat=mystat, mysettings=self.settings,
						hardlink_candidates=hardlink_candidates,
						encoding=_encodings['merge'])
					if mymtime is None:
						return 1
					if hardlink_candidates is not None:
						hardlink_candidates.append(mydest)
					zing = ">>>"

				if mymtime != None:
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				showMessage("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing = "!!!"
				if mydmode is None:
					# destination doesn't exist
					if movefile(mysrc, mydest, newmtime=thismtime,
						sstat=mystat, mysettings=self.settings,
						encoding=_encodings['merge']) is not None:
						zing = ">>>"
					else:
						return 1
				if stat.S_ISFIFO(mymode):
					outfile.write("fif %s\n" % myrealdest)
				else:
					outfile.write("dev %s\n" % myrealdest)
				showMessage(zing + " " + mydest + "\n")

	def merge(self, mergeroot, inforoot, myroot, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		"""
		If portage is reinstalling itself, create temporary
		copies of PORTAGE_BIN_PATH and PORTAGE_PYM_PATH in order
		to avoid relying on the new versions which may be
		incompatible. Register an atexit hook to clean up the
		temporary directories. Pre-load elog modules here since
		we won't be able to later if they get unmerged (happens
		when namespace changes).
		"""
		if self.vartree.dbapi._categories is not None:
			self.vartree.dbapi._categories = None
		if self.myroot == "/" and \
			match_from_list(PORTAGE_PACKAGE_ATOM, [self.mycpv]) and \
			not self.vartree.dbapi.cpv_exists(self.mycpv):
			# Load lazily referenced portage submodules into memory,
			# so imports won't fail during portage upgrade/downgrade.
			portage.proxy.lazyimport._preload_portage_submodules()
			settings = self.settings
			base_path_orig = os.path.dirname(settings["PORTAGE_BIN_PATH"])
			from tempfile import mkdtemp

			# Make the temp directory inside PORTAGE_TMPDIR since, unlike
			# /tmp, it can't be mounted with the "noexec" option.
			base_path_tmp = mkdtemp("", "._portage_reinstall_.",
				settings["PORTAGE_TMPDIR"])
			from portage.process import atexit_register
			atexit_register(shutil.rmtree, base_path_tmp)
			dir_perms = 0o755
			for subdir in "bin", "pym":
				var_name = "PORTAGE_%s_PATH" % subdir.upper()
				var_orig = settings[var_name]
				var_new = os.path.join(base_path_tmp, subdir)
				settings[var_name] = var_new
				settings.backup_changes(var_name)
				shutil.copytree(var_orig, var_new, symlinks=True)
				os.chmod(var_new, dir_perms)
			os.chmod(base_path_tmp, dir_perms)
			# This serves so pre-load the modules.
			elog_process(self.mycpv, self.settings)

		return self._merge(mergeroot, inforoot,
				myroot, myebuild=myebuild, cleanup=cleanup,
				mydbapi=mydbapi, prev_mtimes=prev_mtimes)

	def _merge(self, mergeroot, inforoot, myroot, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		retval = -1
		self.lockdb()
		self.vartree.dbapi._bump_mtime(self.mycpv)
		try:
			self.vartree.dbapi.plib_registry.load()
			self.vartree.dbapi.plib_registry.pruneNonExisting()
			retval = self.treewalk(mergeroot, myroot, inforoot, myebuild,
				cleanup=cleanup, mydbapi=mydbapi, prev_mtimes=prev_mtimes)

			# If PORTAGE_BUILDDIR doesn't exist, then it probably means
			# fail-clean is enabled, and the success/die hooks have
			# already been called by _emerge.EbuildPhase (via
			# self._scheduler.dblinkEbuildPhase) prior to cleaning.
			if os.path.isdir(self.settings['PORTAGE_BUILDDIR']):

				if retval == os.EX_OK:
					phase = 'success_hooks'
				else:
					phase = 'die_hooks'

				if self._scheduler is None:
					_spawn_misc_sh(self.settings, [phase],
						phase=phase)
				else:
					self._scheduler.dblinkEbuildPhase(
						self, mydbapi, myebuild, phase)

				elog_process(self.mycpv, self.settings)

				if 'noclean' not in self.settings.features and \
					(retval == os.EX_OK or \
					'fail-clean' in self.settings.features):
					if myebuild is None:
						myebuild = os.path.join(inforoot, self.pkg + ".ebuild")

					if self._scheduler is None:
						doebuild(myebuild, "clean", myroot,
							self.settings, tree=self.treetype,
							mydbapi=mydbapi, vartree=self.vartree)
					else:
						self._scheduler.dblinkEbuildPhase(
							self, mydbapi, myebuild, "clean")

		finally:
			self.vartree.dbapi.linkmap._clear_cache()
			self.unlockdb()
			self.vartree.dbapi._bump_mtime(self.mycpv)
		return retval

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		mydata = codecs.open(
			_unicode_encode(os.path.join(self.dbdir, name),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			).read().split()
		return " ".join(mydata)

	def copyfile(self,fname):
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))

	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		return codecs.open(_unicode_encode(os.path.join(self.dbdir, fname),
			encoding=_encodings['fs'], errors='strict'), 
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			).read()

	def setfile(self,fname,data):
		kwargs = {}
		if fname == 'environment.bz2' or not isinstance(data, basestring):
			kwargs['mode'] = 'wb'
		else:
			kwargs['mode'] = 'w'
			kwargs['encoding'] = _encodings['repo.content']
		write_atomic(os.path.join(self.dbdir, fname), data, **kwargs)

	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return []
		mylines = codecs.open(_unicode_encode(
			os.path.join(self.dbdir, ename),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			).readlines()
		myreturn = []
		for x in mylines:
			for y in x[:-1].split():
				myreturn.append(y)
		return myreturn

	def setelements(self,mylist,ename):
		myelement = codecs.open(_unicode_encode(
			os.path.join(self.dbdir, ename),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace')
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()

	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(os.path.join(self.dbdir, "CATEGORY"))

def merge(mycat, mypkg, pkgloc, infloc, myroot, mysettings, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None, blockers=None,
	scheduler=None):
	if not os.access(myroot, os.W_OK):
		writemsg(_("Permission denied: access('%s', W_OK)\n") % myroot,
			noiselevel=-1)
		return errno.EACCES
	mylink = dblink(mycat, mypkg, myroot, mysettings, treetype=mytree,
		vartree=vartree, blockers=blockers, scheduler=scheduler)
	return mylink.merge(pkgloc, infloc, myroot, myebuild,
		mydbapi=mydbapi, prev_mtimes=prev_mtimes)

def unmerge(cat, pkg, myroot, mysettings, mytrimworld=1, vartree=None,
	ldpath_mtimes=None, scheduler=None):
	mylink = dblink(cat, pkg, myroot, mysettings, treetype="vartree",
		vartree=vartree, scheduler=scheduler)
	vartree = mylink.vartree
	try:
		mylink.lockdb()
		if mylink.exists():
			vartree.dbapi.plib_registry.load()
			vartree.dbapi.plib_registry.pruneNonExisting()
			retval = mylink.unmerge(trimworld=mytrimworld, cleanup=1,
				ldpath_mtimes=ldpath_mtimes)
			if retval == os.EX_OK:
				mylink.delete()
			return retval
		return os.EX_OK
	finally:
		vartree.dbapi.linkmap._clear_cache()
		mylink.unlockdb()

def write_contents(contents, root, f):
	"""
	Write contents to any file like object. The file will be left open.
	"""
	root_len = len(root) - 1
	for filename in sorted(contents):
		entry_data = contents[filename]
		entry_type = entry_data[0]
		relative_filename = filename[root_len:]
		if entry_type == "obj":
			entry_type, mtime, md5sum = entry_data
			line = "%s %s %s %s\n" % \
				(entry_type, relative_filename, md5sum, mtime)
		elif entry_type == "sym":
			entry_type, mtime, link = entry_data
			line = "%s %s -> %s %s\n" % \
				(entry_type, relative_filename, link, mtime)
		else: # dir, dev, fif
			line = "%s %s\n" % (entry_type, relative_filename)
		f.write(line)

def tar_contents(contents, root, tar, protect=None, onProgress=None):
	os = _os_merge

	try:
		for x in contents:
			_unicode_encode(x,
				encoding=_encodings['merge'],
				errors='strict')
	except UnicodeEncodeError:
		# The package appears to have been merged with a
		# different value of sys.getfilesystemencoding(),
		# so fall back to utf_8 if appropriate.
		try:
			for x in contents:
				_unicode_encode(x,
					encoding=_encodings['fs'],
					errors='strict')
		except UnicodeEncodeError:
			pass
		else:
			os = portage.os

	from portage.util import normalize_path
	import tarfile
	root = normalize_path(root).rstrip(os.path.sep) + os.path.sep
	id_strings = {}
	maxval = len(contents)
	curval = 0
	if onProgress:
		onProgress(maxval, 0)
	paths = list(contents)
	paths.sort()
	for path in paths:
		curval += 1
		try:
			lst = os.lstat(path)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			if onProgress:
				onProgress(maxval, curval)
			continue
		contents_type = contents[path][0]
		if path.startswith(root):
			arcname = path[len(root):]
		else:
			raise ValueError("invalid root argument: '%s'" % root)
		live_path = path
		if 'dir' == contents_type and \
			not stat.S_ISDIR(lst.st_mode) and \
			os.path.isdir(live_path):
			# Even though this was a directory in the original ${D}, it exists
			# as a symlink to a directory in the live filesystem.  It must be
			# recorded as a real directory in the tar file to ensure that tar
			# can properly extract it's children.
			live_path = os.path.realpath(live_path)
		tarinfo = tar.gettarinfo(live_path, arcname)

		if stat.S_ISREG(lst.st_mode):
			# break hardlinks due to bug #185305
			tarinfo.type = tarfile.REGTYPE
			if protect and protect(path):
				# Create an empty file as a place holder in order to avoid
				# potential collision-protect issues.
				f = tempfile.TemporaryFile()
				f.write(_unicode_encode(
					"# empty file because --include-config=n " + \
					"when `quickpkg` was used\n"))
				f.flush()
				f.seek(0)
				tarinfo.size = os.fstat(f.fileno()).st_size
				tar.addfile(tarinfo, f)
				f.close()
			else:
				f = open(_unicode_encode(path,
					encoding=object.__getattribute__(os, '_encoding'),
					errors='strict'), 'rb')
				try:
					tar.addfile(tarinfo, f)
				finally:
					f.close()
		else:
			tar.addfile(tarinfo)
		if onProgress:
			onProgress(maxval, curval)
