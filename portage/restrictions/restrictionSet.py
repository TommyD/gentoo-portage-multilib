# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import restriction

class RestrictionSet(restriction.base):
	__slots__ = tuple(["restrictions"] + restriction.base.__slots__)

	def __init__(self, *restrictions, **kwds):
		if "finalize" in kwds:
			finalize = kwds["finalize"]
			del kwds["finalize"]
		else:
			finalize = False
		super(RestrictionSet, self).__init__(**kwds)
		for x in restrictions:
			if not isinstance(x, restriction.base):
				#bad monkey.
				raise TypeError, x

		if finalize:
			self.restrictions = tuple(restrictions)
		else:
			self.restrictions = list(restrictions)


	def add_restriction(self, NewRestriction, strict=True):
		if strict and not isinstance(NewRestriction, restriction.base):
			raise TypeError, NewRestriction

		self.restrictions.append(NewRestriction)

	def finalize(self):
		self.restrictions = tuple(self.restrictions)

	def total_len(self):	return sum(map(lambda x: x.total_len(), self.restrictions)) + 1

	def __len__(self):	return len(self.restrictions)

	def __iter__(self):	return iter(self.restrictions)

	def __getitem__(self, key):
		return self.restrictions[key]

class AndRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if not rest.match(packagedataInstance):
				return self.negate
		return not self.negate


#	def intersect(self, other):

	def __str__(self):
		if self.negate:	s=" !& "
		else:					s=" && "
		return '( %s )' % s.join(map(str,self.restrictions))


class OrRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if rest.match(packagedataInstance):
				return not self.negate
		return self.negate

	def __str__(self):
		if self.negate:	s=" !| "
		else:					s=" || "
		return '( %s )' % s.join(map(str,self.restrictions))


class XorRestrictionSet(RestrictionSet):
	__slots__ = tuple(RestrictionSet.__slots__)

	def match(self, pkginst):
		armed = False
		for rest in self.restrictions:
			if rest.match(pkginst):
				if armed:
					return self.negate
				armed = True
		return armed ^ self.negate

	def __str__(self):
		if self.negate:	s=" !^ "
		else:					s=" ^^ "
		return '( %s )' % s.join(map(str,self.restrictions))


bases = (AndRestrictionSet, OrRestrictionSet, XorRestrictionSet)
