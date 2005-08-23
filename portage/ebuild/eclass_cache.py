# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.util.fs import normpath
import os, sys

class cache:
	"""
	Maintains the cache information about eclasses used in ebuild.
	get_eclass_path and get_eclass_data are special- one (and only one) can be set to None.
	Any code trying to get eclass data/path will choose which method it prefers, falling back to what's available if only one option
	exists.

	get_eclass_path should be defined when local path is possible/preferable.
	get_eclass_data should be defined when dumping the eclass down the pipe is preferable/required (think remote tree)

	Base defaults to having both set (it's local, and i.  Override as needed.
	"""
	def __init__(self, porttree, *additional_porttrees):
		self.eclasses = {} # {"Name": ("location","_mtime_")}

		self.porttrees = tuple(map(normpath, [porttree] + list(additional_porttrees)))
		self._master_eclass_root = os.path.join(self.porttrees[0],"eclass")
		self.update_eclasses()


	def update_eclasses(self):
		self.eclasses = {}
		eclass_len = len(".eclass")
		for x in [normpath(os.path.join(y,"eclass")) for y in self.porttrees]:
			if not os.path.isdir(x):
				continue
			for y in [y for y in os.listdir(x) if y.endswith(".eclass")]:
				try:
					mtime=os.stat(x+"/"+y).st_mtime
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

	def get_eclass_path(self, eclass):
		"""get on disk eclass path.  remote implementations need a way to say 'piss off tool' if this is called..."""
		return os.path.join(self.eclasses[eclass][0],eclass+".eclass")

	def get_eclass_contents(self, eclass):
		"""Get the actual contents of the eclass.  This should be overridden for remote implementations"""
		f=file(os.path.join(self.eclasses[eclass][0], eclass+".eclass"),"r")
		l=f.read()
		f.close()
		return l
