# Copyright: 2005 Gentoo Foundation
# Author(s): Nicholas Carpaski (carpaski@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

from portage.util import normalize_path, writemsg
import errno, os, sys
from portage.data import portage_gid
from portage.exception import PermissionDenied

class cache(object):
	"""
	Maintains the cache information about eclasses used in ebuild.
	"""
	def __init__(self, porttree_root, overlays=[]):
		self.porttree_root = porttree_root

		self.eclasses = {} # {"Name": ("location","_mtime_")}
		self._eclass_locations = {}

		# screw with the porttree ordering, w/out having bash inherit match it, and I'll hurt you.
		# ~harring
		self.porttrees = [self.porttree_root]+overlays
		self.porttrees = tuple(map(normalize_path, self.porttrees))
		self._master_eclass_root = os.path.join(self.porttrees[0],"eclass")
		self._master_eclasses_overridden = {}
		self.update_eclasses()

	def close_caches(self):
		import traceback
		traceback.print_stack()
		print "%s close_cache is deprecated" % self.__class__
		self.eclasses.clear()

	def flush_cache(self):
		import traceback
		traceback.print_stack()
		print "%s flush_cache is deprecated" % self.__class__

		self.update_eclasses()

	def update_eclasses(self):
		self.eclasses = {}
		self._eclass_locations = {}
		master_eclasses = {}
		eclass_len = len(".eclass")
		ignored_listdir_errnos = (errno.ENOENT, errno.ENOTDIR)
		for x in [normalize_path(os.path.join(y,"eclass")) for y in self.porttrees]:
			try:
				eclass_filenames = os.listdir(x)
			except OSError, e:
				if e.errno in ignored_listdir_errnos:
					del e
					continue
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(x)
				raise
			for y in eclass_filenames:
				if not y.endswith(".eclass"):
					continue
				try:
					mtime = long(os.stat(os.path.join(x, y)).st_mtime)
				except OSError:
					continue
				ys=y[:-eclass_len]
				self.eclasses[ys] = (x, long(mtime))
				self._eclass_locations[ys] = x
				if x == self._master_eclass_root:
					master_eclasses[ys] = mtime
				else:
					master_mtime = master_eclasses.get(ys)
					if master_mtime and master_mtime != mtime:
						self._master_eclasses_overridden[ys] = x

	def is_eclass_data_valid(self, ec_dict):
		if not isinstance(ec_dict, dict):
			return False
		for eclass, tup in ec_dict.iteritems():
			cached_data = self.eclasses.get(eclass, None)
			""" Only use the mtime for validation since the probability of a
			collision is small and, depending on the cache implementation, the
			path may not be specified (cache from rsync mirrors, for example).
			"""
			if cached_data is None or tup[1] != cached_data[1]:
				return False

		return True

	def get_eclass_data(self, inherits, from_master_only=False):
		ec_dict = {}
		for x in inherits:
			try:
				ec_dict[x] = self.eclasses[x]
			except KeyError:
				print "ec=",ec_dict
				print "inherits=",inherits
				raise
			if from_master_only and \
				self._eclass_locations[x] != self._master_eclass_root:
				return None

		return ec_dict
