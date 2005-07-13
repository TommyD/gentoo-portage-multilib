# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import os
from portage import package

class ebuild_package(package.metadata.package):

	def __getattr__(self, key):
		if key == "path":
			return self.__dict__.setdefault("path", os.path.join(self.__dict__["_parent"].base, \
				self.category,	self.package, "%s-%s.ebuild" % (self.package, self.fullver)))

		if key == "_mtime_":
			#XXX wrap this.
			return self.__dict__.setdefault("_mtime_",long(os.stat(self.path).st_mtime))
		elif key == "P":
			return self.__dict__.setdefault("P", self.package + "-" + self.version)
		elif key == "PN":
			return self.__dict__.setdefault("PN", self.package)
		elif key == "PR":
			return self.__dict__.setdefault("PR", "-r"+str(self.revision))

		return super(ebuild_package, self).__getattr__(key)


	def _fetch_metadata(self):
#		import pdb;pdb.set_trace()
		data = self._parent._get_metadata(self)
		doregen = False
		if data == None:
			doregen = True

		# got us a dict.  yay.
		if not doregen:
			if self._mtime_ != data.get("_mtime_"):
				doregen = True
			elif data.get("_eclasses_") != None and not self._parent._ecache.is_eclass_data_valid(data["_eclasses_"]):
				doregen = True

		if doregen:
			# ah hell.
			data = self._parent._update_metadata(self)

#		for k,v in data.items():
#			self.__dict__[k] = v

#		self.__dict__["_finalized"] = True
		return data


class ebuild_factory(package.metadata.factory):
	child_class = ebuild_package

	def __init__(self, parent, cachedb, eclass_cache, *args,**kwargs):
		super(ebuild_factory, self).__init__(parent, *args,**kwargs)
		self._cache = cachedb
		self._ecache = eclass_cache
		self.base = self._parent_repo.base

	def _get_metadata(self, pkg):
		if self._cache != None:
			try:
				return self._cache[pkg.cpvstr]
			except KeyError:
				pass
		return None

	def _update_metadata(self, pkg):

		import processor
		ebp=processor.request_ebuild_processor()
		mydata = ebp.get_keys(pkg, self._ecache)
		processor.release_ebuild_processor(ebp)

		mydata["_mtime_"] = pkg._mtime_
		if mydata.get("INHERITED", False):
			mydata["_eclasses_"] = self.eclassdb.get_eclass_data(mydata["INHERITED"].split() )
			del mydata["INHERITED"]
		else:
			mydata["_eclasses_"] = {}

		if self._cache != None:
			self._cache[pkg.cpvstr] = mydata

		return mydata

