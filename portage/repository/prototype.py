# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.util.dicts import IndexableSequence
from weakref import proxy

def ix_cat_callable(*cat):
	return "/".join(cat)

class tree(object):
	package_class = None

	def __init__(self, frozen=True):
		self.categories = IndexableSequence(self._get_categories, self._get_categories, 
			returnIterFunc=ix_cat_callable, returnEmpty=True, modifiable=(not frozen))
		self.packages   = IndexableSequence(self.categories.iterkeys, self._get_packages, \
			returnIterFunc=lambda x,y: str(x)+"/"+str(y), modifiable=(not frozen))
		self.versions   = IndexableSequence(self.packages.__iter__, self._get_versions, \
			returnIterFunc=lambda x,y: str(x)+"-"+str(y), modifiable=(not frozen))
		self.raw_repo = proxy(self)
		self.frozen = frozen


	def _get_categories(self, *arg):
		raise NotImplementedError


	def _get_packages(self, category):
		raise NotImplementedError


	def _get_versions(self, package):
		raise NotImplementedError


	def __getitem__(self, cpv):
		cpv_inst = self.package_class(cpv)
		if cpv_inst.fullver not in self.versions[cpv_inst.key]:
			del cpv_inst
			raise KeyError(cpv)
		return cpv_inst


	def __setitem__(self, *values):
		raise AttributeError


	def __delitem__(self, cpv):
		raise AttributeError


	def __iter__(self):
		for cpv in self.versions:
			yield self.package_class(cpv)
		return


	def match(self, atom):
		return list(self.itermatch(atom))


	def itermatch(self, atom):
		if atom.category == None:
			candidates = self.packages
		else:
			if atom.package == None:
				try:	candidates = self.packages[atom.category]
				except KeyError:
					# just stop now.  no category matches == no yielded cpvs.
					return
			else:
				try:
					if atom.package not in self.packages[atom.category]:
						# no matches possible
						return
					candidates = [atom.key]

				except KeyError:
					# atom.category wasn't valid.  no matches possible.
					return

		#actual matching.
		for catpkg in candidates:
			for ver in self.versions[catpkg]:
				if atom.match(self.package_class(catpkg+"-"+ver)):
					yield self[catpkg+"-"+ver]
		return


	def add_package(self, pkg):
		if self.frozen:
			raise AttributeError,"repo is frozen"
		return self._add_new_package(self, pkg)


	def _add_new_package(self, pkg):
		raise NotImplementedError


	def del_package(self, key):
		if self.frozen:
			raise AttributeError,"repo is frozen"
		return self._del_package(self,key)


	def _del_package(self,pkg):
		raise NotImplementedError
