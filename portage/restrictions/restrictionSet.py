# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import restriction

class RestrictionSet(restriction.base):
	__slots__ = tuple(["restrictions"] + restriction.base.__slots__)

	def __init__(self, *restrictions, **kwds):
		super(RestrictionSet, self).__init__(**kwds)
		for x in restrictions:
			if not isinstance(x, restriction.base):
				#bad monkey.
				raise TypeError, x
		self.restrictions = restrictions


	def addRestriction(self, NewRestriction):
		if not isinstance(NewRestriction, restriction.base):
			raise TypeError, NewRestriction

		self.restrictions.append(NewRestriction)


	def pmatch(self, packagedataInstance):
		raise NotImplementedError


	def finalize(self):
		self.restrictions = tuple(self.restrictions)


class AndRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if not rest.match(packagedataInstance):
				return self.negate
		return not self.negate


class OrRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if rest.match(packagedataInstance):
				return self.negate
		return not self.negate


