# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import sys

import portage
from portage import os
from portage import digraph
from portage.sets.base import InternalPackageSet

from _emerge.BlockerCache import BlockerCache
from _emerge.FakeVartree import FakeVartree
from _emerge.show_invalid_depstring_notice import show_invalid_depstring_notice

if sys.hexversion >= 0x3000000:
	long = int

class BlockerDB(object):

	def __init__(self, root_config):
		self._root_config = root_config
		self._vartree = root_config.trees["vartree"]
		self._portdb = root_config.trees["porttree"].dbapi

		self._dep_check_trees = None
		self._fake_vartree = None

	def _get_fake_vartree(self, acquire_lock=0):
		fake_vartree = self._fake_vartree
		if fake_vartree is None:
			fake_vartree = FakeVartree(self._root_config,
				acquire_lock=acquire_lock)
			self._fake_vartree = fake_vartree
			self._dep_check_trees = { self._vartree.root : {
				"porttree"    :  fake_vartree,
				"vartree"     :  fake_vartree,
			}}
		else:
			fake_vartree.sync(acquire_lock=acquire_lock)
		return fake_vartree

	def findInstalledBlockers(self, new_pkg, acquire_lock=0):
		blocker_cache = BlockerCache(self._vartree.root, self._vartree.dbapi)
		dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		settings = self._vartree.settings
		stale_cache = set(blocker_cache)
		fake_vartree = self._get_fake_vartree(acquire_lock=acquire_lock)
		dep_check_trees = self._dep_check_trees
		vardb = fake_vartree.dbapi
		installed_pkgs = list(vardb)

		for inst_pkg in installed_pkgs:
			stale_cache.discard(inst_pkg.cpv)
			cached_blockers = blocker_cache.get(inst_pkg.cpv)
			if cached_blockers is not None and \
				cached_blockers.counter != long(inst_pkg.metadata["COUNTER"]):
				cached_blockers = None
			if cached_blockers is not None:
				blocker_atoms = cached_blockers.atoms
			else:
				# Use aux_get() to trigger FakeVartree global
				# updates on *DEPEND when appropriate.
				depstr = " ".join(vardb.aux_get(inst_pkg.cpv, dep_keys))
				try:
					portage.dep._dep_check_strict = False
					success, atoms = portage.dep_check(depstr,
						vardb, settings, myuse=inst_pkg.use.enabled,
						trees=dep_check_trees, myroot=inst_pkg.root)
				finally:
					portage.dep._dep_check_strict = True
				if not success:
					pkg_location = os.path.join(inst_pkg.root,
						portage.VDB_PATH, inst_pkg.category, inst_pkg.pf)
					portage.writemsg("!!! %s/*DEPEND: %s\n" % \
						(pkg_location, atoms), noiselevel=-1)
					continue

				blocker_atoms = [atom for atom in atoms \
					if atom.startswith("!")]
				blocker_atoms.sort()
				counter = long(inst_pkg.metadata["COUNTER"])
				blocker_cache[inst_pkg.cpv] = \
					blocker_cache.BlockerData(counter, blocker_atoms)
		for cpv in stale_cache:
			del blocker_cache[cpv]
		blocker_cache.flush()

		blocker_parents = digraph()
		blocker_atoms = []
		for pkg in installed_pkgs:
			for blocker_atom in blocker_cache[pkg.cpv].atoms:
				blocker_atom = blocker_atom.lstrip("!")
				blocker_atoms.append(blocker_atom)
				blocker_parents.add(blocker_atom, pkg)

		blocker_atoms = InternalPackageSet(initial_atoms=blocker_atoms)
		blocking_pkgs = set()
		for atom in blocker_atoms.iterAtomsForPackage(new_pkg):
			blocking_pkgs.update(blocker_parents.parent_nodes(atom))

		# Check for blockers in the other direction.
		depstr = " ".join(new_pkg.metadata[k] for k in dep_keys)
		try:
			portage.dep._dep_check_strict = False
			success, atoms = portage.dep_check(depstr,
				vardb, settings, myuse=new_pkg.use.enabled,
				trees=dep_check_trees, myroot=new_pkg.root)
		finally:
			portage.dep._dep_check_strict = True
		if not success:
			# We should never get this far with invalid deps.
			show_invalid_depstring_notice(new_pkg, depstr, atoms)
			assert False

		blocker_atoms = [atom.lstrip("!") for atom in atoms \
			if atom[:1] == "!"]
		if blocker_atoms:
			blocker_atoms = InternalPackageSet(initial_atoms=blocker_atoms)
			for inst_pkg in installed_pkgs:
				try:
					next(blocker_atoms.iterAtomsForPackage(inst_pkg))
				except (portage.exception.InvalidDependString, StopIteration):
					continue
				blocking_pkgs.add(inst_pkg)

		return blocking_pkgs

