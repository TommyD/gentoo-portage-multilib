# Copyright 1999-200 Gentoo Technologies, Inc. 
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author: Daniel Robbins <drobbins@gentoo.org>
# $Header$

import string
import re

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}


class eid:
	"""
	An eid is an ebuild/package id, consisting of a category, package, version
	and revision.  If validate is set to 1 (the default), the init code will
	validate the input.  If set to zero, the input is assumed correct, but an
	exception will be raised if it is not.

	An eid, or ebuild id, is an object that stores category, package, version
	and revision information.  eids can be valid or invalid.  If validate is
	set to 1 (the default), the init code will validate the input.  If set to
	zero, the input is assumed correct, but an exception will be raised if it
	is not.  If invalid, the eid will set an internal variable called "error"
	to a human-readable error message describing what is wrong with the eid.
	Note that eids aren't tied to a particular ebuild file or package database
	entry; instead they're used by Portage to talk about particular
	category/package-version-revs in the abstract.  Because all the information
	about a particular ebuild/db entry/.tbz2 package is stored in a single
	object, a lot of redundancy is eliminated.  Also, the eid methods make good
	use of caching in order to optimize performance for version comparisons,
	etc.

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

	MORE TESTS:

	>>> a=eid("sys-apps/foo-3.0")
	>>> b=eid("sys-apps/foo-1.0_rc6")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '1.0_rc6', '0', 1, 'sys-apps/foo-1.0_rc6', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-4.0_pre12")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '4.0_pre12', '0', 1, 'sys-apps/foo-4.0_pre12', None], 1, 0, 1)
	>>> b=eid("sys-apps/foo-4.0")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '4.0', '0', 1, 'sys-apps/foo-4.0', None], 1, 0, 1)
	>>> b=eid("sys-apps/foo-9.12.13")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '9.12.13', '0', 1, 'sys-apps/foo-9.12.13', None], 1, 0, 1)
	>>> b=eid("sys-apps/foo-0.9.10")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '0.9.10', '0', 1, 'sys-apps/foo-0.9.10', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-1.0.9-r1")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '1.0.9', '1', 1, 'sys-apps/foo-1.0.9-r1', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-3.0")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0', '0', 1, 'sys-apps/foo-3.0', None], 1, 0, 0)
	>>> b=eid("sys-apps/foo-3.0_alpha1")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0_alpha1', '0', 1, 'sys-apps/foo-3.0_alpha1', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-3.0_beta")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0_beta', '0', 1, 'sys-apps/foo-3.0_beta', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-3.0_rc1")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0_rc1', '0', 1, 'sys-apps/foo-3.0_rc1', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-3.0_pre1")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0_pre1', '0', 1, 'sys-apps/foo-3.0_pre1', None], 1, 1, 0)
	>>> b=eid("sys-apps/foo-3.0_p3")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0_p3', '0', 1, 'sys-apps/foo-3.0_p3', None], 1, 0, 1)
	>>> b=eid("sys-apps/foo-3.0a")
	>>> b.debug(0), b.valid, a>b, a<b
	([None, 'sys-apps', 'foo', '3.0a', '0', 1, 'sys-apps/foo-3.0a', None], 1, 0, 1)
"""

	pattern=re.compile(
		'^(\w+-\w+)/'                           # category
		'([^/]+?)'                              # name
		'-(\d+(?:\.\d+)*[a-z]*)'                # version, eg 1.23.4a
		'(_(?:alpha|beta|pre|rc|p)\d*)?'        # special suffix
		'(?:-r(\d+))?$')                        # revision, eg r12

	def __init__(self,mystring=None,validate=1):
		"initialization; optional assignment; optional validation of input (otherwise assumed correct)"
		self.repr=mystring
		self.valid=1
		self.cmp=None
		self.error=None
		
		if not mystring:
			self.invalidate()
			return
		match=eid.pattern.search(mystring)
		if match:
			(self.category, self.package, v1, v2, rev) = match.groups()
			self.version = v1 + (v2 or '')
			self.revision = rev or '0'
			return

		# parse error -- try to figure out what's wrong with a looser regexp
		match=re.compile(
				'^(?:(.*)/)?'                     # category
				'([^/]*?)'                        # name
				'(?:-([^-_]*?))?'                 # version, eg 1.23.4a
				'(_?(?:alpha|beta|pre|rc|p)\d*)?' # special suffix
				'(?:-r(.*))?$'                    # revision, eg r12
			).search(mystring)
		if not match:
			# no good -- even the loose regexp failed
			self.invalidate("Unparseable")
			return
		(cat, pkg, v1, v2, rev) = match.groups()

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
	
	def debug(self, verbose=1):
		"internal debug function"
		if verbose:
			print
			print "DEBUG EID"
		out=[]
		for x in ["error","category","package","version","revision","valid","repr","cmp"]:
			try:
				exec("y=self." + x)
			except:
				y="(undefined)"
			out.append(y)
			if verbose:
				print x, y
		return out
	
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

class eidset:
	def __init__(self):
		self.db={"category":{},"catpkg":{},"rep":{}}
	
	def add(self,myeid):
		"add an eid, indexing by category, catpkg and rep"
		if not myeid.valid:
			return
		if not self.db["category"].has_key(myeid.category):
			self.db["category"][myeid.category]=[]
		self.db["category"][myeid.category].append(myeid)
		mykey=myeid.category+"/"+myeid.package
		if not self.db["catpkg"].has_key(mykey):
			self.db["catpkg"][mykey]=[]
		self.db["catpkg"][mykey].append(myeid)
		self.db["rep"][myeid.rep]=myeid



"""new dep ideas:

we introduce the concept of "hard deps" and "soft deps".  By default, apps use
"hard deps".  Hard deps are used to decribe relationships where the ebuild
depends on a specific version/rev of a package currently installed, and becomes
intrinsically tied to it.  soft deps specify a dependency on a set of packages.
As long as one of the set is currently installed, the package will run fine.

Syntax ideas:

=sys-apps/foo-1.0 (hard dep)
'sys-apps/man (soft dep, depends on any version of man)
sys-apps/man (hard dep, depends on the specific version of man installed right now)
'foo/bar (soft dep, requires foo/bar and foo/oni to be installed
'{foo/bar >=1.0 <2.0} (soft dep using new set syntax, depending on any foo/bar 1.0 or greater, but less than 2.0)
'{foo/bar 1.*} (same as above)
'{foo/bar >=1.2 <2.0} (more specific)
'{foo/bar ~1.0 ~1.3} (any revision of 1.0 or 1.3)
{foo/bar >=4.0} a *hard* dependency on any ebuild
Questions: do we need to be able to "*hard*" depend on a specific version *and*
rev of a package?

Tenative answer: yes.  The hard dependency should depend on whatever rev is installed,
and if a new rev is installed, the package dependent on it should be rebuilt too.

Do we need to only be able to hard-depend on a specific version of a package?

Tenative answer: no. hard deps are used to link multiple packages into
a logical whole.  A hard dep is like concrete, forming an amalgam meta-package.

Why we are doing this: By specifying hard and soft deps, we provide the necessary
info that Portage needs to carefully rebuild/upgrade the system.  We can now track
how packages *currently* are relying on one another... this is something that we
aren't doing yet, and is required for a nice, fast "emerge update" implementation.

Question: will this additional informatin allow portage to determine if a particular
package is currently being depended upon by anything on the running system?

Answer: yes, it will.  Whee!
"""

def _test():
	import doctest, portage_core
	return doctest.testmod(portage_core)

if __name__ == "__main__":
	_test()

