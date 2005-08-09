# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

"""
This module provides classes that can be used to combine arbitrary collections of restrictions in AND, NAND, OR, NOR, XOR, XNOR 
style operations.
"""

import restriction
from itertools import imap
__all__ = ("AndRestrictionSet", "OrRestrictionSet", "XorRestrictionSet")

class RestrictionSet(restriction.base):
	__slots__ = tuple(["restrictions"] + restriction.base.__slots__)

	def __init__(self, *restrictions, **kwds):
		"""Optionally hand in (positionally) restrictions to use as the basis of this restriction
		finalize=False, set it to True to notify this instance to internally finalize itself (no way to reverse it yet)
		negate=False, controls whether matching results are negated
		"""
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


	def add_restriction(self, *new_restrictions, **kwds):
		"""add restriction(s)
		strict=True, set to false to disable isinstance checks to ensure all restrictions are restriction.base derivatives
		"""
		if len(new_restrictions) == 0:
			raise TypeError("need at least one restriction handed in")
		if kwds.get("strict", True):
			for r in new_restrictions:
				if not isinstance(r, restriction.base):
					raise TypeError("instance '%s' isn't a restriction.base, and strict is on" % r)
		
		self.restrictions.extend(new_restrictions)

	def finalize(self):
		self.restrictions = tuple(self.restrictions)

	def total_len(self):	return sum(imap(lambda x: x.total_len(), self.restrictions)) + 1

	def __len__(self):	return len(self.restrictions)

	def __iter__(self):	return iter(self.restrictions)

	def __getitem__(self, key):
		return self.restrictions[key]

def unwind_changes(pkg, pop_count, negate):
	while pop_count:
		pkg.pop_change()
		pop_count-=1
	if negate:
		return pkg
	return None

class AndRestrictionSet(RestrictionSet):
	"""Boolean AND grouping of restrictions."""
	__slots__ = tuple(RestrictionSet.__slots__)

	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if not rest.match(packagedataInstance):
				return self.negate
		return not self.negate

	def cmatch(self, pkg):
		entry_point = pkg.changes_count()
		for rest in self.restrictions:
			if c.match(pkg) == False:
				pkg.rollback_changes(entry_point)
				if self.negate:	return pkg
				return self.negate

		# for this to be reached, things went well.
		if self.negate:
			pkg.rollback_changes(entry_point)
			# yes, normally it's "not negate", but we no negates status already via the if
			return False
		return True

	def __str__(self):
		if self.negate:	return "not ( %s )" % " && ".join(imap(str, self.restrictions))
		return "( %s )" % " && ".join(imap(str, self.restrictions))


class OrRestrictionSet(RestrictionSet):
	"""Boolean OR grouping of restrictions."""
	__slots__ = tuple(RestrictionSet.__slots__)
	
	def match(self, packagedataInstance):
		for rest in self.restrictions:
			if rest.match(packagedataInstance):
				return not self.negate
		return self.negate

	def cmatch(self, pkg):
		entry_point = pkg.changes_count()
		for rest in self.restrictions:
			if rest.cmatch(pkg) == True:
				if self.negate:
					pkg.rollback_changes(entry_point)
				return not self.negate
			else:
				pkg.rollback_changes(entry_point)

		if self.negate:
			pkg.rollback_changes(entry_point)
		return self.negate

	def __str__(self):
		if self.negate:	return "not ( %s )" % " || ".join(imap(str, self.restrictions))
		return "( %s )" % " || ".join(imap(str, self.restrictions))


class XorRestrictionSet(RestrictionSet):
	"""Boolean XOR grouping of restrictions."""
	__slots__ = tuple(RestrictionSet.__slots__)

	def match(self, pkginst):
		armed = False
		for rest in self.restrictions:
			if rest.match(pkginst):
				if armed:
					return self.negate
				armed = True
		return armed ^ self.negate

	def cmatch(self, pkg):
		entry_point = None
		armed = False
		for ret in self.restrictions:
			node_entry_point = pkg.changes_count()
			if rest.cmatch(pkg):
				if armed:
					pkg.rollback_changes(entry_point)
					return self.negate
				armed = True
			else:
				pkg.rollback_changes(node_entry_point)

		if self.negate and entry_point != None:
			pkg.rollback_changes(entry_point)
		return armed ^ self.negate

	def __str__(self):
		if self.negate:	return "not ( %s )" % " ^^ ".join(imap(str, self.restrictions))
		return "( %s )" % " ^^ ".join(imap(str, self.restrictions))


bases = (AndRestrictionSet, OrRestrictionSet, XorRestrictionSet)
