# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import re

class Restriction(object):

	def match(self, *arg, **kwargs):
		raise NotImplementedError


class RestrictionClause(object):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	def __setattr__(self, name, value):
		try:	getattr(self, name)
			
		except AttributeError:
			object.__setattr__(self, name, value)
		else:	raise AttributeError

class VersionRestriction(RestrictionClause):
	pass


class StrMatch(RestrictionClause):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	pass


class StrRegexMatch(StrMatch):
	#potentially redesign this to jit the compiled_re object
	__slots__ = ("regex", "compiled_re", "flags")

	def __init__(self, regex, CaseSensitive=True):
		self.regex = regex
		flags = 0
		if not CaseSensitive:
			flags = re.I
		self.flags = flags
		self.compiled_re = re.compile(regex, flags)


	def match(self, value):
		return self.compiled_re.match(str(value)) != None


class StrExactMatch(StrMatch):
	__slots__ = ("exact", "flags")

	def __init__(self, exact, CaseSensitive=True):
		if not CaseSensitive:
			self.flags = re.I
			self.exact = str(exact).lower()
		else:
			self.flags = 0
			self.exact = str(exact)


	def match(self, value):
		if self.flags & re.I:	return self.exact == str(value).lower()
		else:			return self.exact == str(value)


class StrSubstringMatch(StrMatch):
	__slots__ = ("substr")

	def __init__(self, substr, CaseSensitive=True):
		if not CaseSensitive:
			self.flags = re.I
			substr = str(substr).lower()
		else:
			self.flags = 0
			substr = str(substr)
		self.substr = substr;


	def match(self, value):
		if self.flags & re.I:	value = str(value).lower()
		else:			value = str(value)
		return value.find(self.substr) != -1


class PackageDataRestriction(Restriction):
	__slots__ = ("metadata_key", "strmatch")

	def __init__(self, metadata_key, StrMatchInstance):
		self.metadata_key = metadata_key
		self.strmatch = StrMatchInstance


	def pmatch(self, packageinstance):
		try:	return self.match(getattr(packageinstance.data, self.metadatakey))

		except AttributeError:
			return False


	def match(self, value):
		return self.strmatch.match(value)


	def __setattr__(self, name, value):
		try:	getattr(self, name)
			
		except AttributeError:
			object.__setattr__(self, name, value)

		else:	raise AttributeError


#cough. yeah.  somebody fill thus out please :)
class ConfigRestriction(Restriction):
	pass
