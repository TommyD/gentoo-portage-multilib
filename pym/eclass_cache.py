# Copyright: 2005 Gentoo Foundation
# Author(s): Nicholas Carpaski (carpaski@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

from portage_util import normalize_path, writemsg
import os, sys
from portage_data import portage_gid

class cache:
	"""
	Maintains the cache information about eclasses used in ebuild.
	"""
	def __init__(self, porttree_root, overlays=[]):
		self.porttree_root = porttree_root

		self.eclasses = {} # {"Name": ("location","_mtime_")}

		# screw with the porttree ordering, w/out having bash inherit match it, and I'll hurt you.
		# ~harring
		self.porttrees = [self.porttree_root]+overlays
		self.porttrees = tuple(map(normalize_path, self.porttrees))
		self._master_eclass_root = os.path.join(self.porttrees[0],"eclass")
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
		eclass_len = len(".eclass")
		for x in [normalize_path(os.path.join(y,"eclass")) for y in self.porttrees]:
			if not os.path.isdir(x):
				continue
			for y in [y for y in os.listdir(x) if y.endswith(".eclass")]:
				try:
					mtime = long(os.stat(os.path.join(x, y)).st_mtime)
				except OSError:
					continue
				ys=y[:-eclass_len]
				self.eclasses[ys] = (x, long(mtime))
	
	def is_eclass_data_valid(self, ec_dict):
		if not isinstance(ec_dict, dict):
			return False
		for eclass, tup in ec_dict.iteritems():
			if eclass not in self.eclasses or tuple(tup) != self.eclasses[eclass]:
				return False

		return True

	def get_eclass_data(self, inherits, from_master_only=False):
		ec_dict = {}
		for x in inherits:
			try:
				ec_dict[x] = self.eclasses[x]
			except:
				print "ec=",ec_dict
				print "inherits=",inherits
				raise
			if from_master_only and self.eclasses[x][0] != self._master_eclass_root:
				return None

		return ec_dict
