# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from restriction import base, AlwaysTrue
from inspect import isroutine
from restrictionSet import bases, OrRestrictionSet
from portage.util.inheritance import check_for_base

class DictBased(base):
	__slots__ = tuple(["restricts_dict", "get_pkg_key", "get_atom_key"] + base.__slots__)

	def __init__(self, restriction_items, get_key_from_package, get_key_from_atom, *args, **kwargs):
		"""restriction_items is a source of restriction keys and remaining restriction (if none, set it to None)
		get_key is a function to get the key from a pkg instance"""

		if not isroutine(get_key_from_package):
			raise TypeError(get_key_from_package)

		super(DictBased, self).__init__(*args, **kwargs)
		self.restricts_dict = {}
		for r in restriction_items:
			key, remaining = get_key_from_atom(r)
			if len(remaining) == 0:
				remaining = AlwaysTrue
			else:
				if len(remaining) == 1 and (isinstance(remaining, list) or isinstance(remaining, tuple)):
					remaining = remaining[0]
				if not isinstance(remaining, base):
					b = check_for_base(r, bases)
					if b == None:
						raise KeyError("unable to convert '%s', remaining '%s' isn't of a known base" % (str(r), str(remaining)))
					remaining = b(*remaining)

			if key in self.restricts_dict:
				self.restricts_dict[key].add_restriction(remaining)
			else:
				self.restricts_dict[key] = OrRestrictionSet(remaining)

		self.get_pkg_key, self.get_atom_key = get_key_from_package, get_key_from_atom


	def match(self, pkginst):
		try:
			key = self.get_pkg_key(pkginst)
		except (TypeError, AttributeError):
			return self.negate
		if key not in self.restricts_dict:
			return self.negate
	
		remaining = self.restricts_dict[key]
		return remaining.match(pkginst) ^ self.negate

			
	def __contains__(self, restriction):
		if isinstance(restriction, base):
			key, r = self.get_atom_key(restriction)
		if key != None and key in self.restricts_dict:
			return True
		return False


#	def __getitem__(self, restriction, default=None):
#		if isinstance(restriction, base):
#			key, r = self.get_atom_key(restriction)
#		if key == None:	return default
#		return self.restricts_dict.get(key, default)
#		
#
#	def __setitem__(self, restriction, val):
#		if isinstance(restriction, base):
#			key, r = self.get_atom_key(restriction)
#		if key == None:
#			raise KeyError("either passed in, or converted val became None, invalid as key")
#		self.restricts_dict[key] = val
#
#
#	def __delitem__(self, restriction):
#		if isinstance(restriction, base):
#			key = self.get_atom_key(restriction)
#		if key != None and key in self.restricts_dict:
#			del self.restricts_dict[key]
