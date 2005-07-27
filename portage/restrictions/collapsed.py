# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from restriction import base
from inspect import isroutine

class DictBased(base):
	__slots__ = tuple(["restricts_dict", "get_key", "get_atom_key"] + base.__slots__)
	def __init__(self, restriction_items, get_key, get_key_from_atom, *args, **kwargs)
		"""restriction_items is a source of restriction keys and remaining restriction (if none, set it to None)
		get_key is a function to get the key from a pkg instance"""

		if not isroutine(get_key):
			raise TypeError(get_key)

		super(LookupBase, self).__init__(*args, **kwargs)
		restricts_dict = {}
		for r in restrictions:
			key, remaining = chunk_it
			restricts_dict[key] = remaining
		self.get_key, self.get_atom_key = get_key, get_key_from_atom


	def match(self, pkginst):
		try:
			key = self.get_key(pkginst)
		except (TypeError, AttributeError):
			return self.negate
		remaining = self.restricts_dict.get(key, False)
		if remaining == False:
			return self.negate
		elif remaining == None:
			return not self.negate
		return remaining.match(pkginst) ^ self.negate
			
	def __contains__(self, restriction):
		if isinstance(key, base):
			key = get_atom_key(restriction):
		if key != None and key in self.restricts_dict:
			return True
		return False

	def __getitem__(self, key, default=None):
		if isinstance(key, base):
			key = get_atom_key(restriction):
		if key == None:	return default
		return self.restricts_dict.get(key, default)
		
	def __setitem__(self, key, val):
		if isinstance(key, base):
			key = get_atom_key(restriction):
		if key == None:
			raise KeyError("either passed in, or converted val became None, invalid as key")
		self.restricts_dict[key] = val

	def __delitem__(self, key):
		if isinstance(key, base):
			key = get_atom_key(restriction):
		if key != None and key in self.restricts_dict:
			del self.restricts_dict[key]
