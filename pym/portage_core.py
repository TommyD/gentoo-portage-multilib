# Copyright 1999-200 Gentoo Technologies, Inc. 
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author: Daniel Robbins <drobbins@gentoo.org>
# $Header$

import string

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}

class eid:
	"An eid is an ebuild/package id, consisting of a category, package, version and revision"
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
		self.category=None
		self.package=None
		self.version=None
		self.revision=None
		self.valid=0
		self.repr=None
	
	def validateversion(self):	
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
		print
		print "DEBUG EID"
		for x in ["error","category","package","version","revision","valid","repr"]:
			try:
				exec("print x,self."+x)
			except:
				print x,"(undefined)"
	
	def __repr__(self):
		"return string representation of this eid"
		
	def __cmp__(self,other):
		"comparison"

	def isvalid(self):
		"is this a valid eid (proper category, package, version string, rev)"
	
	def similar(self,other):
		"are we talking about the same category and package (but possibly different versions/revs)?"
		if self.valid and other.valid:
			if (self.category==other.category) and (self.package==other.package):
				return 1
		return 0
	
