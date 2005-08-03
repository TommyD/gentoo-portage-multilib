# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import re, logging

class base(object):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	__slots__ = ["negate"]

	def __init__(self, negate=False):
		self.negate = negate

#	def __setattr__(self, name, value):
#		import traceback;traceback.print_stack()
#		object.__setattr__(self, name, value)
#		try:	getattr(self, name)
#			
#		except AttributeError:
#			object.__setattr__(self, name, value)
#		else:	raise AttributeError

	def match(self, *arg, **kwargs):
		raise NotImplementedError

	def intersect(self, other):
		return None

	def __len__(self):
		return 1

	total_len = __len__

class AlwaysBoolMatch(base):
	__slots__ = base.__slots__
	def match(self, *a, **kw):		return self.negate
	def __str__(self):	return "always '%s'" % self.negate

AlwaysFalse = AlwaysBoolMatch(False)
AlwaysTrue  = AlwaysBoolMatch(True)


class VersionRestriction(base):
	"""use this as base for version restrictions, gives a clue to what the restriction does"""
	pass


class StrMatch(base):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	__slots__ = ["flags"] + base.__slots__
	pass


class StrRegexMatch(StrMatch):
	#potentially redesign this to jit the compiled_re object
	__slots__ = tuple(["regex", "compiled_re"] + StrMatch.__slots__)

	def __init__(self, regex, CaseSensitive=True, **kwds):
		super(StrRegexMatch, self).__init__(**kwds)
		self.regex = regex
		flags = 0
		if not CaseSensitive:
			flags = re.I
		self.flags = flags
		self.compiled_re = re.compile(regex, flags)

	def match(self, value):
		return (self.compiled_re.match(str(value)) != None) ^ self.negate

	def intersect(self, other):
		if self.regex == other.regex and self.negate == other.negate and self.flags == other.flags:
			return self
		return None

	def __eq__(self, other):
		return self.regex == other.regex and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:	return "not like %s" % self.regex
		return "like %s" % self.regex


class StrExactMatch(StrMatch):
	__slots__ = tuple(["exact", "flags"] + StrMatch.__slots__)

	def __init__(self, exact, CaseSensitive=True, **kwds):
		super(StrExactMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.exact = str(exact).lower()
		else:
			self.flags = 0
			self.exact = str(exact)

	def match(self, value):
		if self.flags & re.I:	return (self.exact == str(value).lower()) ^ self.negate
		else:			return (self.exact == str(value)) ^ self.negate

	def intersect(self, other):
		s1, s2 = self.exact, other.exact
		if other.flags and not self.flags:
			s1 = s1.lower()
		elif self.flags and not other.flags:
			s2 = s2.lower()
		if s1 == s2 and self.negate == other.negate:
			if other.flags:
				return other
			return self
		return None

	def __eq__(self, other):
		return self.exact == other.exact and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:	return "!= "+self.exact
		return "== "+self.exact


class StrSubstringMatch(StrMatch):
	__slots__ = tuple(["substr"] + StrMatch.__slots__)

	def __init__(self, substr, CaseSensitive=True, **kwds):
		super(StrSubstringMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.substr = str(substr).lower()
		else:
			self.flags = 0
			self.substr = str(substr)

	def match(self, value):
		if self.flags & re.I:	value = str(value).lower()
		else:			value = str(value)
		return (value.find(self.substr) != -1) ^ self.negate

	def intersect(self, other):
		if self.negate == other.negate:
			if self.substr == other.substr and self.flags == other.flags:
				return self
		else:
			return None
		s1, s2 = self.substr, other.substr
		if other.flags and not self.flags:
			s1 = s1.lower()
		elif self.flags and not other.flags:
			s2 = s2.lower()
		if s1.find(s2) != -1:
			return self
		elif s2.find(s1) != -1:
			return other
		return None			

	def __eq__(self, other):
		return self.substr == other.substr and self.negate == other.negate and self.flags == other.flags


class StrGlobMatch(StrMatch):
	__slots__ = tuple(["glob"] + StrMatch.__slots__)
	def __init__(self, glob, CaseSensitive=True, **kwds):
		super(StrGlobMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.glob = str(glob).lower()
		else:
			self.flags = 0
			self.glob = str(glob)

	def match(self, value):
		value = str(value)
		if self.flags & re.I:	value = value.lower()
		return value.startswith(self.glob) ^ self.negate

	def intersect(self, other):
		if self.match(other.glob):
			if self.negate == other.negate:
				return other
		elif other.match(self.glob):
			if self.negate == other.negate:
				return self
		return None

	def __eq__(self, other):
		return self.glob == other.glob and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:	return "not "+self.glob+"*"
		return self.glob+"*"


class PackageRestriction(base):
	"""cpv data restriction.  Inherit for anything that's more then cpv mangling please"""

	__slots__ = tuple(["attr", "restriction"] + base.__slots__)

	def __init__(self, attr, restriction, **kwds):
		super(PackageRestriction, self).__init__(**kwds)
		self.attr = attr.split(".")
		if not isinstance(restriction, base):
			raise TypeError("restriction must be of a restriction type")
		self.restriction = restriction

	def match(self, packageinstance):
		try:
			o = packageinstance
			for x in self.attr:
				o = getattr(o, x)
			return self.restriction.match(o) ^ self.negate

		except AttributeError,ae:
			logging.debug("failed getting attribute %s from %s, exception %s" % \
				(".".join(self.attr), str(packageinstance), str(ae)))
			return self.negate

	def __getitem__(self, key):
		try:
			g = self.restriction[key]
		except TypeError:
			if key == 0:
				return self.restriction
			raise IndexError("index out of range")

	def total_len(self):
		return len(self.restriction) + 1

	def intersect(self, other):
		if self.negate != other.negate or self.attr != other.attr:
			return None
		if isinstance(self.restriction, other.restriction.__class__):
			s = self.restriction.intersect(other.restriction)
		elif isinstance(other.restriction, self.restriction.__class__):
			s = other.restriction.intersect(self.restriction)
		else:	return None
		if s == None:
			return None
		if s == self.restriction:		return self
		elif s == other.restriction:	return other

		# this can probably bite us in the ass self or other is a derivative, and the other isn't.
		return self.__class__(self.attr, s)

	def __eq__(self, other):
		return self.negate == self.negate and self.attr == other.attr and self.restriction == other.restriction

	def __str__(self):
		s='.'.join(self.attr)+" "
		if self.negate:	s += "not "
		return s + str(self.restriction)


class ContainmentMatch(base):
	"""used for an 'in' style operation, 'x86' in ['x86','~x86'] for example"""
	__slots__ = tuple(["vals"] + base.__slots__)
	
	def __init__(self, vals, **kwds):
		"""vals must support a contaiment test"""
		super(ContainmentMatch, self).__init__(**kwds)
		self.vals = vals

	def match(self, val):
		return (val in self.vals) ^ self.negate

	def __str__(self):
		if self.negate:	s="not in [%s]"
		else:			s="in [%s]"
		return s % ', '.join(map(str, self.vals))

