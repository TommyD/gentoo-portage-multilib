# Copyright 1999-200 Gentoo Technologies, Inc. 
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author: Daniel Robbins <drobbins@gentoo.org>
# $Header$

import string

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}

""" 
An eid, or ebuild id, is an object that stores category, package, version and
revision information.  eids can be valid or invalid.  If invalid, the eid will
set an internal variable called "error" to a human-readable error message
describing what is wrong with the eid.  Note that eids aren't tied to a
particular ebuild file or package database entry; instead they're used by
Portage to talk about particular category/package-version-revs in the abstract.
Because all the information about a particular ebuild/db entry/.tbz2 package is
stored in a single object, a lot of redundancy is eliminated.  Also, the eid
methods make good use of caching in order to optimize performance for version
comparisons, etc.

Example use:

>>> from portage_core import *
>>> a=eid("sys-apps/foo-1.0")
>>> a.valid
1
>>> a.version
'1.0'
>>> a.revision
'0'
>>> a.category
'sys-apps'
>>> b=eid("sys-apps/foo-1.1")
>>> a>b
0
>>> a<b
1
>>> c=eid("sys-bad/packagename-1.0p3")
>>> c.valid
0
>>> c.error
'sys-bad/packagename-1.0p3: Invalid ending version part'

(NOTE: the version string should be "1.0_p3", not "1.0p3".)

Data Definitions:

eid.repr: A human-readable represenation of the eid data, i.e. "sys-apps/foo-1.0-r1"
eid.category: category, i.e. "sys-apps"
eid.package: package, i.e. "foo"
eid.version: version, i.e. "1.0"
eid.revision: revision, i.e. "1"
eid.valid: boolean specifying whether this is a valid eid, i.e. 1
eid.error: a human-readable error message relating to a non-true eid.valid, i.e. "Invalid version part"
eid.cmp: cached eid comparison data

TEST ROUTINE: 

for x in ["1.0_rc6","4.0_pre12", "4.0","9.12.13","0.9.10","1.0.9-r1","3.0","3.0_alpha1","3.0_beta","3.0_rc1","3.0_pre1","3.0_p3","3.0a"]:
	a=eid("sys-apps/foo-"+x)
	b=eid("sys-apps/foo-3.0")
	a.debug()
	if not a.valid:
		print x,"(INVALID)"
		continue
	if a>b:
		print x,">","3.0"
	elif a<b:
		print x,"<","3.0"
	else:
		print x,"=","3.0"
"""

class eid:
	"""An eid is an ebuild/package id, consisting of a category, package, version and revision.
	If validate is set to 1 (the default), the init code will validate the input.  If set to zero,
	the input is assumed correct, but an exception will be raised if it is not."""
	
	def __init__(self,mystring=None,validate=1):
		"initialization; optional assignment; optional validation of input (otherwise assumed correct)"
		
		#initialize this here so it's available for self.invalidate, which uses self.repr
		self.repr=mystring
		
		if not mystring:
			self.invalidate()
			return
		else:
			if not validate:
				# no input validation performed; assumed correct and bad input will cause an exception to be raised
				if mystring:
					mysplit=string.split(mystring,"/")
					self.category=mysplit[0]
					self.cmp=None
					myparts=string.split(mysplit[1],'-')
					if myparts[-1][0]=="r":
						self.revision=myparts[-1][1:]
						self.version=myparts[-2]
						self.package=string.join(myparts[0:-2],"-")
					else:
						self.revision="0"
						self.version=myparts[-1]
						self.package=string.join(myparts[0:-1],"-")
					self.error=None
					self.valid=1
					self.repr=mystring
			else:
				# validation performed; everything will be scrubbed.  On invalid input, self.valid will be set to 0.
				
				#initial assigns; assume we'll get through this OK (optimize for valid input)
				self.error=None
				self.valid=1
				
				mysplit=string.split(mystring,"/")
				if len(mysplit)!=2:
					self.invalidate("More than one \"/\"")
					return
				self.category=mysplit[0]
				self.cmp=None
				myparts=string.split(mysplit[1],"-")
				if len(myparts)<2:
					self.invalidate("Missing version or name part")
					return
				for x in myparts:
					if len(x)==0:
						self.invalidate("Empty \"-\" part")
						return
				#at this point, we know that we have at least 2 non-empty parts
				if myparts[-1][0]=="r":
					#potential rev
					if len(myparts)==2:
						self.invalidate("Invalid version")
					#we now know we have at least 3 parts
					if len(myparts[-1])<=1:
						self.invalidate("Missing revision number")
						return
					try:
						string.atoi(myparts[-1][1:])
					except:
						self.invalidate("Invalid revision number")
						return
					self.revision=myparts[-1][1:]
					self.version=myparts[-2]
					if not self.validateversion():
						return
					self.package=string.join(myparts[0:-2],"-")
					return	
				else:
					self.revision="0"
					self.version=myparts[-1]
					if not self.validateversion():
						return
					self.package=string.join(myparts[0:-1],"-")
					return
	
	def invalidate(self,error=None):
		"make this an invalid eid"
		if error:
			if self.repr:
				#record string representation for later reference
				self.error=self.repr+": "+error
			else:
				self.error=error
		else:
			self.error=None
		self.cmp=None
		self.category=None
		self.package=None
		self.version=None
		self.revision=None
		self.valid=0
		self.repr=None
	
	def validateversion(self):	
		"internal support routine that validates self.version"
		myval=string.split(self.version,'.')
		if len(myval)==0:
			self.invalidate("Empty version string")
			return
		for x in myval[:-1]:
			if not len(x):
				self.invalidate("Two decimal points in a row")
				return 0
			try:
				foo=string.atoi(x)
			except:
				self.invalidate("\""+x+"\" is not a valid version component")
				return 0
		if not len(myval[-1]):
				self.invalidate("Two decimal points in a row")
				return 0
		try:
			foo=string.atoi(myval[-1])
			return 1
		except:
			pass
		#ok, our last component is not a plain number or blank, let's continue
		if myval[-1][-1] in string.lowercase:
			try:
				foo=string.atoi(myval[-1][:-1])
				return 1
				# 1a, 2.0b, etc.
			except:
				pass
		#ok, maybe we have a 1_alpha or 1_beta2; let's see
		#ep="endpart"
		ep=string.split(myval[-1],"_")
		if len(ep)!=2:
			self.invalidate("Invalid ending version part")
			return 0
		try:
			foo=string.atoi(ep[0])
		except:
			#this needs to be numeric, i.e. the "1" in "1_alpha"
			self.invalidate("characters before \"_\" must be numeric")
			return 0
		for mye in endversion.keys():
			if ep[1][0:len(mye)]==mye:
				if len(mye)==len(ep[1]):
					#no trailing numeric; ok
					return 1
				else:
					try:
						foo=string.atoi(ep[1][len(mye):])
						return 1
					except:
						#if no endversions work, *then* we return 0
						pass	
		self.invalidate("Name error (miscellaneous)")
		return 0
	
	def debug(self):
		"internal debug function"
		print
		print "DEBUG EID"
		for x in ["error","category","package","version","revision","valid","repr","cmp"]:
			try:
				exec("print x,self."+x)
			except:
				print x,"(undefined)"
	
	def __cmp__(self,other):
		"comparison operator code"
		if self.cmp==None:
			self.cmp=self.gencmp()
		if other.cmp==None:
			other.cmp=other.gencmp()
		mycmp=self.cmp[:]
		othercmp=other.cmp[:]
		while(len(mycmp)<len(othercmp)):
			mycmp.append([0,0,0])
		while(len(mycmp)>len(othercmp)):
			othercmp.append([0,0,0])
		for x in range(0,len(mycmp)-1):
			for y in range(0,3):
				myret=mycmp[x][y]-othercmp[x][y]
				if myret!=0:
					return myret
		return 0
		
	def gencmp(self):
		"internal function used to generate comparison lists"
		cmplist=[]
		splitversion=string.split(self.version,".")
		for x in splitversion[:-1]:
			cmplist.append([string.atoi(x),0,0])
		a=string.split(splitversion[-1],"_")
		match=0
		p1=0
		p2=0
		if len(a)==2:
			pos=len(a[1])
			number=string.atoi(a[0])
			if a[1][-1] in string.digits:
				pos=0
				while a[1][pos-1] in string.digits:
					pos=pos-1
			for x in endversion.keys():
				if a[1][0:pos]==x:
					match=1
					#p1 stores the numerical weight of _alpha, _beta, etc.
					p1=endversion[x]
					try:
						p2=string.atoi(a[1][len(x):])
					except:
						p2=0
					cmplist.append([number,p1,p2])
					cmplist.append([string.atoi(self.revision),0,0])
					return cmplist
		if not match:	
			#normal number or number with letter at end
			if self.version[-1] not in string.digits:
				#letter at end
				p1=ord(self.version[-1])
				number=string.atoi(splitversion[-1][0:-1])
			else:
				number=string.atoi(splitversion[-1])		
		cmplist.append([number,p1,p2])
		cmplist.append([string.atoi(self.revision),0,0])
		return cmplist

	def similar(self,other):
		"are we talking about the same category and package (but possibly different versions/revs)?"
		if self.valid and other.valid:
			if (self.category==other.category) and (self.package==other.package):
				return 1
		return 0


