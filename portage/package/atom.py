# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.restrictions import restriction 
from cpv import ver_cmp, CPV
from portage.restrictions.restrictionSet import AndRestrictionSet
from portage.util.lists import unique

class VersionMatch(restriction.base):
	__slots__ = tuple(["ver","rev", "vals"] + restriction.StrMatch.__slots__)
	"""any overriding of this class *must* maintain numerical order of self.vals, see intersect for reason why
	vals also must be a tuple"""

	def __init__(self, operator, ver, rev=None, negate=False, **kwd):
		kwd["negate"] = False
		super(self.__class__, self).__init__(**kwd)
		self.ver, self.rev = ver, rev
		l=[]
		if "<" in operator:	l.append(-1)
		if "=" in operator:	l.append(0)
		if ">" in operator:	l.append(1)
		self.vals = tuple(l)

	def intersect(self, other, allow_hand_off=True):
		if not isinstance(other, self.__class__):
			if allow_hand_off:
				return other.intersect(self, allow_hand_off=False)
			return None

		vc = ver_cmp(self.ver, self.rev, other.ver, other.ver)
		# ick.  28 possible valid combinations.
		if vc == 0:
			if 0 in self.vals and 0 in other.vals:
				for x in (-1, 1):
					if x in self.vals and x in other.vals:
						return self
				# need a '=' restrict.
				if self.vals == (0,):
					return self
				elif other.vals == (0,):
					return other
				return self.__class__("=", self.ver, rev=self.rev)

			# hokay, no > in each.  potentially disjoint
			for x, v in ((-1, "<"), (1,">")):
				if x in self.vals and x in other.vals:
					return self.__class__(v, self.ver, rev=self.rev)

			# <, > ; disjoint.
			return None

		if vc < 0:	vc = -1
		else:		vc = 1
		# this handles a node already containing the intersection
		for x in (-1, 1):
			if x in self.vals and x in other.vals:
				if vc == x:
					return self
				return other

		# remaining permutations are interesections
		for x in (-1, 1):
			needed = x * -1
			if (x in self.vals and needed in other.vals) or (x in other.vals and needed in self.vals):
				return AndRestrictionSet(self, other)

		if vc == -1 and 1 in self.vals and 0 in other.vals:
				return self.__class__("=", other.ver, rev=other.rev)
		elif vc == 1 and -1 in other.vals and 0 in self.vals:
			return self.__class__("=", self.ver, rev=self.rev)
		# disjoint.
		return None

	def match(self, pkginst):
		return (ver_cmp(self.ver, self.rev, pkginst.version, pkginst.revision) in self.vals) ^ self.negate


class atom(AndRestrictionSet):
	__slots__ = ("glob","atom","blocks","op", "negate_vers","cpv","use","slot") + tuple(AndRestrictionSet.__slots__)

	def __init__(self, atom, slot=None, use=[], negate_vers=False):
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

		self.negate_vers = negate_vers
		self.cpv = CPV(self.atom)
		self.use, self.slot = use, slot
		# force jitting of it.
		del self.restrictions


	def __getattr__(self, attr):
		if attr in ("category", "package", "version", "revision", "cpvstr", "fullver", "key"):
			g = getattr(self.cpv, attr)
#			self.__dict__[attr] = g
			return g
		elif attr == "restrictions":
			r = [restriction.PackageRestriction("package", restriction.StrExactMatch(self.package))]
			try:
				cat = self.category
				r.append(restriction.PackageRestriction("category", restriction.StrExactMatch(cat)))
			except AttributeError:
				pass
			if self.version:
				if self.glob:
					r.append(restriction.PackageRestriction("fullver", restriction.StrGlobMatch(self.fullver)))
				else:
					r.append(VersionMatch(self.op, self.version, self.revision, negate=self.negate_vers))
			if self.use or self.slot:
				raise Exception("yo.  I don't support use or slot yet, fix me pls kthnx")
#			self.__dict__[attr] = r
			setattr(self, attr, r)
			return r

		raise AttributeError(attr)

	def __str__(self):
		s=self.op+self.category+"/"+self.package
		if self.version:		s+="-"+self.fullver
		if self.glob:			s+="*"
		return s
