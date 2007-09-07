# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from portage.util import grabfile_package, stack_lists
from portage.sets import PackageSet

class PackagesSystemSet(PackageSet):
	_operations = ["merge"]

	def __init__(self, name, profile_paths):
		super(PackagesSystemSet, self).__init__(name)
		self._profile_paths = profile_paths
		self.description = "System packages for profile %s" % self._profile_paths[-1]
	
	def load(self):
		mylist = [grabfile_package(os.path.join(x, "packages")) for x in self._profile_paths]
		mylist = stack_lists(mylist, incremental=1)
		self._setAtoms([x[1:] for x in mylist if x[0] == "*"])
