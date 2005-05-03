import re,string,copy


pkg_regexp = re.compile("^[a-zA-Z0-9]([-_+a-zA-Z0-9]*[+a-zA-Z0-9])?$")
ver_regexp = re.compile("^(cvs\\.)?(\\d+)((\\.\\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\\d*)*)(-r(\\d+))?$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 0, "alpha": -4, "beta": -3, "rc": -1}

class CPV(object):

	"""
	Attributes

	str category
	str package
	str key (cat/pkg)
	str version
	int revision

	Methods

	int __hash__()
	str __repr__()
	int __cmp__(CPV)
	"""

	def __init__(self, cpvstr):
		if not isinstance(cpvstr, str):
			raise ValueError(cpvstr)
		self.__dict__["cpvstr"] = cpvstr
		self.__dict__["hash"] = hash(cpvstr)

	def __hash__(self):
		return self.hash

	def __repr__(self):
		return self.cpvstr

	def __setattr__(self, name, value):
		raise Exception()

	def __getattr__(self, name):

		if name == "category":
			myparts = self.cpvstr.split("/")
			if len(myparts) >= 2:
				if not pkg_regexp.match(myparts[0]):
					raise ValueError(self.cpvstr)
				self.__dict__["category"] = myparts[0]
			else:
				self.__dict__["category"] = None
			return self.category

		if name == "package":
			if self.category:
				myparts = self.cpvstr[len(self.category)+1:].split("-")
			else:
				myparts = self.cpvstr.split("-")
			if ver_regexp.match(myparts[0]):
				raise ValueError(self.cpvstr)
			pos = 1
			while pos < len(myparts) and not ver_regexp.match(myparts[pos]):
				pos += 1
			pkgname = "-".join(myparts[:pos])
			if not pkg_regexp.match(pkgname):
				raise ValueError(self.cpvstr)
			self.__dict__["package"] = pkgname
			return self.package

		if name == "key":
			if self.category:
				self.__dict__["key"] = self.category +"/"+ self.package
			else:
				self.__dict__["key"] = self.package
			return self.key

		if name == "version" or name == "revision":
			if self.category:
				myparts = self.cpvstr[len(self.category+self.package)+2:].split("-")
			else:
				myparts = self.cpvstr[len(self.package)+1:].split("-")

			if not myparts[0]:
				self.__dict__["version"] = None
				self.__dict__["revision"] = None

			else:
				if myparts[-1][0] == "r" and myparts[-1][1:].isdigit():
					self.__dict__["revision"] = int(myparts[-1][1:])
					myparts = myparts[:-1]
				else:
					self.__dict__["revision"] = 0

				for x in myparts:
					if not ver_regexp.match(x):
						raise ValueError(self.mycpv)

				self.__dict__["version"] = "-".join(myparts)

			if name == "version":
				return self.version
			else:
				return self.revision

		raise AttributeError(name)

	def __cmp__(self, other):

		if self.cpvstr == other.cpvstr:
			return 0

		if self.category and other.category and self.category != other.category:
			return cmp(self.category, other.category)

		if self.package and other.package and self.package != other.package:
			return cmp(self.package, other.package)

		if self.version != other.version:

			if self.version is None:
				raise ValueError(self)

			if other.version is None:
				raise ValueError(other)

			match1 = ver_regexp.match(self.version)
			match2 = ver_regexp.match(other.version)

			# shortcut for cvs ebuilds (new style)
			if match1.group(1) and not match2.group(1):
				return 1
			elif match2.group(1) and not match1.group(1):
				return -1

			# building lists of the version parts before the suffix
			# first part is simple
			list1 = [string.atoi(match1.group(2))]
			list2 = [string.atoi(match2.group(2))]

			# this part would greatly benefit from a fixed-length version pattern
			if len(match1.group(3)) or len(match2.group(3)):
				vlist1 = match1.group(3)[1:].split(".")
				vlist2 = match2.group(3)[1:].split(".")
				for i in range(0, max(len(vlist1), len(vlist2))):
					if len(vlist1) <= i or len(vlist1[i]) == 0:
						list1.append(0)
						list2.append(string.atoi(vlist2[i]))
					elif len(vlist2) <= i or len(vlist2[i]) == 0:
						list1.append(string.atoi(vlist1[i]))
						list2.append(0)
					# Let's make life easy and use integers unless we're forced to use floats
					elif (vlist1[i][0] != "0" and vlist2[i][0] != "0"):
						list1.append(string.atoi(vlist1[i]))
						list2.append(string.atoi(vlist2[i]))
					# now we have to use floats so 1.02 compares correctly against 1.1
					else:
						list1.append(string.atof("0."+vlist1[i]))
						list2.append(string.atof("0."+vlist2[i]))

			# and now the final letter
			if len(match1.group(5)):
				list1.append(ord(match1.group(5)))
			if len(match2.group(5)):
				list2.append(ord(match2.group(5)))

			for i in range(0, max(len(list1), len(list2))):
				if len(list1) <= i:
					return -1
				elif len(list2) <= i:
					return 1
				elif list1[i] != list2[i]:
					return list1[i] - list2[i]

			# main version is equal, so now compare the _suffix part
			list1 = match1.group(6).split("_")[1:]
			list2 = match2.group(6).split("_")[1:]

			for i in range(0, max(len(list1), len(list2))):
				if len(list1) <= i:
					s1 = ("p","0")
				else:
					s1 = suffix_regexp.match(list1[i]).groups()
				if len(list2) <= i:
					s2 = ("p","0")
				else:
					s2 = suffix_regexp.match(list2[i]).groups()
				if s1[0] != s2[0]:
					return suffix_value[s1[0]] - suffix_value[s2[0]]
				if s1[1] != s2[1]:
					# it's possible that the s(1|2)[1] == ''
					# in such a case, fudge it.
					try:			r1 = string.atoi(s1[1])
					except ValueError:	r1 = 0
					try:			r2 = string.atoi(s2[1])
					except ValueError:	r2 = 0
					return r1 - r2

		return cmp(self.revision, other.revision)


class Atom(object):

	"""
	Attributes

	bool blocks
	str  operator
	bool glob_match
	CPV  cpv

	Methods
	int __hash__()
	str __str__()
	str __repr__()
	bool match(CPV)
	"""

	def __init__(self, atomstr):
		if not isinstance(atomstr, str):
			raise ValueError(atomstr)
		self.__dict__["atomstr"] = atomstr
		self.__dict__["hash"] = hash(atomstr)

	def __hash__(self):
		return self.hash

	def __str__(self):
		return self.atomstr

	def __repr__(self):
		return "Atom('" + self.atomstr + "')"

	def __setattr__(self, name, value):
		raise Exception()

	def __getattr__(self, name):

		if not self.__dict__.has_key("category"):

			myatom = self.atomstr

			if myatom[0] == "!":
				self.__dict__["blocks"] = True
				myatom = myatom[1:]
			else:
				self.__dict__["blocks"] = False

			if myatom[0:2] in ["<=", ">="]:
				self.__dict__["operator"] = myatom[0:2]
				myatom = myatom[2:]
			elif myatom[0] in ["<", ">", "=", "~"]:
				self.__dict__["operator"] = myatom[0]
				myatom = myatom[1:]
			else:
				self.__dict__["operator"] = None

			if myatom[-1] == "*":
				self.__dict__["glob_match"] = True
				myatom = myatom[:-1]
			else:
				self.__dict__["glob_match"] = False

			self.__dict__["cpv"] = CPV(myatom)

			if self.operator != "=" and self.glob_match:
				raise ValueError(self.atomstr)

			if self.operator and not self.cpv.version:
				raise ValueError(self.atomstr)

			if not self.operator and self.cpv.version:
				raise ValueError(self.atomstr)

			if self.operator == "~" and self.cpv.revision:
				raise ValueError(self.atomstr)

			if self.glob_match and self.cpv.revision:
				raise ValueError(self.atomstr)

		if not self.__dict__.has_key(name):
			raise AttributeError(name)

		return self.__dict__[name]

	def match(self, cpv):

		if self.cpv.category and cpv.category and self.cpv.category != cpv.category:
			return False

		if self.cpv.package and cpv.package and self.cpv.package != cpv.package:
			return False

		if not self.operator:
			return True

		if self.operator == "=":
			if self.glob_match and cpv.version.startswith(self.cpv.version):
				return True
			if self.cpv.version != cpv.version:
				return False
			if self.cpv.revision != cpv.revision:
				return False

		if self.operator == "~" and self.cpv.version == cpv.version:
			return True

		diff = cmp(self.cpv, cpv)

		if not diff:
			if self.operator == "<=" or self.operator == ">=":
				return True
			else:
				return False

		if diff > 0:
			if self.operator[0] == "<":
				return True
			else:
				return False

		#if diff < 0:
		if self.operator[0] == ">":
			return True
		#else:
		return False

	def intersects(self, atom):
		if self == other:
			return True
		if self.key != atom.key:
			return False
		if self.blocks != other.blocks:
			return False
		if not self.operator or not other.operator:
			return True
		if self.cpv == other.cpv:
			if self.operator == other.operator:
				return True
			if self.operator == "<":
				return (other.operator[0] == "<")
			if self.operator == ">":
				return (other.operator[0] == ">" or other.operator == "~")
			if self.operator == "=":
				return (other.operator != "<" and other.operator != ">")
			if self.operator == "~" or self.operator == ">=":
				return (other.operator != "<")
			return (other.operator != ">")
		elif self.cpv.version == other.cpv.version:
			if self.cpv > other.cpv:
				if self.operator == "=" and other.operator == "~":
					return True
			elif self.operator == "~" and other.operator == "=":
					return True
		if self.operator in ["=","~"] and other.operator in ["=","~"]:
			return False
		if self.cpv > other.cpv:
			if self.operator in ["<","<="]:
				return True
			if other.operator in [">",">="]:
				return True
			return False
		if self.operator in [">",">="]:
			return True
		if other.operator in ["<","<="]:
			return True
		return False

	def encapsulates(self, atom):
		if not self.intersects(atom):
			return False

		if self.operator and not other.operator:
			return False
		if not self.operator:
			return True

		if self.cpv == other.cpv:
			if self.operator == other.operator:
				return True
			if other.operator == "=":
				return True
			if self.operator == "<=" and other.operator == "<":
				return True
			if self.operator == ">=" and other.operator == ">":
				return True
			return False
		elif self.cpv.version == other.cpv.version:
			if self.cpv < other.cpv and self.operator == "~":
				return true
		if self.cpv > other.cpv:
			if self.operator in ["<","<="] and other.operator not in [">",">="]:
				return True
			return False
		if self.operator in [">",">="] and other.operator not in ["<","<="]:
			return True
		return False


class DependSpec:

	"""
	Attributes

	list elements
	bool preferential
	str  condition

	Methods

	int __str__()
	str __repr__()
	"""

	def __init__(self, dependstr="", element_class=str):

		if not isinstance(dependstr, str):
			raise ValueError(dependstr)
		if isinstance(element_class, DependSpec):
			raise ValueEro

		dependstr = " ".join(dependstr.split())
		self.__dict__["dependstr"] = dependstr
		self.__dict__["condition"] = None
		self.__dict__["preferential"] = False
		self.__dict__["elements"] = []

		depstrlen = len(dependstr)
		parseidx = 0
		condition = None
		element = None

		while parseidx != depstrlen:
			c = dependstr[parseidx]

			if c == " ":
				parseidx += 1
				continue

			if c == ")":
				raise ValueError(self.dependstr)

			if c == "|" and not element and dependstr[parseidx:].startswith("||"):
				parseidx += 2
				(subdependstr, parseidx) = self._extract_dependstr(dependstr, parseidx)
				element = DependSpec(subdependstr, element_class)
				if len(element.elements) > 1:
					element.__dict__["preferential"] = True
				if condition:
					element.__dict__["condition"] = condition
					condition = None
				self.elements.append(element)
				element = None
				continue

			if c == "(":
				(subdependstr, parseidx) = self._extract_dependstr(dependstr, parseidx)
				element = DependSpec(subdependstr, element_class)
				if condition:
					element.__dict__["condition"] = condition
					condition = None
				self.elements.append(element)
				element = None
				continue

			if dependstr.find(" ", parseidx) != -1:
				element = dependstr[parseidx:dependstr.find(" ", parseidx)]
			else:
				element = dependstr[parseidx:]
			parseidx += len(element)

			if element[-1] == "?":
				if condition:
					raise ValueError(self.dependstr)
				condition = element[:-1]
				if not condition:
					raise ValueError(self.dependstr)
				element = None
			elif condition:
				if not element:
					raise ValueError(self.dependstr)
				if not isinstance(element, DependSpec):
					element = DependSpec(element, element_class)
				element.__dict__["condition"] = condition
				condition = None
				self.elements.append(element)
				element = None
			else:
				element = element_class(element)
				self.elements.append(element)
				element = None

		self.__dict__["dependstr"] = None

	def _extract_dependstr(self, dependstr, parseidx):
		depstrlen = len(dependstr)

		while dependstr[parseidx] != "(":
			parseidx += 1
			if parseidx == depstrlen or dependstr[parseidx] not in [" ", "("]:
				raise ValueError(self.dependstr)

		parseidx += 1
		startpos = parseidx
		bracketcount = 1

		while bracketcount:
			if parseidx == depstrlen:
				raise ValueError(self.dependstr)

			nextopen = dependstr.find("(", parseidx)
			nextclose = dependstr.find(")", parseidx)
			if nextopen == -1 and nextclose == -1:
				raise ValueError(self.dependstr)

			if nextclose == -1 or nextopen != -1 and nextopen < nextclose:
				parseidx = nextopen + 1
				bracketcount += 1
			else:
				parseidx = nextclose + 1
				bracketcount -= 1

		subdependstr = dependstr[startpos:parseidx-1]
		return (subdependstr, parseidx)

	def __setattr__(self, name, value):
		raise Exception()

	def __repr__(self):
		return "DependSpec('" + str(self) + "')"

	def __eq__(self, other):
		return str(self) == str(other)

	def __str__(self):
		if self.dependstr:
			return self.dependstr

		dependstr = ""
		if self.condition:
			dependstr = self.condition + "? ( "
		if self.preferential:
			dependstr += "|| ( "
		for element in self.elements:
			if isinstance(element, DependSpec) and len(element.elements) > 1 and not element.preferential and not element.condition:
				dependstr += "( " + str(element) + " )"
			else:
				dependstr += str(element)
			dependstr += " "
		if self.elements:
			dependstr = dependstr[:-1]
		if self.preferential:
			dependstr += " )"
		if self.condition:
			dependstr += " )"
		self.__dict__["dependstr"] == dependstr
		return dependstr

	def compact(self):
		for element in self.elements:
			if isinstance(element, DependSpec):
				element.compact()

		changed = True
		while changed:
			changed = False
			for x in range(len(self.elements)-1, -1, -1):
				if isinstance(self.elements[x], DependSpec) and not len(self.elements[x].elements):
					del self.elements[x]
					changed = True
			if not self.condition and not self.preferential:
				for x in range(len(self.elements)-1, -1, -1):
					if isinstance(self.elements[x], DependSpec):
						if not self.elements[x].condition and not self.elements[x].preferential:
							self.elements.extend(self.elements[x].elements)
							del self.elements[x]
							changed = True

		elements = self.elements[:]
		del self.elements[:]
		for element in elements:
			if element not in self.elements:
				self.elements.append(element)

		if not self.condition and not self.preferential and len(self.elements) == 1 and isinstance(self.elements[0], DependSpec):
			element = self.elements[0]
			self.__dict__["condition"] = element.condition
			self.__dict__["preferential"] = element.preferential
			self.__dict__["elements"] = element.elements

	def __copy__(self):
		dependspec = DependSpec()
		dependspec.__dict__["condition"] = self.condition
		dependspec.__dict__["preferential"] = self.preferential
		for element in self.elements:
			dependspec.elements.append(copy.copy(element))
		return dependspec

	def resolve_conditions(self, truths):
		if self.condition and self.condition not in truths:
			del self.elements[:]
			return

		dependspec.__dict__["preferential"] = self.preferential
		for element in self.elements:
			if isinstance(element, DependSpec):
				element.resolve_conditions(truths)

		self.compact()
