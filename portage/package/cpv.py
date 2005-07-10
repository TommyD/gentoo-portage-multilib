# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org)
# License: GPL2
# $Header$

import re


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
		
		if name == "key":
			if self.category:
				self.__dict__["key"] = self.category +"/"+ self.package
			else:
				self.__dict__["key"] = self.package
		
		if name in ("version","revision","fullver"):
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
#					self.__dict__["revision"] = 0 # harring changed this
					self.__dict__["revision"] = None
				
				for x in myparts:
					if not ver_regexp.match(x):
						raise ValueError(self.mycpv)
				
				self.__dict__["version"] = "-".join(myparts)
		if name == "fullver":
			if self.version == None:
				self.__dict__["fullver"] = None
			elif self.revision == None:
				self.__dict__["fullver"] = self.version
			else:
				self.__dict__["fullver"] = "%s-r%i" % (self.version,self.revision)

		if name in self.__dict__:
			return self.__dict__[name]
		raise AttributeError,name
	
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
			list1 = [int(match1.group(2))]
			list2 = [int(match2.group(2))]
			
			# this part would greatly benefit from a fixed-length version pattern
			if len(match1.group(3)) or len(match2.group(3)):
				vlist1 = match1.group(3)[1:].split(".")
				vlist2 = match2.group(3)[1:].split(".")
				for i in range(0, max(len(vlist1), len(vlist2))):
					if len(vlist1) <= i or len(vlist1[i]) == 0:
						list1.append(0)
						list2.append(int(vlist2[i]))
					elif len(vlist2) <= i or len(vlist2[i]) == 0:
						list1.append(int(vlist1[i]))
						list2.append(0)
					# Let's make life easy and use integers unless we're forced to use floats
					elif (vlist1[i][0] != "0" and vlist2[i][0] != "0"):
						list1.append(int(vlist1[i]))
						list2.append(int(vlist2[i]))
					# now we have to use floats so 1.02 compares correctly against 1.1
					else:
						list1.append(float("0."+vlist1[i]))
						list2.append(float("0."+vlist2[i]))
			
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
					try:			r1 = int(s1[1])
					except ValueError:	r1 = 0
					try:			r2 = int(s2[1])
					except ValueError:	r2 = 0
					return r1 - r2
		
		return cmp(self.revision, other.revision)


class Atom(object):
	
	"""
	Attributes
	
	bool blocks
	str operator
	bool glob_match
	CPV cpv
	
	Methods
	int __hash__()
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
	
	def __repr__(self):
		return self.atomstr
	
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
