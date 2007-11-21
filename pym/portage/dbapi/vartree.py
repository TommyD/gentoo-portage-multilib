# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.checksum import perform_md5
from portage.const import CACHE_PATH, CONFIG_MEMORY_FILE, PORTAGE_BIN_PATH, \
	PRIVATE_PATH, VDB_PATH
from portage.data import portage_gid, portage_uid, secpass
from portage.dbapi import dbapi
from portage.dep import dep_getslot, use_reduce, paren_reduce, isvalidatom, \
	isjustname, dep_getkey, match_from_list
from portage.exception import InvalidPackageName, InvalidAtom, \
	FileNotFound, PermissionDenied, UnsupportedAPIException
from portage.locks import lockdir, unlockdir
from portage.output import bold, red, green
from portage.update import fixdbentries
from portage.util import apply_secpass_permissions, ConfigProtect, ensure_dirs, \
	writemsg, writemsg_stdout, write_atomic, atomic_ofstream, writedict, \
	grabfile, grabdict, normalize_path, new_protect_filename
from portage.versions import pkgsplit, catpkgsplit, catsplit, best, pkgcmp

from portage import listdir, dep_expand, flatten, key_expand, \
	doebuild_environment, doebuild, env_update, prepare_build_dirs, \
	abssymlink, movefile, _movefile, bsd_chflags

from portage.elog import elog_process
from portage.elog.messages import ewarn
from portage.elog.filtering import filter_mergephases, filter_unmergephases

import os, sys, stat, errno, commands, copy, time
from itertools import izip

try:
	import cPickle
except ImportError:
	import pickle as cPickle

class PreservedLibsRegistry(object):
	""" This class handles the tracking of preserved library objects """
	def __init__(self, filename, autocommit=True):
		""" @param filename: absolute path for saving the preserved libs records
		    @type filename: String
			@param autocommit: determines if the file is written after every update
			@type autocommit: Boolean
		"""
		self._filename = filename
		self._autocommit = autocommit
		self.load()
	
	def load(self):
		""" Reload the registry data from file """
		try:
			self._data = cPickle.load(open(self._filename, "r"))
		except IOError, e:
			if e.errno == errno.ENOENT:
				self._data = {}
			elif e.errno == PermissionDenied.errno:
				raise PermissionDenied(self._filename)
			else:
				raise e
		
	def store(self):
		""" Store the registry data to file. No need to call this if autocommit
		    was enabled.
		"""
		cPickle.dump(self._data, open(self._filename, "w"))
	
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
		if len(paths) == 0 and self._data.has_key(cps) \
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
		for cps in self._data.keys():
			cpv, counter, paths = self._data[cps]
			paths = [f for f in paths if os.path.exists(f)]
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

class LibraryPackageMap(object):
	""" This class provides a library->consumer mapping generated from VDB data """
	def __init__(self, filename, vardbapi):
		self._filename = filename
		self._dbapi = vardbapi

	def get(self):
		""" Read the global library->consumer map for the given vdb instance.
		    @returns mapping of library objects (just basenames) to consumers (absolute paths)
			@rtype filename->list-of-paths
		"""
		if not os.path.exists(self._filename):
			self.update()
		rValue = {}
		for l in open(self._filename, "r").read().split("\n"):
			mysplit = l.split()
			if len(mysplit) > 1:
				rValue[mysplit[0]] = mysplit[1].split(",")
		return rValue

	def update(self):
		""" Update the global library->consumer map for the given vdb instance. """
		obj_dict = {}
		aux_get = self._dbapi.aux_get
		for cpv in self._dbapi.cpv_all():
			needed_list = aux_get(cpv, ["NEEDED"])[0].splitlines()
			for l in needed_list:
				mysplit = l.split()
				if len(mysplit) < 2:
					continue
				libs = mysplit[1].split(",")
				for lib in libs:
					if not obj_dict.has_key(lib):
						obj_dict[lib] = [mysplit[0]]
					else:
						obj_dict[lib].append(mysplit[0])
		mapfile = open(self._filename, "w")
		for lib in obj_dict:
			mapfile.write(lib+" "+",".join(obj_dict[lib])+"\n")
		mapfile.close()

class vardbapi(dbapi):
	def __init__(self, root, categories=None, settings=None, vartree=None):
		self.root = root[:]

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
		if categories is None:
			categories = settings.categories
		self.categories = categories[:]
		if vartree is None:
			from portage import db
			vartree = db[root]["vartree"]
		self.vartree = vartree
		self._aux_cache_keys = set(
			["CHOST", "COUNTER", "DEPEND", "EAPI", "IUSE", "KEYWORDS",
			"LICENSE", "PDEPEND", "PROVIDE", "RDEPEND", "NEEDED",
			"repository", "RESTRICT" , "SLOT", "USE"])
		self._aux_cache = None
		self._aux_cache_version = "1"
		self._aux_cache_filename = os.path.join(self.root,
			CACHE_PATH.lstrip(os.path.sep), "vdb_metadata.pickle")

		self.libmap = LibraryPackageMap(os.path.join(self.root, CACHE_PATH.lstrip(os.sep), "library_consumers"), self)
		try:
			self.plib_registry = PreservedLibsRegistry(
				os.path.join(self.root, PRIVATE_PATH, "preserved_libs_registry"))
		except PermissionDenied:
			# apparently this user isn't allowed to access PRIVATE_PATH
			self.plib_registry = None

	def getpath(self, mykey, filename=None):
		rValue = os.path.join(self.root, VDB_PATH, mykey)
		if filename != None:
			rValue = os.path.join(rValue, filename)
		return rValue

	def cpv_exists(self, mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.getpath(mykey))

	def cpv_counter(self, mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		try:
			return long(self.aux_get(mycpv, ["COUNTER"])[0])
		except (KeyError, ValueError):
			pass
		cdir = self.getpath(mycpv)
		cpath = self.getpath(mycpv, filename="COUNTER")

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption on XFS (unexpected reboot.)
		corrupted = 0
		if os.path.exists(cpath):
			cfile = open(cpath, "r")
			try:
				counter = long(cfile.readline())
			except ValueError:
				print "portage: COUNTER for", mycpv, "was corrupted; resetting to value of 0"
				counter = long(0)
				corrupted = 1
			cfile.close()
		elif os.path.exists(cdir):
			mys = pkgsplit(mycpv)
			myl = self.match(mys[0], use_cache=0)
			print mys, myl
			if len(myl) == 1:
				try:
					# Only one package... Counter doesn't matter.
					write_atomic(cpath, "1")
					counter = 1
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
						noiselevel=-1)
					writemsg("!!! Please run %s/fix-db.py or\n" % PORTAGE_BIN_PATH,
						noiselevel=-1)
					writemsg("!!! unmerge this exact version.\n", noiselevel=-1)
					writemsg("!!! %s\n" % e, noiselevel=-1)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
					noiselevel=-1)
				writemsg("!!! Please run %s/fix-db.py or\n" % PORTAGE_BIN_PATH,
					noiselevel=-1)
				writemsg("!!! remerge the package.\n", noiselevel=-1)
				sys.exit(1)
		else:
			counter = long(0)
		if corrupted:
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

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
		for cp in [origcp, newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise InvalidPackageName(cp)
		origmatches = self.match(origcp, use_cache=0)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			mycpsplit = catpkgsplit(mycpv)
			mynewcpv = newcp + "-" + mycpsplit[2]
			mynewcat = newcp.split("/")[0]
			if mycpsplit[3] != "r0":
				mynewcpv += "-" + mycpsplit[3]
			mycpsplit_new = catpkgsplit(mynewcpv)
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

			# We need to rename the ebuild now.
			old_pf = catsplit(mycpv)[1]
			new_pf = catsplit(mynewcpv)[1]
			if new_pf != old_pf:
				try:
					os.rename(os.path.join(newpath, old_pf + ".ebuild"),
						os.path.join(newpath, new_pf + ".ebuild"))
				except EnvironmentError, e:
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
			mystat = os.stat(self.getpath(mysplit[0]))[stat.ST_MTIME]
		except OSError:
			mystat = 0
		if use_cache and self.cpcache.has_key(mycp):
			cpc = self.cpcache[mycp]
			if cpc[0] == mystat:
				return cpc[1][:]
		cat_dir = self.getpath(mysplit[0])
		try:
			dir_list = os.listdir(cat_dir)
		except EnvironmentError, e:
			from portage.exception import PermissionDenied
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(cat_dir)
			del e
			dir_list = []

		returnme = []
		for x in dir_list:
			if x.startswith("."):
				continue
			if x[0] == '-':
				#writemsg(red("INCOMPLETE MERGE:")+str(x[len("-MERGING-"):])+"\n")
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
		elif self.cpcache.has_key(mycp):
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self, use_cache=1):
		returnme = []
		basepath = os.path.join(self.root, VDB_PATH) + os.path.sep
		for x in self.categories:
			for y in listdir(basepath + x, EmptyOnError=1):
				if y.startswith("."):
					continue
				subpath = x + "/" + y
				# -MERGING- should never be a cpv, nor should files.
				if os.path.isdir(basepath + subpath) and (pkgsplit(y) is not None):
					returnme += [subpath]
		return returnme

	def cp_all(self, use_cache=1):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			mysplit = catpkgsplit(y)
			if not mysplit:
				self.invalidentry(self.getpath(y))
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return d.keys()

	def checkblockers(self, origdep):
		pass

	def match(self, origdep, use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		mykey = dep_getkey(mydep)
		mycat = catsplit(mykey)[0]
		if not use_cache:
			if self.matchcache.has_key(mycat):
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			mymatch = match_from_list(mydep,
				self.cp_list(mykey, use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			return mymatch
		try:
			curmtime = os.stat(self.root+VDB_PATH+"/"+mycat)[stat.ST_MTIME]
		except (IOError, OSError):
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat] = curmtime
			self.matchcache[mycat] = {}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch = match_from_list(mydep, self.cp_list(mykey, use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
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
			self._aux_cache["modified"] and \
			secpass >= 2:
			valid_nodes = set(self.cpv_all())
			for cpv in self._aux_cache["packages"].keys():
				if cpv not in valid_nodes:
					del self._aux_cache["packages"][cpv]
			del self._aux_cache["modified"]
			try:
				f = atomic_ofstream(self._aux_cache_filename)
				cPickle.dump(self._aux_cache, f, -1)
				f.close()
				apply_secpass_permissions(
					self._aux_cache_filename, gid=portage_gid, mode=0644)
			except (IOError, OSError), e:
				pass
			self._aux_cache["modified"] = False

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
		if not self._aux_cache_keys.intersection(wants):
			return self._aux_get(mycpv, wants)
		if self._aux_cache is None:
			try:
				f = open(self._aux_cache_filename)
				mypickle = cPickle.Unpickler(f)
				mypickle.find_global = None
				self._aux_cache = mypickle.load()
				f.close()
				del f
			except (IOError, OSError, EOFError, cPickle.UnpicklingError):
				pass
			if not self._aux_cache or \
				not isinstance(self._aux_cache, dict) or \
				self._aux_cache.get("version") != self._aux_cache_version or \
				not self._aux_cache.get("packages"):
				self._aux_cache = {"version": self._aux_cache_version}
				self._aux_cache["packages"] = {}
			self._aux_cache["modified"] = False
		mydir = self.getpath(mycpv)
		mydir_stat = None
		try:
			mydir_stat = os.stat(mydir)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			raise KeyError(mycpv)
		mydir_mtime = long(mydir_stat.st_mtime)
		pkg_data = self._aux_cache["packages"].get(mycpv)
		mydata = {}
		cache_valid = False
		if pkg_data:
			cache_mtime, metadata = pkg_data
			cache_valid = cache_mtime == mydir_mtime
		if cache_valid:
			cache_incomplete = self._aux_cache_keys.difference(metadata)
			needed = metadata.get("NEEDED")
			if needed is None or needed and "\n" not in needed:
				# Cached value has whitespace filtered, so it has to be pulled
				# again. This is temporary migration code which can be removed
				# later, since it only affects users who are running trunk.
				cache_incomplete.add("NEEDED")
			if cache_incomplete:
				# Allow self._aux_cache_keys to change without a cache version
				# bump and efficiently recycle partial cache whenever possible.
				cache_valid = False
				pull_me = cache_incomplete.union(wants)
			else:
				pull_me = set(wants).difference(self._aux_cache_keys)
			mydata.update(metadata)
		else:
			pull_me = self._aux_cache_keys.union(wants)
		if pull_me:
			# pull any needed data and cache it
			aux_keys = list(pull_me)
			for k, v in izip(aux_keys, self._aux_get(mycpv, aux_keys)):
				mydata[k] = v
			if not cache_valid:
				cache_data = {}
				for aux_key in self._aux_cache_keys:
					cache_data[aux_key] = mydata[aux_key]
				self._aux_cache["packages"][mycpv] = (mydir_mtime, cache_data)
				self._aux_cache["modified"] = True
		return [mydata[x] for x in wants]

	def _aux_get(self, mycpv, wants):
		mydir = self.getpath(mycpv)
		try:
			if not stat.S_ISDIR(os.stat(mydir).st_mode):
				raise KeyError(mycpv)
		except OSError, e:
			if e.errno == errno.ENOENT:
				raise KeyError(mycpv)
			del e
			raise
		results = []
		for x in wants:
			try:
				myf = open(os.path.join(mydir, x), "r")
				try:
					myd = myf.read()
				finally:
					myf.close()
				if x != "NEEDED":
					myd = " ".join(myd.split())
			except IOError:
				myd = ""
			if x == "EAPI" and not myd:
				results.append("0")
			else:
				results.append(myd)
		return results

	def aux_update(self, cpv, values):
		cat, pkg = catsplit(cpv)
		mylink = dblink(cat, pkg, self.root, self.settings,
		treetype="vartree", vartree=self.vartree)
		if not mylink.exists():
			raise KeyError(cpv)
		for k, v in values.iteritems():
			if v:
				mylink.setfile(k, v)
			else:
				try:
					os.unlink(os.path.join(self.getpath(cpv), k))
				except EnvironmentError:
					pass

	def counter_tick(self, myroot, mycpv=None):
		return self.counter_tick_core(myroot, incrementing=1, mycpv=mycpv)

	def get_counter_tick_core(self, myroot, mycpv=None):
		return self.counter_tick_core(myroot, incrementing=0, mycpv=mycpv) + 1

	def counter_tick_core(self, myroot, incrementing=1, mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		cpath = os.path.join(myroot, CACHE_PATH.lstrip(os.sep), "counter")
		changed = False
		counter = -1
		try:
			cfile = open(cpath, "r")
		except EnvironmentError:
			writemsg("!!! COUNTER file is missing: '%s'\n" % cpath,
				noiselevel=-1)
		else:
			try:
				try:
					counter = long(cfile.readline().strip())
				finally:
					cfile.close()
			except (OverflowError, ValueError):
				writemsg("!!! COUNTER file is corrupt: '%s'\n" % cpath,
					noiselevel=-1)

		if counter < 0:
			changed = True
			max_counter = 0
			cp_list = self.cp_list
			for cp in self.cp_all():
				for cpv in cp_list(cp):
					try:
						counter = int(self.aux_get(cpv, ["COUNTER"])[0])
					except (KeyError, OverflowError, ValueError):
						continue
					if counter > max_counter:
						max_counter = counter
			counter = max_counter
			writemsg("!!! Initializing COUNTER to " + \
				"value of %d\n" % counter, noiselevel=-1)

		if incrementing or changed:

			#increment counter
			counter += 1
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

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
			self.settings = settings # for key_expand calls
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
		except SystemExit, e:
			raise
		except Exception, e:
			mydir = os.path.join(self.root, VDB_PATH, mycpv)
			writemsg("\nParse Error reading PROVIDE and USE in '%s'\n" % mydir,
				noiselevel=-1)
			if mylines:
				writemsg("Possibly Invalid: '%s'\n" % str(mylines),
					noiselevel=-1)
			writemsg("Exception: %s\n\n" % str(e), noiselevel=-1)
			return []

	def get_all_provides(self):
		myprovides = {}
		for node in self.getallcpv():
			for mykey in self.get_provide(node):
				if myprovides.has_key(mykey):
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

	def exists_specific_cat(self, cpv, use_cache=1):
		cpv = key_expand(cpv, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		a = catpkgsplit(cpv)
		if not a:
			return 0
		mylist = listdir(self.getpath(a[0]), EmptyOnError=1)
		for x in mylist:
			b = pkgsplit(x)
			if not b:
				self.dbapi.invalidentry(self.getpath(a[0], filename=x))
				continue
			if a[1] == b[0]:
				return 1
		return 0

	def getebuildpath(self, fullpackage):
		cat, package = catsplit(fullpackage)
		return self.getpath(fullpackage, filename=package+".ebuild")

	def getnode(self, mykey, use_cache=1):
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		if not mykey:
			return []
		mysplit = catsplit(mykey)
		mydirlist = listdir(self.getpath(mysplit[0]),EmptyOnError=1)
		returnme = []
		for x in mydirlist:
			mypsplit = pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.getpath(mysplit[0], filename=x))
				continue
			if mypsplit[0] == mysplit[1]:
				appendme = [mysplit[0]+"/"+x, [mysplit[0], mypsplit[0], mypsplit[1], mypsplit[2]]]
				returnme.append(appendme)
		return returnme


	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			return self.dbapi.aux_get(mycatpkg, ["SLOT"])[0]
		except KeyError:
			return ""

	def hasnode(self, mykey, use_cache):
		"""Does the particular node (cat/pkg key) exist?"""
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		mysplit = catsplit(mykey)
		mydirlist = listdir(self.getpath(mysplit[0]), EmptyOnError=1)
		for x in mydirlist:
			mypsplit = pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.getpath(mysplit[0], filename=x))
				continue
			if mypsplit[0] == mysplit[1]:
				return 1
		return 0

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

	def __init__(self, cat, pkg, myroot, mysettings, treetype=None,
		vartree=None):
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
		self.mysplit = pkgsplit(self.mycpv)
		self.treetype = treetype
		if vartree is None:
			from portage import db
			vartree = db[myroot]["vartree"]
		self.vartree = vartree

		self.dbroot = normalize_path(os.path.join(myroot, VDB_PATH))
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir = self.dbpkgdir

		self._lock_vdb = None

		self.settings = mysettings
		if self.settings == 1:
			raise ValueError

		self.myroot=myroot
		protect_obj = ConfigProtect(myroot,
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split())
		self.updateprotect = protect_obj.updateprotect
		self.isprotected = protect_obj.isprotected
		self._installed_instance = None
		self.contentscache = None
		self._contents_inodes = None

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
		try:
			for x in os.listdir(self.dbdir):
				os.unlink(self.dbdir+"/"+x)
			os.rmdir(self.dbdir)
		except OSError, e:
			print "!!! Unable to remove db entry for this package."
			print "!!! It is possible that a directory is in this one. Portage will still"
			print "!!! register this package as installed as long as this directory exists."
			print "!!! You may delete this directory with 'rm -Rf "+self.dbdir+"'"
			print "!!! "+str(e)
			print
			sys.exit(1)

		# Due to mtime granularity, mtime checks do not always properly
		# invalidate vardbapi caches.
		self.vartree.dbapi.mtdircache.pop(self.cat, None)
		self.vartree.dbapi.matchcache.pop(self.cat, None)
		self.vartree.dbapi.cpcache.pop(self.mysplit[0], None)

	def clearcontents(self):
		"""
		For a given db entry (self), erase the CONTENTS values.
		"""
		if os.path.exists(self.dbdir+"/CONTENTS"):
			os.unlink(self.dbdir+"/CONTENTS")

	def getcontents(self):
		"""
		Get the installed files of a given package (aka what that package installed)
		"""
		contents_file = os.path.join(self.dbdir, "CONTENTS")
		if self.contentscache is not None:
			return self.contentscache
		pkgfiles = {}
		try:
			myc = open(contents_file,"r")
		except EnvironmentError, e:
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
				errors.append((pos + 1, "Null byte found in CONTENTS entry"))
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
						errors.append((pos + 1, "Unrecognized CONTENTS entry"))
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
					errors.append((pos + 1, "Unrecognized CONTENTS entry"))
			except (KeyError, IndexError):
				errors.append((pos + 1, "Unrecognized CONTENTS entry"))
		if errors:
			writemsg("!!! Parse error in '%s'\n" % contents_file, noiselevel=-1)
			for pos, e in errors:
				writemsg("!!!   line %d: %s\n" % (pos, e), noiselevel=-1)
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

		# When others_in_slot is supplied, the security check has already been
		# done for this slot, so it shouldn't be repeated until the next
		# replacement or unmerge operation.
		if others_in_slot is None:
			slot = self.vartree.dbapi.aux_get(self.mycpv, ["SLOT"])[0]
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (dep_getkey(self.mycpv), slot))
			others_in_slot = []
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					self.vartree.root, self.settings, vartree=self.vartree))
			retval = self._security_check([self] + others_in_slot)
			if retval:
				return retval

		contents = self.getcontents()
		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath = None
		ebuild_phase = "prerm"
		mystuff = listdir(self.dbdir, EmptyOnError=1)
		for x in mystuff:
			if x.endswith(".ebuild"):
				myebuildpath = os.path.join(self.dbdir, self.pkg + ".ebuild")
				if x[:-7] != self.pkg:
					# Clean up after vardbapi.move_ent() breakage in
					# portage versions before 2.1.2
					os.rename(os.path.join(self.dbdir, x), myebuildpath)
					write_atomic(os.path.join(self.dbdir, "PF"), self.pkg+"\n")
				break

		self.settings.load_infodir(self.dbdir)
		if myebuildpath:
			try:
				doebuild_environment(myebuildpath, "prerm", self.myroot,
					self.settings, 0, 0, self.vartree.dbapi)
			except UnsupportedAPIException, e:
				# Sometimes this happens due to corruption of the EAPI file.
				writemsg("!!! FAILED prerm: %s\n" % \
					os.path.join(self.dbdir, "EAPI"), noiselevel=-1)
				writemsg("%s\n" % str(e), noiselevel=-1)
				return 1
			catdir = os.path.dirname(self.settings["PORTAGE_BUILDDIR"])
			ensure_dirs(os.path.dirname(catdir),
				uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		builddir_lock = None
		catdir_lock = None
		retval = -1
		try:
			if myebuildpath:
				catdir_lock = lockdir(catdir)
				ensure_dirs(catdir,
					uid=portage_uid, gid=portage_gid,
					mode=070, mask=0)
				builddir_lock = lockdir(
					self.settings["PORTAGE_BUILDDIR"])
				try:
					unlockdir(catdir_lock)
				finally:
					catdir_lock = None
				# Eventually, we'd like to pass in the saved ebuild env here...
				retval = doebuild(myebuildpath, "prerm", self.myroot,
					self.settings, cleanup=cleanup, use_cache=0,
					mydbapi=self.vartree.dbapi, tree="vartree",
					vartree=self.vartree)
				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					writemsg("!!! FAILED prerm: %s\n" % retval, noiselevel=-1)
					return retval

			self._unmerge_pkgfiles(pkgfiles, others_in_slot)
			
			# Remove the registration of preserved libs for this pkg instance
			self.vartree.dbapi.plib_registry.unregister(self.mycpv, self.settings["SLOT"], self.settings["COUNTER"])

			if myebuildpath:
				ebuild_phase = "postrm"
				retval = doebuild(myebuildpath, "postrm", self.myroot,
					 self.settings, use_cache=0, tree="vartree",
					 mydbapi=self.vartree.dbapi, vartree=self.vartree)

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					writemsg("!!! FAILED postrm: %s\n" % retval, noiselevel=-1)
					return retval

			# regenerate reverse NEEDED map
			self.vartree.dbapi.libmap.update()

		finally:
			if builddir_lock:
				try:
					if myebuildpath:
						if retval != os.EX_OK:
							msg = ("The '%s' " % ebuild_phase) + \
							("phase of the '%s' package " % self.mycpv) + \
							("has failed with exit value %s. " % retval) + \
							"The problem occurred while executing " + \
							("the ebuild located at '%s'. " % myebuildpath) + \
							"If necessary, manually remove the ebuild " + \
							"in order to skip the execution of removal phases."
							from portage.elog.messages import eerror
							from textwrap import wrap
							for l in wrap(msg, 72):
								eerror(l, phase=ebuild_phase, key=self.mycpv)

						# process logs created during pre/postrm
						elog_process(self.mycpv, self.settings, phasefilter=filter_unmergephases)
						if retval == os.EX_OK:
							doebuild(myebuildpath, "cleanrm", self.myroot,
								self.settings, tree="vartree",
								mydbapi=self.vartree.dbapi,
								vartree=self.vartree)
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
					except OSError, e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					unlockdir(catdir_lock)
		env_update(target_root=self.myroot, prev_mtimes=ldpath_mtimes,
			contents=contents, env=self.settings.environ())
		return os.EX_OK

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

		if not pkgfiles:
			writemsg_stdout("No package files given... Grabbing a set.\n")
			pkgfiles = self.getcontents()

		if others_in_slot is None:
			others_in_slot = []
			slot = self.vartree.dbapi.aux_get(self.mycpv, ["SLOT"])[0]
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (dep_getkey(self.mycpv), slot))
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					self.vartree.root, self.settings,
					vartree=self.vartree))
		dest_root = normalize_path(self.vartree.root).rstrip(os.path.sep) + \
			os.path.sep
		dest_root_len = len(dest_root)

		unmerge_orphans = "unmerge-orphans" in self.settings.features

		if pkgfiles:
			mykeys = pkgfiles.keys()
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
				finally:
					if bsd_chflags and pflags != 0:
						# Restore the parent flags we saved before unlinking
						bsd_chflags.chflags(parent_name, pflags)

			def show_unmerge(zing, desc, file_type, file_name):
					writemsg_stdout("%s %s %s %s\n" % \
						(zing, desc.ljust(8), file_type, file_name))
			for objkey in mykeys:
				obj = normalize_path(objkey)
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
						show_unmerge("---", "!found", file_type, obj)
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
						show_unmerge("---", "replaced", file_type, obj)
						continue
				# next line includes a tweak to protect modules from being unmerged,
				# but we don't protect modules from being overwritten if they are
				# upgraded. We effectively only want one half of the config protection
				# functionality for /lib/modules. For portage-ng both capabilities
				# should be able to be independently specified.
				if obj.startswith(modprotect):
					show_unmerge("---", "cfgpro", file_type, obj)
					continue

				# Don't unlink symlinks to directories here since that can
				# remove /lib and /usr/lib symlinks.
				if unmerge_orphans and \
					lstatobj and not stat.S_ISDIR(lstatobj.st_mode) and \
					not (islink and statobj and stat.S_ISDIR(statobj.st_mode)) and \
					not self.isprotected(obj):
					try:
						unlink(obj, lstatobj)
					except EnvironmentError, e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
					continue

				lmtime = str(lstatobj[stat.ST_MTIME])
				if (pkgfiles[objkey][0] not in ("dir", "fif", "dev")) and (lmtime != pkgfiles[objkey][1]):
					show_unmerge("---", "!mtime", file_type, obj)
					continue

				if pkgfiles[objkey][0] == "dir":
					if statobj is None or not stat.S_ISDIR(statobj.st_mode):
						show_unmerge("---", "!dir", file_type, obj)
						continue
					mydirs.append(obj)
				elif pkgfiles[objkey][0] == "sym":
					if not islink:
						show_unmerge("---", "!sym", file_type, obj)
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
					except (OSError, IOError),e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
						show_unmerge("!!!", "", file_type, obj)
				elif pkgfiles[objkey][0] == "obj":
					if statobj is None or not stat.S_ISREG(statobj.st_mode):
						show_unmerge("---", "!obj", file_type, obj)
						continue
					mymd5 = None
					try:
						mymd5 = perform_md5(obj, calc_prelink=1)
					except FileNotFound, e:
						# the file has disappeared between now and our stat call
						show_unmerge("---", "!obj", file_type, obj)
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != pkgfiles[objkey][2].lower():
						show_unmerge("---", "!md5", file_type, obj)
						continue
					try:
						unlink(obj, lstatobj)
					except (OSError, IOError), e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
				elif pkgfiles[objkey][0] == "fif":
					if not stat.S_ISFIFO(lstatobj[stat.ST_MODE]):
						show_unmerge("---", "!fif", file_type, obj)
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
				except EnvironmentError, e:
					if e.errno not in ignored_rmdir_errnos:
						raise
					if e.errno != errno.ENOENT:
						show_unmerge("---", "!empty", "dir", obj)
					del e

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

	def isowner(self,filename, destroot):
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
		destfile = normalize_path(
			os.path.join(destroot, filename.lstrip(os.path.sep)))

		pkgfiles = self.getcontents()
		if pkgfiles and destfile in pkgfiles:
			return True
		if pkgfiles:
			# Use stat rather than lstat since we want to follow
			# any symlinks to the real parent directory.
			parent_path = os.path.dirname(destfile)
			try:
				parent_stat = os.stat(parent_path)
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				return False
			if self._contents_inodes is None:
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
				basename = os.path.basename(destfile)
				for p_path in p_path_list:
					x = os.path.join(p_path, basename)
					if x in pkgfiles:
						return True

		return False

	def _preserve_libs(self, srcroot, destroot, mycontents, counter):
		# read global reverse NEEDED map
		libmap = self.vartree.dbapi.libmap.get()

		# get list of libraries from old package instance
		old_contents = self._installed_instance.getcontents().keys()
		old_libs = set([os.path.basename(x) for x in old_contents]).intersection(libmap)

		# get list of libraries from new package instance
		mylibs = set([os.path.basename(x) for x in mycontents]).intersection(libmap)

		# check which libs are present in the old, but not the new package instance
		preserve_libs = old_libs.difference(mylibs)

		# ignore any libs that are only internally used by the package
		def has_external_consumers(lib, contents, otherlibs):
			consumers = set(libmap[lib])
			contents_without_libs = [x for x in contents if not os.path.basename(x) in otherlibs]
			
			# just used by objects that will be autocleaned
			if len(consumers.difference(contents_without_libs)) == 0:
				return False
			# used by objects that are referenced as well, need to check those 
			# recursively to break any reference cycles
			elif len(consumers.difference(contents)) == 0:
				otherlibs = set(otherlibs)
				for ol in otherlibs.intersection(consumers):
					if has_external_consumers(ol, contents, otherlibs.difference([lib])):
						return True
				return False
			# used by external objects directly
			else:
				return True

		for lib in list(preserve_libs):
			if not has_external_consumers(lib, old_contents, preserve_libs):
				preserve_libs.remove(lib)						
			
		# get the real paths for the libs
		preserve_paths = [x for x in old_contents if os.path.basename(x) in preserve_libs]
		del old_contents, old_libs, mylibs, preserve_libs
			
		# inject files that should be preserved into our image dir
		import shutil
		for x in preserve_paths:
			print "injecting %s into %s" % (x, srcroot)
			mydir = os.path.join(srcroot, os.path.dirname(x))
			if not os.path.exists(mydir):
				os.makedirs(mydir)

			# resolve symlinks and extend preserve list
			# NOTE: we're extending the list in the loop to emulate recursion to
			#       also get indirect symlinks
			if os.path.islink(x):
				linktarget = os.readlink(x)
				os.symlink(linktarget, os.path.join(srcroot, x.lstrip(os.sep)))
				if linktarget[0] != os.sep:
					linktarget = os.path.join(os.path.dirname(x), linktarget)
				preserve_paths.append(linktarget)
			else:
				shutil.copy2(os.path.join(destroot, x), os.path.join(srcroot, x.lstrip(os.sep)))

		# keep track of the libs we preserved
		self.vartree.dbapi.plib_registry.register(self.mycpv, self.settings["SLOT"], counter, preserve_paths)

		del preserve_paths
	
	def _collision_protect(self, srcroot, destroot, mypkglist, mycontents):
			collision_ignore = set([normalize_path(myignore) for myignore in \
				self.settings.get("COLLISION_IGNORE", "").split()])

			stopmerge = False
			i=0
			collisions = []
			destroot = normalize_path(destroot).rstrip(os.path.sep) + \
				os.path.sep
			writemsg_stdout("%s checking %d files for package collisions\n" % \
				(green("*"), len(mycontents)))
			for f in mycontents:
				i = i + 1
				if i % 1000 == 0:
					writemsg_stdout("%d files checked ...\n" % i)
				dest_path = normalize_path(
					os.path.join(destroot, f.lstrip(os.path.sep)))
				try:
					dest_lstat = os.lstat(dest_path)
				except EnvironmentError, e:
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
							except EnvironmentError, e:
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
				isowned = False
				for ver in [self] + mypkglist:
					if (ver.isowner(f, destroot) or ver.isprotected(f)):
						isowned = True
						break
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
			return collisions

	def _security_check(self, installed_instances):
		if not installed_instances:
			return 0
		file_paths = set()
		for dblnk in installed_instances:
			file_paths.update(dblnk.getcontents())
		inode_map = {}
		real_paths = set()
		for path in file_paths:
			try:
				s = os.lstat(path)
			except OSError, e:
				if e.errno != errno.ENOENT:
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
		for path_list in inode_map.itervalues():
			path, s = path_list[0]
			if len(path_list) == s.st_nlink:
				# All hardlinks seem to be owned by this package.
				continue
			suspicious_hardlinks.append(path_list)
		if not suspicious_hardlinks:
			return 0
		from portage.output import colorize
		prefix = colorize("SECURITY_WARN", "*") + " WARNING: "
		writemsg(prefix + "suid/sgid file(s) " + \
			"with suspicious hardlink(s):\n", noiselevel=-1)
		for path_list in suspicious_hardlinks:
			for path, s in path_list:
				writemsg(prefix + "  '%s'\n" % path, noiselevel=-1)
		writemsg(prefix + "See the Gentoo Security Handbook " + \
			"guide for advice on how to proceed.\n", noiselevel=-1)
		return 1

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

		srcroot = normalize_path(srcroot).rstrip(os.path.sep) + os.path.sep

		if not os.path.isdir(srcroot):
			writemsg("!!! Directory Not Found: D='%s'\n" % srcroot,
				noiselevel=-1)
			return 1

		inforoot_slot_file = os.path.join(inforoot, "SLOT")
		slot = None
		try:
			f = open(inforoot_slot_file)
			try:
				slot = f.read().strip()
			finally:
				f.close()
		except EnvironmentError, e:
			if e.errno != errno.ENOENT:
				raise
			del e

		if slot is None:
			slot = ""

		if slot != self.settings["SLOT"]:
			writemsg("!!! WARNING: Expected SLOT='%s', got '%s'\n" % \
				(self.settings["SLOT"], slot))

		if not os.path.exists(self.dbcatdir):
			os.makedirs(self.dbcatdir)

		otherversions = []
		for v in self.vartree.dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		slot_matches = self.vartree.dbapi.match(
			"%s:%s" % (self.mysplit[0], slot))
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
				vartree=self.vartree))
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

		# get current counter value (counter_tick also takes care of incrementing it)
		# XXX Need to make this destroot, but it needs to be initialized first. XXX
		# XXX bis: leads to some invalidentry() call through cp_all().
		# Note: The counter is generated here but written later because preserve_libs
		#       needs the counter value but has to be before dbtmpdir is made (which
		#       has to be before the counter is written) - genone
		counter = self.vartree.dbapi.counter_tick(self.myroot, mycpv=self.mycpv)

		myfilelist = []
		mylinklist = []
		def onerror(e):
			raise
		for parent, dirs, files in os.walk(srcroot, onerror=onerror):
			for f in files:
				file_path = os.path.join(parent, f)
				file_mode = os.lstat(file_path).st_mode
				if stat.S_ISREG(file_mode):
					myfilelist.append(file_path[len(srcroot):])
				elif stat.S_ISLNK(file_mode):
					# Note: os.walk puts symlinks to directories in the "dirs"
					# list and it does not traverse them since that could lead
					# to an infinite recursion loop.
					mylinklist.append(file_path[len(srcroot):])

		# Preserve old libs if they are still in use
		if slot_matches and "preserve-libs" in self.settings.features:
			self._preserve_libs(srcroot, destroot, myfilelist+mylinklist, counter)

		# check for package collisions
		collisions = self._collision_protect(srcroot, destroot, others_in_slot,
			myfilelist+mylinklist)

		# Make sure the ebuild environment is initialized and that ${T}/elog
		# exists for logging of collision-protect eerror messages.
		if myebuild is None:
			myebuild = os.path.join(inforoot, self.pkg + ".ebuild")
		doebuild_environment(myebuild, "preinst", destroot,
			self.settings, 0, 0, mydbapi)
		prepare_build_dirs(destroot, self.settings, cleanup)

		from portage.elog.messages import eerror as _eerror
		def eerror(lines):
			for l in lines:
				_eerror(l, phase="preinst", key=self.settings.mycpv)

		if collisions:
			collision_protect = "collision-protect" in self.settings.features
			msg = "This package will overwrite one or more files that" + \
			" may belong to other packages (see list below)."
			if not collision_protect:
				msg += " Add \"collision-protect\" to FEATURES in" + \
				" make.conf if you would like the merge to abort" + \
				" in cases like this."
			if self.settings.get("PORTAGE_QUIET") != "1":
				msg += " You can use a command such as" + \
				" `portageq owners / <filename>` to identify the" + \
				" installed package that owns a file. If portageq" + \
				" reports that only one package owns a file then do NOT" + \
				" file a bug report. A bug report is only useful if it" + \
				" identifies at least two or more packages that are known" + \
				" to install the same file(s)." + \
				" If a collision occurs and you" + \
				" can not explain where the file came from then you" + \
				" should simply ignore the collision since there is not" + \
				" enough information to determine if a real problem" + \
				" exists. Please do NOT file a bug report at" + \
				" http://bugs.gentoo.org unless you report exactly which" + \
				" two packages install the same file(s). Once again," + \
				" please do NOT file a bug report unless you have" + \
				" completely understood the above message."

			self.settings["EBUILD_PHASE"] = "preinst"
			from textwrap import wrap
			msg = wrap(msg, 70)
			if collision_protect:
				msg.append("")
				msg.append("package %s NOT merged" % self.settings.mycpv)
			msg.append("")
			msg.append("Detected file collision(s):")
			msg.append("")

			for f in collisions:
				msg.append("\t%s" % \
					os.path.join(destroot, f.lstrip(os.path.sep)))

			eerror(msg)

			if collision_protect:
				msg = []
				msg.append("")
				msg.append("Searching all installed" + \
					" packages for file collisions...")
				msg.append("")
				msg.append("Press Ctrl-C to Stop")
				msg.append("")
				eerror(msg)

				found_owner = False
				for cpv in self.vartree.dbapi.cpv_all():
					cat, pkg = catsplit(cpv)
					mylink = dblink(cat, pkg, destroot, self.settings,
						vartree=self.vartree)
					mycollisions = []
					for f in collisions:
						if mylink.isowner(f, destroot):
							mycollisions.append(f)
					if mycollisions:
						found_owner = True
						msg = []
						msg.append("%s" % cpv)
						for f in mycollisions:
							msg.append("\t%s" % os.path.join(destroot,
								f.lstrip(os.path.sep)))
						eerror(msg)
				if not found_owner:
					eerror(["None of the installed" + \
						" packages claim the file(s)."])
				return 1

		writemsg_stdout(">>> Merging %s to %s\n" % (self.mycpv, destroot))

		# The merge process may move files out of the image directory,
		# which causes invalidation of the .installed flag.
		try:
			os.unlink(os.path.join(
				os.path.dirname(normalize_path(srcroot)), ".installed"))
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			del e

		self.dbdir = self.dbtmpdir
		self.delete()
		ensure_dirs(self.dbtmpdir)

		# run preinst script
		a = doebuild(myebuild, "preinst", destroot, self.settings,
			use_cache=0, tree=self.treetype, mydbapi=mydbapi,
			vartree=self.vartree)

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			writemsg("!!! FAILED preinst: "+str(a)+"\n", noiselevel=-1)
			return a

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# write local package counter for recording
		lcfile = open(os.path.join(self.dbtmpdir, "COUNTER"),"w")
		lcfile.write(str(counter))
		lcfile.close()

		# open CONTENTS file (possibly overwriting old one) for recording
		outfile = open(os.path.join(self.dbtmpdir, "CONTENTS"),"w")

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		conf_mem_file = os.path.join(destroot, CONFIG_MEMORY_FILE)
		cfgfiledict = grabdict(conf_mem_file)
		if self.settings.has_key("NOCONFMEM"):
			cfgfiledict["IGNORE"]=1
		else:
			cfgfiledict["IGNORE"]=0

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
			self.mergeme(srcroot, destroot, outfile, thirdhand, secondhand, cfgfiledict, mymtime)

			#swap hands
			lastlen = len(secondhand)

			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			self.mergeme(srcroot, destroot, outfile, None, secondhand, cfgfiledict, mymtime)

		#restore umask
		os.umask(prevmask)

		#if we opened it, close it
		outfile.flush()
		outfile.close()

		for dblnk in others_in_slot:
			if dblnk.mycpv != self.mycpv:
				continue
			writemsg_stdout(">>> Safely unmerging already-installed instance...\n")
			# These caches are populated during collision-protect and the data
			# they contain is now invalid. It's very important to invalidate
			# the contents_inodes cache so that FEATURES=unmerge-orphans
			# doesn't unmerge anything that belongs to this package that has
			# just been merged.
			self.contentscache = None
			self._contents_inodes = None
			others_in_slot.append(self)  # self has just been merged
			others_in_slot.remove(dblnk) # dblnk will unmerge itself now
			dblnk.unmerge(trimworld=0, ldpath_mtimes=prev_mtimes,
				others_in_slot=others_in_slot)
			writemsg_stdout(">>> Original instance of package unmerged safely.\n")
			break

		# We hold both directory locks.
		self.dbdir = self.dbpkgdir
		self.delete()
		_movefile(self.dbtmpdir, self.dbpkgdir, mysettings=self.settings)
		# Due to mtime granularity, mtime checks do not always properly
		# invalidate vardbapi caches.
		self.vartree.dbapi.mtdircache.pop(self.cat, None)
		self.vartree.dbapi.matchcache.pop(self.cat, None)
		self.vartree.dbapi.cpcache.pop(self.mysplit[0], None)
		contents = self.getcontents()

		#write out our collection of md5sums
		if cfgfiledict.has_key("IGNORE"):
			del cfgfiledict["IGNORE"]

		my_private_path = os.path.join(destroot, PRIVATE_PATH)
		ensure_dirs(my_private_path, gid=portage_gid, mode=02750, mask=02)

		writedict(cfgfiledict, conf_mem_file)
		del conf_mem_file

		# regenerate reverse NEEDED map
		self.vartree.dbapi.libmap.update()

		#do postinst script
		a = doebuild(myebuild, "postinst", destroot, self.settings, use_cache=0,
			tree=self.treetype, mydbapi=mydbapi, vartree=self.vartree)

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			writemsg("!!! FAILED postinst: "+str(a)+"\n", noiselevel=-1)
			return a

		downgrade = False
		for v in otherversions:
			if pkgcmp(catpkgsplit(self.pkg)[1:], catpkgsplit(v)[1:]) < 0:
				downgrade = True

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=(not downgrade),
			target_root=self.settings["ROOT"], prev_mtimes=prev_mtimes,
			contents=contents, env=self.settings.environ())

		writemsg_stdout(">>> %s %s\n" % (self.mycpv,"merged."))
		return os.EX_OK

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
		from os.path import sep, join
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
		for x in mergelist:
			mysrc = join(srcroot, offset, x)
			mydest = join(destroot, offset, x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest = join(sep, offset, x)
			# stat file once, test using S_* macros many times (faster that way)
			try:
				mystat = os.lstat(mysrc)
			except OSError, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: There appears to be ")+bold("FILE SYSTEM CORRUPTION.")+red(" A file that is listed\n"))
				writemsg(red("!!!        as existing is not capable of being stat'd. If you are using an\n"))
				writemsg(red("!!!        experimental kernel, please boot into a stable one, force an fsck,\n"))
				writemsg(red("!!!        and ensure your filesystem is in a sane state. ")+bold("'shutdown -Fr now'\n"))
				writemsg(red("!!!        File:  ")+str(mysrc)+"\n", noiselevel=-1)
				writemsg(red("!!!        Error: ")+str(e)+"\n", noiselevel=-1)
				sys.exit(1)
			except Exception, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: An unknown error has occurred during the merge process.\n"))
				writemsg(red("!!!        A stat call returned the following error for the following file:"))
				writemsg(    "!!!        Please ensure that your filesystem is intact, otherwise report\n")
				writemsg(    "!!!        this as a portage bug at bugs.gentoo.org. Append 'emerge info'.\n")
				writemsg(    "!!!        File:  "+str(mysrc)+"\n", noiselevel=-1)
				writemsg(    "!!!        Error: "+str(e)+"\n", noiselevel=-1)
				sys.exit(1)


			mymode = mystat[stat.ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydstat = os.lstat(mydest)
				mydmode = mydstat.st_mode
			except OSError, e:
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
				mymtime = movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings)
				if mymtime != None:
					writemsg_stdout(">>> %s -> %s\n" % (mydest, myto))
					outfile.write("sym "+myrealdest+" -> "+myto+" "+str(mymtime)+"\n")
				else:
					print "!!! Failed to move file."
					print "!!!", mydest, "->", myto
					sys.exit(1)
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
						writemsg("\n!!! Cannot write to '"+mydest+"'.\n", noiselevel=-1)
						writemsg("!!! Please check permissions and directories for broken symlinks.\n")
						writemsg("!!! You may start the merge process again by using ebuild:\n")
						writemsg("!!! ebuild "+self.settings["PORTDIR"]+"/"+self.cat+"/"+pkgstuff[0]+"/"+self.pkg+".ebuild merge\n")
						writemsg("!!! And finish by running this: env-update\n\n")
						return 1

					if stat.S_ISLNK(mydmode) or stat.S_ISDIR(mydmode):
						# a symlink to an existing directory will work for us; keep it:
						writemsg_stdout("--- %s/\n" % mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						if movefile(mydest, mydest+".backup", mysettings=self.settings) is None:
							sys.exit(1)
						print "bak", mydest, mydest+".backup"
						#now create our directory
						if self.settings.selinux_enabled():
							import selinux
							sid = selinux.get_sid(mysrc)
							selinux.secure_mkdir(mydest,sid)
						else:
							os.mkdir(mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
						os.chmod(mydest, mystat[0])
						os.chown(mydest, mystat[4], mystat[5])
						writemsg_stdout(">>> %s/\n" % mydest)
				else:
					#destination doesn't exist
					if self.settings.selinux_enabled():
						import selinux
						sid = selinux.get_sid(mysrc)
						selinux.secure_mkdir(mydest, sid)
					else:
						os.mkdir(mydest)
					os.chmod(mydest, mystat[0])
					os.chown(mydest, mystat[4], mystat[5])
					writemsg_stdout(">>> %s/\n" % mydest)
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
				if mydmode != None:
					# destination file exists
					if stat.S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						moveme = 0
						writemsg_stdout("!!! %s\n" % mydest)
					elif stat.S_ISREG(mydmode) or (stat.S_ISLNK(mydmode) and os.path.exists(mydest) and stat.S_ISREG(os.stat(mydest)[stat.ST_MODE])):
						cfgprot = 0
						# install of destination is blocked by an existing regular file,
						# or by a symlink to an existing regular file;
						# now, config file management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if self.isprotected(mydest):
							# we have a protection path; enable config file management.
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
										zing = "-o-"
										mymtime = long(mystat.st_mtime)
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
					mymtime = movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings)
					if mymtime is None:
						sys.exit(1)
					zing = ">>>"

				if mymtime != None:
					zing = ">>>"
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				writemsg_stdout("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing = "!!!"
				if mydmode is None:
					# destination doesn't exist
					if movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings) != None:
						zing = ">>>"
					else:
						sys.exit(1)
				if stat.S_ISFIFO(mymode):
					outfile.write("fif %s\n" % myrealdest)
				else:
					outfile.write("dev %s\n" % myrealdest)
				writemsg_stdout(zing + " " + mydest + "\n")

	def merge(self, mergeroot, inforoot, myroot, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		retval = -1
		self.lockdb()
		try:
			retval = self.treewalk(mergeroot, myroot, inforoot, myebuild,
				cleanup=cleanup, mydbapi=mydbapi, prev_mtimes=prev_mtimes)
			# Process ebuild logfiles
			elog_process(self.mycpv, self.settings, phasefilter=filter_mergephases)
			if retval == os.EX_OK and "noclean" not in self.settings.features:
				if myebuild is None:
					myebuild = os.path.join(inforoot, self.pkg + ".ebuild")
				doebuild(myebuild, "clean", myroot, self.settings,
					tree=self.treetype, mydbapi=mydbapi, vartree=self.vartree)
		finally:
			self.unlockdb()
		return retval

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		myfile = open(self.dbdir+"/"+name,"r")
		mydata = myfile.read().split()
		myfile.close()
		return " ".join(mydata)

	def copyfile(self,fname):
		import shutil
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))

	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		myfile = open(self.dbdir+"/"+fname,"r")
		mydata = myfile.read()
		myfile.close()
		return mydata

	def setfile(self,fname,data):
		write_atomic(os.path.join(self.dbdir, fname), data)

	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return []
		myelement = open(self.dbdir+"/"+ename,"r")
		mylines = myelement.readlines()
		myreturn = []
		for x in mylines:
			for y in x[:-1].split():
				myreturn.append(y)
		myelement.close()
		return myreturn

	def setelements(self,mylist,ename):
		myelement = open(self.dbdir+"/"+ename,"w")
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()

	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(os.path.join(self.dbdir, "CATEGORY"))

def tar_contents(contents, root, tar, protect=None, onProgress=None):
	from portage.util import normalize_path
	import tarfile
	root = normalize_path(root).rstrip(os.path.sep) + os.path.sep
	id_strings = {}
	maxval = len(contents)
	curval = 0
	if onProgress:
		onProgress(maxval, 0)
	paths = contents.keys()
	paths.sort()
	for path in paths:
		curval += 1
		try:
			lst = os.lstat(path)
		except OSError, e:
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
		# store numbers instead of real names like tar's --numeric-owner
		tarinfo.uname = id_strings.setdefault(tarinfo.uid, str(tarinfo.uid))
		tarinfo.gname = id_strings.setdefault(tarinfo.gid, str(tarinfo.gid))

		if stat.S_ISREG(lst.st_mode):
			# break hardlinks due to bug #185305
			tarinfo.type = tarfile.REGTYPE
			if protect and protect(path):
				# Create an empty file as a place holder in order to avoid
				# potential collision-protect issues.
				tarinfo.size = 0
				tar.addfile(tarinfo)
			else:
				f = open(path)
				try:
					tar.addfile(tarinfo, f)
				finally:
					f.close()
		else:
			tar.addfile(tarinfo)
		if onProgress:
			onProgress(maxval, curval)
