# Copyright 1999-200 Gentoo Technologies, Inc. 
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author: Daniel Robbins <drobbins@gentoo.org>
# $Header$

import string
import re
import os

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}

#The "categories" variable will eventually be moved out of portage_core2 and will
#most likely be read from a file.

categories=("app-i18n", "app-admin", "app-arch", "app-cdr", "app-crypt",
"app-doc", "app-editors", "app-emulation", "app-games", "app-misc",
"app-office", "app-shells", "app-text", "dev-db", "dev-java", "dev-lang",
"dev-libs", "dev-lisp", "dev-perl", "dev-python", "dev-ruby", "dev-util",
"gnome-base", "gnome-extra", "kde-apps", "kde-i18n", "kde-base", "kde-libs",
"media-gfx", "media-libs", "media-sound", "media-video", "net-analyzer",
"net-apache", "net-dialup", "net-fs", "net-ftp", "net-im", "net-irc",
"net-libs", "net-mail", "net-misc", "net-news", "net-nds", "net-print",
"net-www", "packages", "sys-apps", "sys-devel", "sys-kernel", "sys-libs",
"x11-base", "x11-libs", "x11-misc", "x11-terms", "x11-wm", "virtual",
"dev-tcltk")

class selector:

	"""The selector class is a generic parent class.  Its child classes are
	used to specify a certain subset of ebuilds/packages/db entries."""

	#below, list all "public" attributes for this class 
	attributes=["repr","error","valid"]
	
	def __init__(self):
		pass

	def invalidate(self,error=None):
		"make this an invalid constraint"
		if error:
			if self.__dict__.has_key("repr"):
				#record string representation for later reference
				self.__dict__["error"]=self.repr+": "+error
			else:
				self.__dict__["error"]=error
		else:
			self.__dict__["error"]=None
		self.__dict__["repr"]=None
		for x in self.__class__.attributes:
			self.__dict__[x]=None
		self.__dict__["valid"]=0

	def __nonzero__(self):
		"This allows us to do an 'if myeid:'"
		return self.valid

	def __repr__(self):
		return self.repr

	def __str__(self):
		return self.repr

class key(selector):

	"""A 'key' (name may change in the future) is used to specify a category
	(in "not specific" mode) or a category and package (in "specific" mode).
	It does not specify any version information."""

	#used by selector.invalidate()
	attributes=["category","package","specific"]

	def __init__(self,myfoo):
		#copy object
		if type(myfoo)==type(self):
			for x in selector.attributes+self.__class__.attributes:
				self.__dict__[x]=myfoo.__dict__[x]
				return
		#new object
		if not myfoo:
			self.invalidate()
		self.__dict__["repr"]=myfoo
		mysplit=string.split(myfoo,"/")
		if len(mysplit)>2:
			self.invalidate()
			return
		self.__dict__["valid"]=1
		if len(mysplit)==2:
			self.__dict__["category"],self.__dict__["package"]=mysplit
			self.__dict__["specific"]=1
		else:
			self.__dict__["category"]=myfoo
			self.__dict__["package"]=None
			self.__dict__["specific"]=0
			
	def __setattr__(self,name,value):
		if name not in key.attributes:
			#ignore
			return
		self.__dict__[name]=value
		if self.__dict__["package"]:
			self.__dict__["specific"]=1
			self.__dict__["repr"]=self.category+"/"+self.package
		else:
			self.__dict__["repr"]=self.category
			self.__dict__["specific"]=0

class constraint(selector):

	"""generic parent class for eid and range classes.  eids and ranges both
	store version information, so we move a lot of the version functionality to
	this parent class to eliminate redundant code and ease maintainance."""
	
	attributes=["version","revision"]

	def __init__(self,myfoo):
		if type(myfoo)==type(self):
			#copy supplied object
			for x in selector.attributes+self.attributes:
				self.__dict__[x]=myfoo.__dict__[x]
			#point to existing "cmp" comparison cache.  This will allow us to share comparison caches as long
			#as they are identical, and is a really nice way of saving space and being a bit more efficient.
			self.__dict__["cmp"]=myfoo.__dict__["cmp"]
			return
		
		#generate a new eid from a supplied string.
		if not myfoo:
			self.invalidate()
			return
		
		self.__dict__["repr"]=myfoo	
		self.parse_repr()
	
	def __cmp__(self,other):
		"comparison operator code"
		if self.cmp==None:
			self.__dict__["cmp"]=self.gencmp()
		if other.cmp==None:
			other.__dict__["cmp"]=other.gencmp()
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
	
class eid(constraint):

	"""An eid is used to specify a single, specific category/package-version-rev."""
	
	attributes=constraint.attributes+["key","category","version","revision"]

	pattern=re.compile(
		'^(\w+-\w+)/'                           # category
		'([^/]+?)'                              # name
		'-(\d+(?:\.\d+)*[a-z]*)'                # version, eg 1.23.4a
		'(_(?:alpha|beta|pre|rc|p)\d*)?'        # special suffix
		'(?:-r(\d+))?$')                        # revision, eg r12

	def parse_repr(self):
		match=self.__class__.pattern.search(self.repr)
		if match:
			(self.__dict__["category"], self.__dict__["package"], v1, v2, rev) = match.groups()
			self.__dict__["version"] = v1 + (v2 or '')
			self.__dict__["revision"] = rev or '0'
			self.__dict__["valid"]=1
			self.__dict__["cmp"]=None
			self.__dict__["error"]=None
			self.__dict__["key"]=self.category+"/"+self.package
			return

		# parse error -- try to figure out what's wrong with a looser regexp
		match=re.compile(
				'^(?:(.*)/)?'                     # category
				'([^/]*?)'                        # name
				'(?:-([^-_]*?))?'                 # version, eg 1.23.4a
				'(_?(?:alpha|beta|pre|rc|p)\d*)?' # special suffix
				'(?:-r(.*))?$'                    # revision, eg r12
			).search(myfoo)
		if not match:
			# no good -- even the loose regexp failed
			self.invalidate("Unparseable")
			return
		(cat, pkg, v1, v2, rev) = match.groups()
		self.__dict__["key"]=cat+"/"+pkg
		# the loose regexp worked; now try to find which part is wrong
		if not cat:                               # check category
			self.invalidate("Missing category")
		elif len(string.split(cat, "/")) > 1:
			self.invalidate("More than on \"/\"")
		elif len(string.split(cat, "-")) != 2:
			self.invalidate("Expected exactly 1 \"-\" in category")
		elif not pkg:                             # check package name
			self.invalidate("Missing package name")
		elif not v1:                              # check version
			self.invalidate("Missing version")
		elif not re.compile('^\d+(?:\.\d+)*[a-z]*$').search(v1):
			self.invalidate("Invalid version number")
		elif v2 and v2[0] != '_':
			self.invalidate("Invalid ending version part")
		elif rev != None and not re.compile('^\d+').search(rev):
			self.invalidate("Invalid revision number")
		else:
			self.invalidate("Miscellaneous error")

	def similar(self,other):
		"are we talking about the same category and package (but possibly different versions/revs)?"
		if (self.valid and other.valid) and (self.key == other.key):
			return 1
		return 0
	
	def __setattr__(self,name,value):
		"""causes repr and key to be automatically regenerated if values are assigned to category, package, version, revision.
		input is assumed to be valid.  The comparison cache is also flushed (since data may not be up-to-date)"""
		if not self.valid:
			return
		if name not in ["category","package","version","revision"]:
			return
		self.__dict__[name]=value
		self.__dict__["key"]=self.category+"/"+self.package
		self.__dict__["repr"]=self.key+"-"+self.version
		if self.revision!="0":
			self.__dict__["repr"]=self.repr+"-r"+self.revision
		#reset cmp information (invalid)
		self.__dict__["cmp"]=None

	def __mod__(self,other):
		"self is an eid, and other is a range"	
		return eval("self "+other.operator+" other")


class depid(constraint):

	"""A depid is used to specify a specific version/rev ("=") or simple
	version range (">","<",">=","<=").  Depids contain no category/package
	information."""

	#used by selector.invalidate()
	attributes=["version","revision","operator"]
	
	pattern=re.compile(
		'(=|!|>|>=|<|<=)'						# comparison operator
		'(\d+(?:\.\d+)*[a-z]*)'                # version, eg 1.23.4a
		'(_(?:alpha|beta|pre|rc|p)\d*)?'        # special suffix
		'(?:-r(\d+))?$')                        # revision, eg r12

	def parse_repr(self):
		#we use self.__dict__ instead of direct assignment to avoid calling our __setattr__ method
		match=self.__class__.pattern.search(self.repr)
		if not match:
			#we need to add error handling/detection here
			self.invalidate("misc. error (full error messages not implemented yet)")
			return
		(op, v1, v2, rev) = match.groups()
		self.__dict__["operator"] = op
		self.__dict__["version"] = v1 + (v2 or '')
		self.__dict__["revision"] = rev or '0'
		self.__dict__["valid"]=1
		self.__dict__["cmp"]=None
		self.__dict__["error"]=None
		return
		
	def __setattr__(self,name,value):
		"""causes repr and key to be automatically regenerated if values are assigned. The comparison cache is also flushed (since data may not be up-to-date)"""
		if not self.valid:
			return
		if name not in self.attributes:
			#we can ignore the assign
			return
		self.__dict__[name]=value
		self.__dict__["repr"]=self.operator+self.version
		if self.revision!="0":
			self.__dict__["repr"]=self.repr+"-r"+self.revision
		#reset cmp information (since it's probably invalid now)
		self.__dict__["cmp"]=None

class eidset:

	"""An eidset is used to encapsulate a bunch of eids, allowing subsets to be
	queried using the subset() method.  This particular eidset is hard-coded to
	get its data from /usr/portage; the future eidset implementation will not
	be tied to the filesystem, but there will likely be a portageeidset,
	dbeidset, pkgeidset subclass that do pull their data from the filesystem,
	just like this one."""

	def __init__(self):
		self.keydict={}
		
	def populate(self):
		os.chdir("/usr/portage")
		for x in categories:
			if not os.path.isdir(os.getcwd()+"/"+x):
				continue
			for y in os.listdir(os.getcwd()+"/"+x):
				if not os.path.isdir(os.getcwd()+"/"+x+"/"+y):
					continue
				if y=="CVS":
					continue
				for mypkg in os.listdir(os.getcwd()+"/"+x+"/"+y):
					if mypkg[-7:] != ".ebuild":
						continue
					mypkg=mypkg[:-7]
					mykey=x+"/"+y
					fullpkg=x+"/"+mypkg
					if not self.keydict.has_key(mykey):
						self.keydict[mykey]=[]
					a=eid(fullpkg)
					if not a.valid:
						print "INVALID!",x,y,mypkg
						continue
					self.keydict[mykey].append(a)
			
	def subset(self,selectors):
		"""A subset allows you to select a single category/package (key) and then whittle down the resultant set by using
		depids."""
		myset=eidset()
		for x in selectors:
			if x.__class__==key:
				#if a key selector is specified, select a subset that matches that particular cat/pkg key
				if x.specific:
					if (not myset.keydict.has_key(x.repr)) and self.keydict.has_key(x.repr):
						myset.keydict={}
						#copy the list, don't just reference it (so we can modify it without introducing side-effects)
						myset.keydict[x.repr]=self.keydict[x.repr][:]
					else:
						myset.keydict={}
				else:
					print "WARNING: non-specific key subsets not implemented yet."
					#not specific... and not yet implemented! :)
					pass
			elif x.__class__==depid:
				#if a constraint is specified, iterate through our keys and eliminate non-matching constraints
				for mykey in myset.keydict.keys():
					pos=0
					mylist=myset.keydict[mykey]
					#iterate through a list of constraints
					while pos<len(mylist):
						#is mylist's current package a member of the specified depid?
						if not mylist[pos] % x:
							del mylist[pos]
							#don't increment, since we zapped the current node
							continue
						pos=pos+1	
		return myset

def _test():
	import doctest, portage_core
	return doctest.testmod(portage_core)

if __name__ == "__main__":
	rng=[depid(">=3.0"),depid("<2.0"),depid(">3.1"),depid(">=3.1")]
	e=[eid("sys-apps/foo-3.1"),eid("sys-apps/bar-2.0")]
	print e
	print rng
	for x in e:
		for y in rng:
			# x % y prints out a boolean value that answers the question "is eid x a member of the range specified in depid y?"
			# we override the modulo operator to allow for a membership test.  We may move this to an .ismemberof() method in the
			# future, which would be a trivial change and would be more self-documenting.
			print `x`+`y`, x % y
	#we create a new eidset
	myset=eidset()
	#we call the (hard-coded) populate function to fill the eidset with data from /usr/portage
	myset.populate()
	#we use the subset method to select the media-libs/libsdl packages >=1.2.0 but also <1.2.2.
	mynewset=myset.subset([key("media-libs/libsdl"),depid(">=1.2.0"),depid("<1.2.2")])
	#we print the result :)
	print mynewset.keydict
