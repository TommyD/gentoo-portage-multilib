# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import os, stat
from portage.repository import prototype, errors
#import ebuild_internal
import ebuild_package

class tree(prototype.tree):
	false_categories = ("eclass","profiles","packages","distfiles","licenses","scripts")

	def __init__(self, location, cache=None, eclass_cache=None):
		super(tree, self).__init__()
		self.base = location
		try:	
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)
		if eclass_cache == None:
			import eclass_cache
			eclass_cache = eclass_cache.cache(self.base)
		self.metadata = ebuild_package.ebuild_factory(self, cache, eclass_cache)

	def _get_categories(self, *optionalCategory):
		# why the auto return?  current porttrees don't allow/support categories deeper then one dir.
		if len(optionalCategory):
			#raise KeyError
			return ()

		try:	return tuple([x for x in os.listdir(self.base) \
			if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode) and x not in self.false_categories])

		except (OSError, IOError), e:
			raise KeyError("failed fetching categories: %s" % str(e))

	def _get_packages(self, category):

		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		try:	return tuple([x for x in os.listdir(cpath) \
			if stat.S_ISDIR(os.lstat(os.path.join(cpath,x)).st_mode)])

		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
			(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))

	def _get_versions(self, catpkg):

		pkg = catpkg.split("/")[-1]
		cppath = os.path.join(self.base, catpkg.lstrip(os.path.sep))
		# 7 == len(".ebuild")
		try:	return tuple([x[len(pkg):-7].lstrip("-") for x in os.listdir(cppath) \
			if x.endswith(".ebuild") and x.startswith(pkg) and  \
			stat.S_ISREG(os.lstat(os.path.join(cppath,x)).st_mode)])

		except (OSError, IOError), e:
			raise KeyError("failed fetching versions for package %s: %s" % \
			(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))

