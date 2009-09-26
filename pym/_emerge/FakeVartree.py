# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import sys

import portage
from portage import os
from _emerge.Package import Package
from _emerge.PackageVirtualDbapi import PackageVirtualDbapi

if sys.hexversion >= 0x3000000:
	long = int

class FakeVartree(portage.vartree):
	"""This is implements an in-memory copy of a vartree instance that provides
	all the interfaces required for use by the depgraph.  The vardb is locked
	during the constructor call just long enough to read a copy of the
	installed package information.  This allows the depgraph to do it's
	dependency calculations without holding a lock on the vardb.  It also
	allows things like vardb global updates to be done in memory so that the
	user doesn't necessarily need write access to the vardb in cases where
	global updates are necessary (updates are performed when necessary if there
	is not a matching ebuild in the tree)."""
	def __init__(self, root_config, pkg_cache=None, acquire_lock=1):
		self._root_config = root_config
		if pkg_cache is None:
			pkg_cache = {}
		real_vartree = root_config.trees["vartree"]
		portdb = root_config.trees["porttree"].dbapi
		self.root = real_vartree.root
		self.settings = real_vartree.settings
		mykeys = list(real_vartree.dbapi._aux_cache_keys)
		if "_mtime_" not in mykeys:
			mykeys.append("_mtime_")
		self._db_keys = mykeys
		self._pkg_cache = pkg_cache
		self.dbapi = PackageVirtualDbapi(real_vartree.settings)
		vdb_path = os.path.join(self.root, portage.VDB_PATH)
		try:
			# At least the parent needs to exist for the lock file.
			portage.util.ensure_dirs(vdb_path)
		except portage.exception.PortageException:
			pass
		vdb_lock = None
		try:
			if acquire_lock and os.access(vdb_path, os.W_OK):
				vdb_lock = portage.locks.lockdir(vdb_path)
			real_dbapi = real_vartree.dbapi
			slot_counters = {}
			for cpv in real_dbapi.cpv_all():
				cache_key = ("installed", self.root, cpv, "nomerge")
				pkg = self._pkg_cache.get(cache_key)
				if pkg is not None:
					metadata = pkg.metadata
				else:
					metadata = dict(zip(mykeys, real_dbapi.aux_get(cpv, mykeys)))
				myslot = metadata["SLOT"]
				mycp = portage.cpv_getkey(cpv)
				myslot_atom = "%s:%s" % (mycp, myslot)
				try:
					mycounter = long(metadata["COUNTER"])
				except ValueError:
					mycounter = 0
					metadata["COUNTER"] = str(mycounter)
				other_counter = slot_counters.get(myslot_atom, None)
				if other_counter is not None:
					if other_counter > mycounter:
						continue
				slot_counters[myslot_atom] = mycounter
				if pkg is None:
					pkg = Package(built=True, cpv=cpv,
						installed=True, metadata=metadata,
						root_config=root_config, type_name="installed")
				self._pkg_cache[pkg] = pkg
				self.dbapi.cpv_inject(pkg)
			real_dbapi.flush_cache()
		finally:
			if vdb_lock:
				portage.locks.unlockdir(vdb_lock)
		# Populate the old-style virtuals using the cached values.
		if not self.settings.treeVirtuals:
			self.settings._populate_treeVirtuals(self)

		# Intialize variables needed for lazy cache pulls of the live ebuild
		# metadata.  This ensures that the vardb lock is released ASAP, without
		# being delayed in case cache generation is triggered.
		self._aux_get = self.dbapi.aux_get
		self.dbapi.aux_get = self._aux_get_wrapper
		self._match = self.dbapi.match
		self.dbapi.match = self._match_wrapper
		self._aux_get_history = set()
		self._portdb_keys = ["EAPI", "DEPEND", "RDEPEND", "PDEPEND"]
		self._portdb = portdb
		self._global_updates = None

	def _match_wrapper(self, cpv, use_cache=1):
		"""
		Make sure the metadata in Package instances gets updated for any
		cpv that is returned from a match() call, since the metadata can
		be accessed directly from the Package instance instead of via
		aux_get().
		"""
		matches = self._match(cpv, use_cache=use_cache)
		for cpv in matches:
			if cpv in self._aux_get_history:
				continue
			self._aux_get_wrapper(cpv, [])
		return matches

	def _aux_get_wrapper(self, pkg, wants):
		if pkg in self._aux_get_history:
			return self._aux_get(pkg, wants)
		self._aux_get_history.add(pkg)
		try:
			# Use the live ebuild metadata if possible.
			live_metadata = dict(zip(self._portdb_keys,
				self._portdb.aux_get(pkg, self._portdb_keys)))
			if not portage.eapi_is_supported(live_metadata["EAPI"]):
				raise KeyError(pkg)
			self.dbapi.aux_update(pkg, live_metadata)
		except (KeyError, portage.exception.PortageException):
			if self._global_updates is None:
				self._global_updates = \
					grab_global_updates(self._portdb.porttree_root)
			perform_global_updates(
				pkg, self.dbapi, self._global_updates)
		return self._aux_get(pkg, wants)

	def sync(self, acquire_lock=1):
		"""
		Call this method to synchronize state with the real vardb
		after one or more packages may have been installed or
		uninstalled.
		"""
		vdb_path = os.path.join(self.root, portage.VDB_PATH)
		try:
			# At least the parent needs to exist for the lock file.
			portage.util.ensure_dirs(vdb_path)
		except portage.exception.PortageException:
			pass
		vdb_lock = None
		try:
			if acquire_lock and os.access(vdb_path, os.W_OK):
				vdb_lock = portage.locks.lockdir(vdb_path)
			self._sync()
		finally:
			if vdb_lock:
				portage.locks.unlockdir(vdb_lock)

	def _sync(self):

		real_vardb = self._root_config.trees["vartree"].dbapi
		current_cpv_set = frozenset(real_vardb.cpv_all())
		pkg_vardb = self.dbapi
		aux_get_history = self._aux_get_history

		# Remove any packages that have been uninstalled.
		for pkg in list(pkg_vardb):
			if pkg.cpv not in current_cpv_set:
				pkg_vardb.cpv_remove(pkg)
				aux_get_history.discard(pkg.cpv)

		# Validate counters and timestamps.
		slot_counters = {}
		root = self.root
		validation_keys = ["COUNTER", "_mtime_"]
		for cpv in current_cpv_set:

			pkg_hash_key = ("installed", root, cpv, "nomerge")
			pkg = pkg_vardb.get(pkg_hash_key)
			if pkg is not None:
				counter, mtime = real_vardb.aux_get(cpv, validation_keys)
				try:
					counter = long(counter)
				except ValueError:
					counter = 0

				if counter != pkg.counter or \
					mtime != pkg.mtime:
					pkg_vardb.cpv_remove(pkg)
					aux_get_history.discard(pkg.cpv)
					pkg = None

			if pkg is None:
				pkg = self._pkg(cpv)

			other_counter = slot_counters.get(pkg.slot_atom)
			if other_counter is not None:
				if other_counter > pkg.counter:
					continue

			slot_counters[pkg.slot_atom] = pkg.counter
			pkg_vardb.cpv_inject(pkg)

		real_vardb.flush_cache()

	def _pkg(self, cpv):
		root_config = self._root_config
		real_vardb = root_config.trees["vartree"].dbapi
		pkg = Package(cpv=cpv, installed=True,
			metadata=zip(self._db_keys,
			real_vardb.aux_get(cpv, self._db_keys)),
			root_config=root_config,
			type_name="installed")

		try:
			mycounter = long(pkg.metadata["COUNTER"])
		except ValueError:
			mycounter = 0
			pkg.metadata["COUNTER"] = str(mycounter)

		return pkg

def grab_global_updates(portdir):
	from portage.update import grab_updates, parse_updates
	updpath = os.path.join(portdir, "profiles", "updates")
	try:
		rawupdates = grab_updates(updpath)
	except portage.exception.DirectoryNotFound:
		rawupdates = []
	upd_commands = []
	for mykey, mystat, mycontent in rawupdates:
		commands, errors = parse_updates(mycontent)
		upd_commands.extend(commands)
	return upd_commands

def perform_global_updates(mycpv, mydb, mycommands):
	from portage.update import update_dbentries
	aux_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	aux_dict = dict(zip(aux_keys, mydb.aux_get(mycpv, aux_keys)))
	updates = update_dbentries(mycommands, aux_dict)
	if updates:
		mydb.aux_update(mycpv, updates)
