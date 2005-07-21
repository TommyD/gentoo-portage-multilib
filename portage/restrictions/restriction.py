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

	def __setattr__(self, name, value):
		try:	getattr(self, name)
			
		except AttributeError:
			object.__setattr__(self, name, value)
		else:	raise AttributeError

	def match(self, *arg, **kwargs):
		raise NotImplementedError

class AlwaysTrue(base):
	__slots__ = ()
	def match(self, *a, **kw):
		return True

class AlwaysFalse(base):
	__slots__ = ()
	def match(self, *a, **kw):
		return False

class VersionRestriction(base):
	"""use this as base for version restrictions, gives a clue to what the restriction does"""
	pass


class StrMatch(base):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	__slots__ = base.__slots__
	pass


class StrRegexMatch(StrMatch):
	#potentially redesign this to jit the compiled_re object
	__slots__ = tuple(["regex", "compiled_re", "flags"] + StrMatch.__slots__)

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


class StrSubstringMatch(StrMatch):
	__slots__ = tuple(["substr"] + StrMatch.__slots__)

	def __init__(self, substr, CaseSensitive=True, **kwds):
		super(StrSubString, self).__init__(**kwds)
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


class StrGlobMatch(StrMatch):
	__slots__ = tuple(["glob"] + StrMatch.__slots__)
	def __init__(self, glob, CaseSensitive=True, **kwds):
		super(StrGlobMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.glob = str(glob).lower()
		else:
			self.glags = 0
			self.glob = str(glob)
	def match(self, value):
		value = str(value)
		if self.flags & re.I:	value = value.lower()
		return value.startswith(self.glob) ^ self.negate

class PackageRestriction(base):
	"""cpv data restriction.  Inherit for anything that's more then cpv mangling please"""

	__slots__ = tuple(["attr", "strmatch"] + base.__slots__)

	def __init__(self, attr, StrMatchInstance, **kwds):
		super(PackageRestriction, self).__init__(**kwds)
		self.attr = attr.split(".")
		self.strmatch = StrMatchInstance

	def match(self, packageinstance):
		try:
			o = packageinstance
			for x in self.attr:
				o = getattr(o, x)
			return self.strmatch.match(o) ^ self.negate

		except AttributeError,ae:
			logging.debug("failed getting attribute %s from %s, exception %s" % \
				(".".join(self.attr), str(packageinstance), str(ae)))
			return self.negate
