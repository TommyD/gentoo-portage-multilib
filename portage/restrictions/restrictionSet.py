# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import restriction

class RestrictionSet(restriction.Restriction):
	__slots__ = ("restrictions")

	def __init__(self, initialRestrictions=[]):
		for x in initialRestrictions:
			if not isinstance(x, Restriction.Restriction):
				#bad monkey.
				raise TypeError, x
		self.restrictions = list(initialRestrictions)


	def addRestriction(self, NewRestriction):
		if not isinstance(NewRestriction, Restriction.Restriction):
			raise TypeError, NewRestriction

		self.restrictions.append(NewRestriction)


	def get_tree_restrictions(self):
		l = []
		for x in self.restrictions:
			if isinstance(x, restriction.RestrictionSet):
				l2 = x.get_tree_restrictions()
				if len(l2):
					l.append(l2)
			elif not isinstance(x, restriction.ConfigRestriction):
				l.append(x)
		return self.__class__(l)
				

	def get_conditionals(self):
		l = []
		for x in self.restrictions:
			if isinstance(x, restriction.RestrictionSet):
				l2 = x.get_conditionals()
				if len(l2):
					l.append(l2)
			elif isinstance(x, restriction.ConfigRestriction):
				l.append(x)
		return self.__class__(l)


	def pmatch(self, packagedataInstance):
		raise NotImplementedError


	def finalize(self):
		self.restrictions = tuple(self.restrictions)


class AndRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if not rest.pmatch(packagedataInstance):
				return False
		return True


class OrRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if rest.pmatch(packagedataInstance):
				return True
		return False


# this may not be used.  intended as a way to identify a restrictionSet as specifically identifying a package.
# resolver shouldn't need it anymore
class PackageRestriction(AndRestrictionSet):
        pass

