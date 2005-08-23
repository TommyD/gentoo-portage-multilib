# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.restrictions import restriction 
from cpv import ver_cmp, CPV
from portage.restrictions.restrictionSet import AndRestrictionSet

class VersionMatch(restriction.base):
	__slots__ = tuple(["ver","rev", "vals"] + restriction.StrMatch.__slots__)
	def __init__(self, operator, ver, rev=None, **kwd):
		super(self.__class__, self).__init__(**kwd)
		self.ver, self.rev = ver, rev
		l=[]
		if ">" in operator:	l.append(1)
		if "<" in operator:	l.append(-1)
		if "=" in operator:	l.append(0)
		self.vals = tuple(l)

	def match(self, pkginst):
		return (ver_cmp(self.ver, self.rev, pkginst.version, pkginst.revision) in self.vals) ^ self.negate


class atom(AndRestrictionSet):
	def __init__(self, atom, slot=None, use=[]):

		super(self.__class__, self).__init__()

		pos=0
		while atom[pos] in ("<",">","=","~","!"):
			pos+=1
		if atom.startswith("!"):
			self.blocks  = True
			self.op = atom[1:pos]
		else:
			self.blocks = False
			self.op = atom[:pos]
		if atom.endswith("*"):
			self.glob = True
			self.atom = atom[pos:-1]
		else:
			self.glob = False
			self.atom = atom[pos:]

		self.cpv = CPV(self.atom)
		self.use, self.slot = use, slot
		# force jitting of it.
		del self.restrictions

	def __getattr__(self, attr):
		if attr in ("category", "package", "version", "revision", "cpvstr", "fullver", "key"):
			g = getattr(self.cpv, attr)
			self.__dict__[attr] = g
			return g
			
		elif attr == "restrictions":
			r = []
			try:
				cat = self.category
				r.append(restriction.PackageRestriction("category", restriction.StrExactMatch(cat)))
			except AttributeError:
				pass
			r.append(restriction.PackageRestriction("package", restriction.StrExactMatch(self.package)))
			if self.version:
				if self.glob:
					r.append(restriction.PackageRestriction("fullver", restriction.StrGlobMatch(self.fullver)))
				else:
					r.append(VersionMatch(self.op, self.version, self.revision))
			if self.use or self.slot:
				raise Exception("yo.  I don't support use or slot yet, fix me pls kthnx")
			self.__dict__["restrictions"] = r
			return r

		raise AttributeError(attr)
