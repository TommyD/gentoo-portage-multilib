# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# hack, remove when it's fixed
raise Exception("sorry, this won't work with current portage namespace layout.  plsfix, kthnx")

import os,stat
import prototype, errors

#needed to grab the PN
import portage_versions

class tree(prototype.tree):
	def __init__(self, base):
		super(tree,self).__init__()
		self.base = base
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)


	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if len(optionalCategory):
			return {}

		try:	return tuple([x for x in os.listdir(self.base) \
			if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode) and x != "All"])

		except (OSError, IOError), e:
			raise KeyError("failed fetching categories: %s" % str(e))
	
	def _get_packages(self, category):
		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		l=[]
		try:    
			for x in os.listdir(cpath):
				if stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) and not x.endswith(".lockfile"):
					l.append(portage_versions.pkgsplit(x)[0])
			return tuple(l)

		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
			(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))


	def _get_versions(self, catpkg):
		pkg = catpkg.split("/")[-1]
		l=[]
		try:
			cpath=os.path.join(self.base, os.path.dirname(catpkg.lstrip("/").rstrip("/")))
			for x in os.listdir(cpath):
				if x.startswith(pkg) and stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) and not x.endswith(".lockfile"):
					ver=portage_versions.pkgsplit(x)

					#pkgsplit returns -r0, when it's not always there
					if ver[2] == "r0":
						if x.endswith(ver[2]):
							l.append("%s-%s" % (ver[1], ver[2]))
						else:
							l.append(ver[1])
					else:
						l.append("%s-%s" % (ver[1], ver[2]))
			return tuple(l)
		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for package %s: %s" % \
			(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))
			
