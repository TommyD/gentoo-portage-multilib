# Gentoo Linux Dependency Checking Code
# Copyright 1998-2000 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License

# TO-DO:
# (I'm adding this here because I lose or forget about all my other Portage
# TO-DO files... 
#
# rewrite download system
# -----------------------
# support partials, look into GENTOO_MIRRORS issue
#
# subpackages
# ===========
#src_install will work as normal, and will create the master image that includes
#everything in ${D}.  There will be a new function, called src_subpkg that contains
#instructions for selecting files from ${D} and copying them to subpkg dirs, where
#they will get seperately packaged.  The function will look something like this:
#
#src_subpkg() {
#	subpkg bin
#	#maybe grab should use regular expressions, not globbing?
#	grab /usr/bin/* /usr/sbin/* /usr/lib/*.so
#	
#	subpkg dev
#	grab /usr/lib/*.a (any way to say "everything but *.so"?)
#}
#
#Subpackage naming will work as follows.  For a package foo-1.0, foo-1.0.tbz2
#will be the master package and include all subpackages.  foo:dev-1.0.tbz2 will
#be the development package, and foo:run-1.0.tbz2 will be a runtime package,
#etc.  It should be possible to simply treat them as unique package names with
#P="foo:dev" and P="foo:run" respectively.
#
#dep resolution needs to be upgraded a bit, though.  "sys-apps/foo" will depend
#on the foo master package (i.e. foo-1.0.tbz2) for backwards compatibility.  However,
#it will now also be possible to depend on "sys-apps/foo:dev" or "sys-apps/foo:run",
#and the dep system needs to be upgraded so that it knows how to satisfy these 
#dependencies.  This should allow the new subpackages system to be integrated 
#seamlessly into our existing dependency hierarchy.
#
#Note: It may also be a good idea to allow a make.conf option so that "sys-apps/foo:run"
#automatically resolves to the master package (for those who prefer complete packages
#rather than installing things piecemeal; a great idea for development boxes where many
#things will depend on "sys-apps/foo:dev" for headers, but the developer may want the
#whole enchilada. (generally, I prefer this approach, though for runtime-only systems
#subpackages make a lot of sense).
#
#new dependency functionality
#============================
#
#Important new dep functionality:
#
# ~ IS NOW ADDED
#
#~sys-apps/foo-1.0 will match the latest rev of foo-1.0.  Useful because the latest rev
#should be the most stable and reliable version.
#
#Next, sys-apps/foo-1.0* will match the latest package that starts with 1.0; so 1.0.3 will
#match.  This is an excellent way to depend on libraries where you need a specific major
#or minor version, but also want to be able to use the latest "really minor" version and
#rev available.  For example, if your app depends on glib-1.2:
#
#dev-libs/glib-1.2*
#
#This will match glib-1.2, glib-1.2-r1, glib-1.2.1 and glib-1.2.1.1-r1.  Of these four
#examples, the last will be chosen (most recent) if all are available.  However, glib-1.3
#will not be considered for this dependency.

import string,os
from stat import *
from commands import *
import fchksum,types
import sys
import shlex
import shutil
import xpak
import re
import copy

# master category list.  Any new categories should be added to this list to
# ensure that they all categories are read when we check the portage directory
# for available ebuilds.

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

def tokenize(mystring):
	"""breaks a string like 'foo? (bar) oni? (blah (blah))' into embedded lists; returns None on paren mismatch"""
	tokens=string.split(mystring)
	newtokens=[]
	curlist=newtokens
	prevlist=None
	level=0
	accum=""
	for x in mystring:
		if x=="(":
			if accum:
				curlist.append(accum)
				accum=""
			newlist=[]
			curlist.append(newlist)
			prevlist=curlist
			curlist=newlist
			level=level+1
		elif x==")":
			if accum:
				curlist.append(accum)
				accum=""
			curlist=prevlist
			if level==0:
				return None
			level=level-1
		elif x in string.whitespace:
			if accum:
				curlist.append(accum)
				accum=""
		else:
			accum=accum+x
	if level!=0:
		return None
	if accum:
		curlist.append(accum)
	return newtokens

def evaluate(mytokens,mydefines,allon=0):
	"""removes tokens based on whether conditional definitions exist or not.  Recognizes !"""
	pos=0
	if mytokens==None:
		return None
	while pos<len(mytokens):
		if type(mytokens[pos])==types.ListType:
			evaluate(mytokens[pos],mydefines)
			if not len(mytokens[pos]):
				del mytokens[pos]
				continue
		elif mytokens[pos][-1]=="?":
			cur=mytokens[pos][:-1]
			del mytokens[pos]
			if allon:
				if cur[0]=="!":
					del mytokens[pos]
			else:
				if cur[0]=="!":
					if ( cur[1:] in mydefines ) and (pos<len(mytokens)):
						del mytokens[pos]
						continue
				elif ( cur not in mydefines ) and (pos<len(mytokens)):
					del mytokens[pos]
					continue
		pos=pos+1
	return mytokens

def flatten(mytokens):
	"""convert embedded list into string"""
	newstring=""
	for x in mytokens:
		if type(x)==types.ListType:
			newstring=newstring+" "+flatten(x)
		else:
			newstring=newstring+" "+x
	return newstring

#beautiful directed graph object

class digraph:
	def __init__(self):
		self.dict={}
		#okeys = keys, in order they were added (to optimize firstzero() ordering)
		self.okeys=[]
	
	def addnode(self,mykey,myparent):
		if not self.dict.has_key(mykey):
			self.okeys.append(mykey)
			if myparent==None:
				self.dict[mykey]=[0,[]]
			else:
				self.dict[mykey]=[0,[myparent]]
				self.dict[myparent][0]=self.dict[myparent][0]+1
			return
		if not myparent in self.dict[mykey][1]:
			self.dict[mykey][1].append(myparent)
			self.dict[myparent][0]=self.dict[myparent][0]+1
	
	def delnode(self,mykey):
		if not self.dict.has_key(mykey):
			return
		for x in self.dict[mykey][1]:
			self.dict[x][0]=self.dict[x][0]-1
		del self.dict[mykey]
		while 1:
			try:
				self.okeys.remove(mykey)	
			except ValueError:
				break
	
	def firstzero(self):
		"returns first node with zero references, or NULL if no such node exists"
		for x in self.okeys:
			if self.dict[x][0]==0:
				return x
		return None 

	def empty(self):
		if len(self.dict)==0:
			return 1
		return 0

	def hasnode(self,mynode):
		return self.dict.has_key(mynode)

	def copy(self):
		mygraph=digraph()
		for x in self.dict.keys():
			mygraph.dict[x]=self.dict[x][:]
			mygraph.okeys=self.okeys[:]
		return mygraph

# valid end of version components; integers specify offset from release version
# pre=prerelease, p=patchlevel (should always be followed by an int), rc=release candidate
# all but _p (where it is required) can be followed by an optional trailing integer

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}
# as there's no reliable way to set {}.keys() order
# netversion_keys will be used instead of endversion.keys
# to have fixed search order, so that "pre" is checked
# before "p"
endversion_keys = ["pre", "p", "alpha", "beta", "rc"]

#parse /etc/env.d and generate /etc/profile.env

def env_update():
	global root
	if not os.path.exists(root+"etc/env.d"):
		prevmask=os.umask(0)
		os.makedirs(root+"etc/env.d",0755)
		os.umask(prevmask)
	fns=os.listdir(root+"etc/env.d")
	fns.sort()
	pos=0
	while (pos<len(fns)):
		if fns[pos]<=2:
			del fns[pos]
			continue
		if (fns[pos][0] not in string.digits) or (fns[pos][1] not in string.digits):
			del fns[pos]
			continue
		pos=pos+1

	specials={"PATH":[],"CLASSPATH":[],"LDPATH":[],"MANPATH":[],"INFODIR":[],"ROOTPATH":[]}
	env={}

	for x in fns:
		# don't process backup files
		if x[-1]=='~' or x[-4:]==".bak":
			continue
		myconfig=getconfig(root+"etc/env.d/"+x)
		# process PATH, CLASSPATH, LDPATH
		for myspec in specials.keys():
			if myconfig.has_key(myspec):
				if myspec=="LDPATH":
					specials[myspec].extend(string.split(expand(myconfig[myspec]),":"))
				else:
					specials[myspec].append(expand(myconfig[myspec]))
				del myconfig[myspec]
		# process all other variables
		for myenv in myconfig.keys():
			env[myenv]=expand(myconfig[myenv])
			
	if os.path.exists(root+"etc/ld.so.conf"):
		myld=open(root+"etc/ld.so.conf")
		myldlines=myld.readlines()
		myld.close()
		oldld=[]
		for x in myldlines:
			#each line has at least one char (a newline)
			if x[0]=="#":
				continue
			oldld.append(x[:-1])
		oldld.sort()
	#	os.rename(root+"etc/ld.so.conf",root+"etc/ld.so.conf.bak")
	# Where is the new ld.so.conf generated? (achim)
	else:
		oldld=None
	specials["LDPATH"].sort()
	if (oldld!=specials["LDPATH"]):
		#ld.so.conf needs updating and ldconfig needs to be run
		newld=open(root+"etc/ld.so.conf","w")
		newld.write("# ld.so.conf autogenerated by env-update; make all changes to\n")
		newld.write("# contents of /etc/env.d directory\n")
		for x in specials["LDPATH"]:
			newld.write(x+"\n")
		newld.close()
		#run ldconfig here
	print ">>> Regenerating "+root+"etc/ld.so.cache..."
	getstatusoutput("/sbin/ldconfig -r "+root)
	del specials["LDPATH"]

	#create /etc/profile.env for bash support
	outfile=open(root+"/etc/profile.env","w")

	for path in specials.keys():
		if len(specials[path])==0:
			continue
		outstring="export "+path+"='"
		for x in specials[path][:-1]:
			outstring=outstring+x+":"
		outstring=outstring+specials[path][-1]+"'"
		outfile.write(outstring+"\n")
		#get it out of the way
#		del specials[path]
	
	#create /etc/profile.env
	for x in env.keys():
		if type(env[x])!=types.StringType:
			continue
		outfile.write("export "+x+"='"+env[x]+"'\n")
	outfile.close()
	
	#creat /etc/csh.env for (t)csh support
	outfile=open(root+"/etc/csh.env","w")
	
	for path in specials.keys():
		if len(specials[path])==0:
			continue
		outstring="setenv "+path+" '"
		for x in specials[path][:-1]:
			outstring=outstring+x+":"
		outstring=outstring+specials[path][-1]+"'"
		outfile.write(outstring+"\n")
		#get it out of the way
		del specials[path]
	
	#create /etc/csh.env
	for x in env.keys():
		if type(env[x])!=types.StringType:
			continue
		outfile.write("setenv "+x+" '"+env[x]+"'\n")
	outfile.close()


def grabfile(myfilename):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a list; if a line
	begins with a #, it is ignored, as are empty lines"""

	myfile=open(myfilename,"r")
	if not myfile:
		#keep it an empty sequence type to be loop friendly
		return []
	mylines=myfile.readlines()
	myfile.close()
	newlines=[]
	for x in mylines:
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		myline=string.join(string.split(x))
		if not len(myline):
			continue
		if myline[0]=="#":
			continue
		newlines.append(myline)
	return newlines
	
def getconfig(mycfg,tolerant=0):
	mykeys={}
	f=open(mycfg,'r')
	lex=shlex.shlex(f)
	lex.wordchars=string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"     
	lex.quotes="\"'"
	while 1:
		key=lex.get_token()
		if (key==''):
			#normal end of file
			break;
		equ=lex.get_token()
		if (equ==''):
			#unexpected end of file
			#lex.error_leader(self.filename,lex.lineno)
			if not tolerant:
				print "!!! Unexpected end of config file: variable",key
				return None
			else:
				return mykeys
		elif (equ!='='):
			#invalid token
			#lex.error_leader(self.filename,lex.lineno)
			if not tolerant:
				print "!!! Invalid token (not \"=\")",equ
				return None
			else:
				return mykeys
		val=lex.get_token()
		if (val==''):
			#unexpected end of file
			#lex.error_leader(self.filename,lex.lineno)
			if not tolerant:
				print "!!! Unexpected end of config file: variable",key
				return None
			else:
				return mykeys
		mykeys[key]=val
	return mykeys

def expand(mystring,dictlist=[]):
	"""
	new variable expansion code.  Removes quotes, handles \n, etc, and
	will soon use the dictlist to expand ${variable} references.
	This code will be used by the configfile code, as well as others (parser)
	This would be a good bunch of code to port to C.
	"""
	mystring=" "+mystring
	#in single, double quotes
	insing=0
	indoub=0
	pos=1
	newstring=" "
	while (pos<len(mystring)):
		if (mystring[pos]=="'") and (mystring[pos-1]!="\\"):
			if (indoub):
				newstring=newstring+"'"
			else:
				insing=not insing
			pos=pos+1
			continue
		elif (mystring[pos]=='"') and (mystring[pos-1]!="\\"):
			if (insing):
				newstring=newstring+'"'
			else:
				indoub=not indoub
			pos=pos+1
			continue
		if (not insing): 
			#expansion time
			if (mystring[pos]=="\\"):
				#backslash expansion time
				if (pos+1>=len(mystring)):
					newstring=newstring+mystring[pos]
					break
				else:
					a=mystring[pos+1]
					pos=pos+2
					if a=='a':
						newstring=newstring+chr(007)
					elif a=='b':
						newstring=newstring+chr(010)
					elif a=='e':
						newstring=newstring+chr(033)
					elif (a=='f') or (a=='n'):
						newstring=newstring+chr(012)
					elif a=='r':
						newstring=newstring+chr(015)
					elif a=='t':
						newstring=newstring+chr(011)
					elif a=='v':
						newstring=newstring+chr(013)
					else:
						#remove backslash only, as bash does: this takes care of \\ and \' and \" as well
						newstring=newstring+mystring[pos-1:pos]
						continue
			elif (mystring[pos]=="$") and (mystring[pos-1]!="\\"):
				pos=pos+1
				if (pos+1)>=len(mystring):
					return ""
				if mystring[pos]=="{":
					pos=pos+1
					terminus="}"
				else:
					terminus=string.whitespace
				myvstart=pos
				while mystring[pos] not in terminus:
					if (pos+1)>=len(mystring):
						return ""
					pos=pos+1
				myvarname=mystring[myvstart:pos]
				pos=pos+1
				if len(myvarname)==0:
					return ""
				newstring=newstring+settings[myvarname]	
			else:
				newstring=newstring+mystring[pos]
				pos=pos+1
		else:
			newstring=newstring+mystring[pos]
			pos=pos+1
	return newstring[1:]	

class config:
	def __init__(self):
		self.origenv=os.environ.copy()
		self.populated=0
	def populate(self):
		if profiledir and os.path.exists(profiledir+"/make.defaults"):
			self.configlist=[self.origenv.copy(),getconfig("/etc/make.conf"),getconfig(profiledir+"/make.defaults"),getconfig("/etc/make.globals")]
		else:
			self.configlist=[self.origenv.copy(),getconfig("/etc/make.conf"),getconfig("/etc/make.globals")]
		self.populated=1
		if settings.has_key("MAINTAINER"):
			if settings["MAINTAINER"]=="yes":
				settings["MAINTAINER"]=settings["MAINTAINER_DEFAULT"]
			maintainerparts=string.split(settings["MAINTAINER"],' ')
			for x in maintainerparts:
				settings["MAINTAINER_"+x]="1"
	
	def __getitem__(self,mykey):
		if not self.populated:
			self.populate()
		if mykey=="CONFIG_PROTECT_MASK":
			#Portage needs to always auto-update these files (so that builds don't die when remerging gcc)
			returnme="/etc/env.d "
		else:
			returnme=""
		for x in self.configlist:
			if x.has_key(mykey):
				returnme=returnme+expand(x[mykey],self.configlist)
				#without this break, it concats all settings together -- interesting!
				break
		return returnme		
	
	def has_key(self,mykey):
		if not self.populated:
			self.populate()
		for x in self.configlist:
			if x.has_key(mykey):
				return 1 
		return 0
	def keys(self):
		if not self.populated:
			self.populate()
		mykeys=[]
		for x in self.configlist:
			for y in x.keys():
				if y not in mykeys:
					mykeys.append(y)
		return mykeys
	def __setitem__(self,mykey,myvalue):
		if not self.populated:
			self.populate()
		self.configlist[0][mykey]=myvalue
	def reset(self):
		if not self.populated:
			self.populate()
		"reset environment to original settings"
		self.configlist[0]=self.origenv.copy()
	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		for x in self.keys(): 
			mydict[x]=self[x]
		return mydict
	
def spawn(mystring,debug=0):
	global settings
	mypid=os.fork()
	if mypid==0:
		myargs=[]
		if settings["MAINTAINER_sandbox"]=="1":
			mycommand="/usr/lib/portage/bin/sandbox"
			if debug:
				myargs=["sandbox",mystring]
			else:
				myargs=["sandbox",mystring]
		else:
			mycommand="/bin/bash"
			if debug:
				myargs=["bash","-x","-c",mystring]
			else:
				myargs=["bash","-c",mystring]
		os.execve(mycommand,myargs,settings.environ())
		return
	retval=os.waitpid(mypid,0)[1]
	if (retval & 0xff)==0:
		#return exit code
		return (retval >> 8)
	else:
		#interrupted by signal
		return 16

def getmycwd():
	"this handles situations where the current directory doesn't exist"
	try:
		a=os.getcwd()
	except:
		os.chdir("/")
		a=os.getcwd()
	return a

def doebuild(myebuild,mydo,myroot,checkdeps=1,debug=0):
	global settings
	if not os.path.exists(myebuild):
		print "!!!",myebuild,"not found."
		return 1
	if myebuild[-7:]!=".ebuild":
		print "!!!",myebuild,"does not appear to be an ebuild file."
		return 1
	settings.reset()
	settings["PORTAGE_DEBUG"]=str(debug)
	#settings["ROOT"]=root
	settings["ROOT"]=myroot
	settings["STARTDIR"]=getmycwd()
	settings["EBUILD"]=os.path.abspath(myebuild)
	settings["O"]=os.path.dirname(settings["EBUILD"])
	settings["CATEGORY"]=os.path.basename(os.path.normpath(settings["O"]+"/.."))
	#PEBUILD
	settings["FILESDIR"]=settings["O"]+"/files"
	settings["PF"]=os.path.basename(settings["EBUILD"])[:-7]
	settings["SANDBOX_LOG"]=settings["PF"]
	mysplit=pkgsplit(settings["PF"],0)
	if mysplit==None:
		print "!!! Error: PF is null; exiting."
		return 1
	settings["P"]=mysplit[0]+"-"+mysplit[1]
	settings["PN"]=mysplit[0]
	settings["PV"]=mysplit[1]
	settings["PR"]=mysplit[2]
	if mysplit[2]=="r0":
		settings["PVR"]=mysplit[1]
	else:
		settings["PVR"]=mysplit[1]+"-"+mysplit[2]
	settings["SLOT"]=settings["PV"]
	if settings.has_key("PATH"):
		mysplit=string.split(settings["PATH"],":")
	else:
		mysplit=[]
	if not "/usr/lib/portage/bin" in mysplit:
		settings["PATH"]="/usr/lib/portage/bin:"+settings["PATH"]

	if not settings.has_key("BUILD_PREFIX"):
		print "!!! Error: BUILD_PREFIX not defined."
		return 1
	settings["BUILDDIR"]=settings["BUILD_PREFIX"]+"/"+settings["PF"]
	if not os.path.exists(settings["BUILDDIR"]):
		os.makedirs(settings["BUILDDIR"])
	settings["T"]=settings["BUILDDIR"]+"/temp"
	if not os.path.exists(settings["T"]):
		os.makedirs(settings["T"])
	settings["WORKDIR"]=settings["BUILDDIR"]+"/work"
	settings["D"]=settings["BUILDDIR"]+"/image/"
	
	#initial ebuild.sh bash environment configured
	myso=getstatusoutput("/usr/sbin/ebuild.sh depend")
	if myso[0]!=0:
		print
		print
		print "!!! Portage had a problem processing this file:"
		print "!!!",settings["EBUILD"]
		print 
		print myso[1]
		print
		print "!!! aborting."
		print
		return 1
	# obtain the dependency and slot information from the deps file
	a=open(settings["T"]+"/deps","r")
	counter=0
	mydeps=a.readlines()
	# remove trailing lines
	for mydeps_entry in mydeps:
		mydeps[counter]=mydeps_entry.strip()
		counter=counter+1
	a.close()
	# get possible slot information from the deps file
	if mydeps[2]!="":
		settings["SLOT"]=mydeps[2]
	if checkdeps:
		if mydo=="depend":
			return mydeps
		elif mydo=="check":
			return dep_frontend("build",myebuild,mydeps[0])
		elif mydo=="rcheck":
			return dep_frontend("runtime",myebuild,mydeps[1])
		if mydo in ["merge","qmerge","unpack", "compile", "rpm", "package"]:
			#optional dependency check -- if emerge is merging, this is skipped 
			retval=dep_frontend("build",myebuild,mydeps[0])
			if (retval): return retval
	else:
		if mydo in ["depend","check","rcheck"]:
			print "!!! doebuild(): ",mydo,"cannot be called with checkdeps equal to zero."
			return 1
		
	#initial dep checks complete; time to process main commands
	
	a=open(settings["T"]+"/src_uri","r")
	myuris=a.readline()
	a.close()
	newuris=evaluate(tokenize(myuris),string.split(settings["USE"]))	
	alluris=evaluate(tokenize(myuris),[],1)	
	a=open(settings["T"]+"/src_uri_new","w")
	a.write(flatten(newuris))
	a.close()
	a=open(settings["T"]+"/src_uri_all","w")
	a.write(flatten(alluris))
	a.close()
	
	if mydo=="help": 
		return spawn("/usr/sbin/ebuild.sh help")
	elif mydo=="unpack": 
		if settings["MAINTAINER_noauto"]=="1":
			return spawn("/usr/sbin/ebuild.sh unpack")
		else:
			return spawn("/usr/sbin/ebuild.sh setup fetch unpack")
	elif mydo=="compile":
		if settings["MAINTAINER_noauto"]=="1":
			return spawn("/usr/sbin/ebuild.sh compile")
		else:
			return spawn("/usr/sbin/ebuild.sh setup fetch unpack compile")
	elif mydo=="install":
		if settings["MAINTAINER_noauto"]=="1":
			return spawn("/usr/sbin/ebuild.sh install")
		else:
			return spawn("/usr/sbin/ebuild.sh setup fetch unpack compile install")
	elif mydo=="rpm": 
		if settings["MAINTAINER_noauto"]=="1":
			return spawn("/usr/sbin/ebuild.sh rpm")
		else:
			return spawn("/usr/sbin/ebuild.sh setup fetch unpack compile install rpm")
	elif mydo in ["prerm","postrm","preinst","postinst","config","touch","clean","setup","fetch","digest","batchdigest"]:
		return spawn("/usr/sbin/ebuild.sh "+mydo)
	elif mydo=="qmerge": 
		#qmerge is specifically not supposed to do a runtime dep check
		return merge(settings["CATEGORY"],settings["PF"],settings["D"],settings["BUILDDIR"]+"/build-info",myroot)
	elif mydo=="merge":
		retval=spawn("/usr/sbin/ebuild.sh setup fetch unpack compile install")
		if retval: return retval
		if checkdeps:
			retval=dep_frontend("runtime",myebuild,mydeps[1])
			if (retval): return retval
		return merge(settings["CATEGORY"],settings["PF"],settings["D"],settings["BUILDDIR"]+"/build-info",myroot)
	elif mydo=="unmerge": 
		return unmerge(settings["CATEGORY"],settings["PF"],myroot)
	elif mydo=="package":
		retval=spawn("/usr/sbin/ebuild.sh setup fetch")
		if retval:
			return retval
		for x in ["","/"+settings["CATEGORY"],"/All"]:
			if not os.path.exists(settings["PKGDIR"]+x):
				os.makedirs(settings["PKGDIR"]+x)
		pkgloc=settings["PKGDIR"]+"/All/"+settings["PF"]+".tbz2"
		rebuild=0
		if os.path.exists(pkgloc):
			for x in [settings["A"],settings["EBUILD"]]:
				if not os.path.exists(x):
					continue
				if os.path.getmtime(x)>os.path.getmtime(pkgloc):
					rebuild=1
					break
		else:	
			rebuild=1
		if not rebuild:
			print
			print ">>> Package",settings["PF"]+".tbz2 appears to be up-to-date."
			print ">>> To force rebuild, touch",os.path.basename(settings["EBUILD"])
			print
			return 0
		else:
			return spawn("/usr/sbin/ebuild.sh unpack compile install package")
	else:
		print "!!! Please specify a valid command."
		return 1

def isfifo(x):
	mymode=os.lstat(x)[ST_MODE]
	if S_ISLNK(mymode):
		return 0
	return S_ISFIFO(mymode)

expandcache={}

def expandpath(mypath):
	"""The purpose of this function is to resolve the 'real' path on disk, with all
	symlinks resolved except for the basename, since we may be installing a symlink
	and definitely don't want it expanded.  In fact, the file that we want to install
	doesn't need to exist; just the dirname."""
	global expandcache
	split=string.split(mypath,"/")
	join=string.join(split[:-1],"/")
	try:
		return expandcache[join]+'/'+split[-1]
	except:
		pass
	a=getstatusoutput("/bin/readlink -f	'"+join+"'")
	if a[0]!=0:
		#expansion didn't work; probably because the dir didn't exist.  Return original path.
		return mypath 
	else:
		expandcache[join]=a[1]
		return a[1]+"/"+split[-1]

def movefile(src,dest,unlink=1):
	"""moves a file from src to dest, preserving all permissions and attributes."""
	#The next 2 lines avoid writing to the target
	if os.path.islink(dest):
		os.unlink(dest)
	if dest=="/bin/cp":
		getstatusoutput("/bin/mv /bin/cp /bin/cp.old")
		a=getstatusoutput("/bin/cp.old -a "+"'"+src+"' /bin/cp")
		os.unlink("/bin/cp.old")
	elif dest=="/bin/bash":
		a=getstatusoutput("rm /bin/bash; /bin/cp -a "+"'"+src+"' '"+dest+"'")
	else:
		a=getstatusoutput("/bin/mv -f "+"'"+src+"' '"+dest+"'")	
	if a[0]==0:
		return 1
	else:
		return 0

def getmtime(x):
	 return `os.lstat(x)[-2]`

def md5(x):
	return string.upper(fchksum.fmd5t(x)[0])

def pathstrip(x,mystart):
    cpref=os.path.commonprefix([x,mystart])
    return [root+x[len(cpref)+1:],x[len(cpref):]]

def merge(mycat,mypkg,pkgloc,infloc,myroot):
	mylink=dblink(mycat,mypkg,myroot)
	if not mylink.exists():
		mylink.create()
		#shell error code
	mylink.merge(pkgloc,infloc,myroot)
	
def unmerge(cat,pkg,myroot):
	mylink=dblink(cat,pkg,myroot)
	if mylink.exists():
		mylink.unmerge()
	mylink.delete()

def getenv(mykey,dictlist=[]):
	"dictlist contains a list of dictionaries to check *before* the environment"
	dictlist.append(os.environ)
	for x in dictlist:
		if x.has_key(mykey):
			return expand(x[mykey],dictlist)
	return ""

def relparse(myver):
	"converts last version part into three components"
	number=0
	p1=0
	p2=0
	mynewver=string.split(myver,"_")
	if len(mynewver)==2:
		#an endversion
		number=string.atof(mynewver[0])
		match=0
		for x in endversion_keys:
			elen=len(x)
			if mynewver[1][:elen] == x:
				match=1
				p1=endversion[x]
				try:
					p2=string.atof(mynewver[1][elen:])
				except:
					p2=0
				break
		if not match:	
			#normal number or number with letter at end
			divider=len(myver)-1
			if myver[divider:] not in "1234567890":
				#letter at end
				p1=ord(myver[divider:])
				number=string.atof(myver[0:divider])
			else:
				number=string.atof(myver)		
	else:
		#normal number or number with letter at end
		divider=len(myver)-1
		if myver[divider:] not in "1234567890":
			#letter at end
			p1=ord(myver[divider:])
			number=string.atof(myver[0:divider])
		else:
			number=string.atof(myver)  
	return [number,p1,p2]

def revverify(myrev):
	if len(myrev)==0:
		return 0
	if myrev[0]=="r":
		try:
			string.atoi(myrev[1:])
			return 1
		except: 
			pass
	return 0

#returns 1 if valid version string, else 0
# valid string in format: <v1>.<v2>...<vx>[a-z,_{endversion}[vy]]
# ververify doesn't do package rev.

def ververify(myorigval,silent=1):	
	if len(myorigval)==0:
		if not silent:
			print "!!! Name error: package contains empty \"-\" part."
		return 0
	myval=string.split(myorigval,'.')
	if len(myval)==0:
		if not silent:
			print "!!! Name error: empty version string."
		return 0
	#all but the last version must be a numeric
	for x in myval[:-1]:
		if not len(x):
			if not silent:
				print "!!! Name error in",myorigval+": two decimal points in a row"
			return 0
		try:
			foo=string.atoi(x)
		except:
			if not silent:
				print "!!! Name error in",myorigval+": \""+x+"\" is not a valid version component."
			return 0
	if not len(myval[-1]):
			if not silent:
				print "!!! Name error in",myorigval+": two decimal points in a row"
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
		if not silent:
			print "!!! Name error in",myorigval
		return 0
	try:
		foo=string.atoi(ep[0])
	except:
		#this needs to be numeric, i.e. the "1" in "1_alpha"
		if not silent:
			print "!!! Name error in",myorigval+": characters before _ must be numeric"
		return 0
	for mye in endversion_keys:
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
	if not silent:
		print "!!! Name error in",myorigval
	return 0

def isjustname(mypkg):
	myparts=string.split(mypkg,'-')
	for x in myparts:
		if ververify(x):
			return 0
	return 1

def isspecific(mypkg):
	mysplit=string.split(mypkg,"/")
	if len(mysplit)==2:
		if not isjustname(mysplit[1]):
			return 1
	return 0

# This function can be used as a package verification function, i.e.
# "pkgsplit("foo-1.2-1") will return None if foo-1.2-1 isn't a valid
# package (with version) name.  If it is a valid name, pkgsplit will
# return a list containing: [ pkgname, pkgversion(norev), pkgrev ].
# For foo-1.2-1, this list would be [ "foo", "1.2", "1" ].  For 
# Mesa-3.0, this list would be [ "Mesa", "3.0", "0" ].

def pkgsplit(mypkg,silent=1):
	myparts=string.split(mypkg,'-')
	if len(myparts)<2:
		if not silent:
			print "!!! Name error in",mypkg+": missing a version or name part." 
		return None
	for x in myparts:
		if len(x)==0:
			if not silent:
				print "!!! Name error in",mypkg+": empty \"-\" part."
			return None
	if revverify(myparts[-1]):
		if ververify(myparts[-2]):
			if len(myparts)==2:
				return None
			else:
				for x in myparts[:-2]:
					if ververify(x):
						return None
						#names can't have versiony looking parts
				return [string.join(myparts[:-2],"-"),myparts[-2],myparts[-1]]
		else:
			return None

	elif ververify(myparts[-1],silent):
		if len(myparts)==1:
			if not silent:
				print "!!! Name error in",mypkg+": missing name part."
			return None
		else:
			for x in myparts[:-1]:
				if ververify(x):
					if not silent:
						print "!!! Name error in",mypkg+": multiple version parts."
					return None
			return [string.join(myparts[:-1],"-"),myparts[-1],"r0"]
	else:
		return None

def catpkgsplit(mycatpkg,silent=1):
	"""returns [cat, pkgname, version, rev ]"""
	mysplit=string.split(mycatpkg,"/")
	if len(mysplit)!=2:
		if not silent:
			print "!!! Name error in",mycatpkg+": category or package part missing."
		return None
	mysplit2=pkgsplit(mysplit[1],silent)
	if mysplit2==None:
		return None
	return [mysplit[0],mysplit2[0],mysplit2[1],mysplit2[2]]

# vercmp:
# This takes two version strings and returns an integer to tell you whether
# the versions are the same, val1>val2 or val2>val1.

def vercmp(val1,val2):
	# consider 1_p2 vc 1.1
	# after expansion will become (1_p2,0) vc (1,1)
	# then 1_p2 is compared with 1 before 0 is compared with 1
	# to solve the bug we need to convert it to (1,0_p2)
	# by splitting _prepart part and adding it back _after_expansion
	val1_prepart = val2_prepart = ''
	if val1.count('_'):
		val1, val1_prepart = val1.split('_', 1)
	if val2.count('_'):
		val2, val2_prepart = val2.split('_', 1)

	# replace '-' by '.'
	# FIXME: Is it needed? can val1/2 contain '-'?
	val1=string.split(val1,'-')
	if len(val1)==2:
		val1[0]=val1[0]+"."+val1[1]
	val2=string.split(val2,'-')
	if len(val2)==2:
		val2[0]=val2[0]+"."+val2[1]

	val1=string.split(val1[0],'.')
	val2=string.split(val2[0],'.')

	#add back decimal point so that .03 does not become "3" !
	for x in range(1,len(val1)):
		if val1[x][0] == '0' :
			val1[x]='.' + val1[x]
	for x in range(1,len(val2)):
		if val2[x][0] == '0' :
			val2[x]='.' + val2[x]

	# extend varion numbers
	if len(val2)<len(val1):
		val2.extend(["0"]*(len(val1)-len(val2)))
	elif len(val1)<len(val2):
		val1.extend(["0"]*(len(val2)-len(val1)))

	# add back _prepart tails
	if val1_prepart:
		val1[-1] += '_' + val1_prepart
	if val2_prepart:
		val2[-1] += '_' + val2_prepart
	#The above code will extend version numbers out so they
	#have the same number of digits.
	for x in range(0,len(val1)):
		cmp1=relparse(val1[x])
		cmp2=relparse(val2[x])
		for y in range(0,3):
			myret=cmp1[y]-cmp2[y]
			if myret != 0:
				return myret
	return 0


def pkgcmp(pkg1,pkg2):
	"""if returnval is less than zero, then pkg2 is newer than pkg2, zero if equal and positive if older."""
	mycmp=vercmp(pkg1[1],pkg2[1])
	if mycmp>0:
		return 1
	if mycmp<0:
		return -1
	r1=string.atoi(pkg1[2][1:])
	r2=string.atoi(pkg2[2][1:])
	if r1>r2:
		return 1
	if r2>r1:
		return -1
	return 0

def dep_parenreduce(mysplit,mypos=0):
	"Accepts a list of strings, and converts '(' and ')' surrounded items to sub-lists"
	while (mypos<len(mysplit)): 
		if (mysplit[mypos]=="("):
			firstpos=mypos
			mypos=mypos+1
			while (mypos<len(mysplit)):
				if mysplit[mypos]==")":
					mysplit[firstpos:mypos+1]=[mysplit[firstpos+1:mypos]]
					mypos=firstpos
					break
				elif mysplit[mypos]=="(":
					#recurse
					mysplit=dep_parenreduce(mysplit,mypos)
				mypos=mypos+1
		mypos=mypos+1
	return mysplit

def dep_opconvert(mysplit,myuse):
	"Does dependency operator conversion, such as moving '||' inside a sub-list, etc."
	mypos=0
	while mypos<len(mysplit):
		if type(mysplit[mypos])==types.ListType:
			mysplit[mypos]=dep_opconvert(mysplit[mypos],myuse)
		elif mysplit[mypos]==")":
			#mismatched paren, error
			return None
		elif mysplit[mypos]=="||":
			if (mypos+1)<len(mysplit):
				if type(mysplit[mypos+1])!=types.ListType:
					# || must be followed by paren'd list
					return None
				else:
					mynew=dep_opconvert(mysplit[mypos+1],myuse)
					mysplit[mypos+1]=mynew
					mysplit[mypos+1][0:0]=["||"]
					del mysplit[mypos]
			else:
				#don't end a depstring with || :)
				return None
		elif mysplit[mypos][-1]=="?":
			#uses clause, i.e "gnome? ( foo bar )"
			if (mysplit[mypos][:-1]) in myuse:
				#if the package is installed, just delete the conditional
				del mysplit[mypos]
			else:
				#the package isn't installed, delete conditional and next item
				del mysplit[mypos]
				del mysplit[mypos]
				#we don't want to move to the next item, so we perform a quick hack
				mypos=mypos-1
		mypos=mypos+1
	return mysplit

def dep_eval(deplist):
	if len(deplist)==0:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if type(x)==types.ListType:
				if dep_eval(x)==1:
					return 1
			elif x==1:
				return 1
		return 0
	else:
		for x in deplist:
			if type(x)==types.ListType:
				if dep_eval(x)==0:
					return 0
			elif x==0 or x==2:
				return 0
		return 1

def dep_zapdeps(unreduced,reduced):
	"""Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies."""
	if unreduced[0]=="||":
		if dep_eval(reduced):
			#deps satisfied, return None
			return None
		else:
			return unreduced
	else:
		if dep_eval(reduced):
			#deps satisfied, return None
			return None
		else:
			returnme=[]
			x=0
			while x<len(reduced):
				if type(reduced[x])==types.ListType:
					myresult=dep_zapdeps(unreduced[x],reduced[x])
					if myresult:
						returnme.append(myresult)
				else:
					if reduced[x]==0:
						returnme.append(unreduced[x])
				x=x+1
			return returnme

def dep_listcleanup(deplist):
	"remove unnecessary clutter from deplists.  Remove multiple list levels, empty lists"
	newlist=[]
	if (len(deplist)==1):
		#remove multiple-depth lists
		if (type(deplist[0])==types.ListType):
			for x in deplist[0]:
				if type(x)==types.ListType:
					if len(x)!=0:
						newlist.append(dep_listcleanup(x))
				else:
					newlist.append(x)
		else:
			#unembed single nodes
			newlist.append(deplist[0])
	else:
		for x in deplist:
			if type(x)==types.ListType:
				if len(x)==1:
					newlist.append(x[0])
				elif len(x)!=0:
					newlist=newlist+dep_listcleanup(x)
			else:
				newlist.append(x)
	return newlist
	
def dep_frontend(mytype,myebuild,depstring):
	"""ebuild frontend for dependency system"""
	
	if ebuild_initialized==0:
		ebuild_init()
	if depstring=="":
		print ">>> No",mytype,"dependencies."
		return 0
	if mytype=="build":
		myparse=localtree.depcheck(depstring)
	elif mytype=="runtime":
		myparse=roottree.depcheck(depstring)
	else:
		print "!!! Error: dependency type",mytype,"not recognized.  Exiting."
		return 1
	if myparse[0]==0:
		#error
		print '!!! '+mytype+' dependency error:',myparse[1]
		return 1
	elif myparse[1]==[]:
		print '>>> '+mytype+' dependencies OK ;)'
		return 0
	else:
		# don't take blocking deps into account when issuing a command through ebuild
		# blocking packages should only be warned about and prevent merging through
		# emerge
		for x in myparse[1]:
			if x[0]=="!":
				continue
			else:
				# there were deps that need resolving that are not of the ! dep type
				print '!!! Some '+mytype+' dependencies must be satisfied first.'
				print '!!! To view the dependency list, type "emerge --pretend',myebuild+'".'
				return 1
		print '>>> '+mytype+' dependencies OK ;)'
		return 0

# gets virtual package settings
def getvirtuals(myroot):
	if (not profiledir) or (not os.path.exists(profiledir+"/virtuals")):
		print ">>>",os.path.normpath(myroot+"/etc/make.profile/virtuals"),"does not exist.  Continuing anyway..."
		return {}
	myfile=open(profiledir+"/virtuals")
	mylines=myfile.readlines()
	myvirts={}
	for x in mylines:
		mysplit=string.split(x)
		if len(mysplit)!=2:
			continue
		myvirts[mysplit[0]]=mysplit[1]
	return myvirts

class packagetree:
	def __init__(self,virtual,clone=None):
		if clone:
			self.tree=clone.tree.copy()
			self.populated=clone.populated
			self.virtual=clone.virtual
		else:
			self.tree={}
			self.populated=0
			self.virtual=virtual
	
	def populate(self):
		"populates the tree with values"
		populated=1
		pass

	def zap(self,mycatpkg):
		"remove a catpkg from the deptree"
		cps=catpkgsplit(mycatpkg,0)
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			return
		x=0
		while x<len(self.tree[mykey]):
			if self.tree[mykey][x][0]==mycatpkg:
				del self.tree[mykey][x]
			x=x+1
		if len(self.tree[mykey])==0:
			del self.tree[mykey]

	def inject(self,mycatpkg):
		"add a catpkg to the deptree"
		cps=catpkgsplit(mycatpkg,0)
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			self.tree[mykey]=[]
		self.tree[mykey].append([mycatpkg,cps])
	
	def resolve_key(self,mykey):
		"generates new key, taking into account virtual keys"
		if not self.tree.has_key(mykey):
			if self.virtual:
				if self.virtual.has_key(mykey):
					return self.virtual[mykey]
		return mykey

	def exists_specific(self,myspec):
		if not self.populated:
			self.populate()
		myspec=self.resolve_specific(myspec)
		if not myspec:
			return None
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=cps[0]+"/"+cps[1]
		if self.tree.has_key(mykey):
			for x in self.tree[mykey]:
				if x[0]==myspec: 
					return 1
		return 0

	def exists_specific_cat(self,myspec):
		if not self.populated:
			self.populate()
		myspec=self.resolve_specific(myspec)
		if not myspec:
			return None
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=cps[0]+"/"+cps[1]
		if self.tree.has_key(mykey):
			return 1
		return 0

	def resolve_specific(self,myspec):
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=self.resolve_key(cps[0]+"/"+cps[1])
		mykey=mykey+"-"+cps[2]
		if cps[3]!="r0":
			mykey=mykey+"-"+cps[3]
		return mykey
	
	def hasnode(self,mykey):
		if not self.populated:
			self.populate()
		if self.tree.has_key(self.resolve_key(mykey)):
			return 1
		return 0
	
	def getallnodes(self):
		"returns a list of all keys in our tree"
		if not self.populated:
			self.populate()
		return self.tree.keys()

	def getnode(self,nodename):
		if not self.populated:
			self.populate()
		nodename=self.resolve_key(nodename)
		if not nodename:
			return []
		if not self.tree.has_key(nodename):
			return []
		return self.tree[nodename]
	
	def depcheck(self,depstring):
		"""evaluates a dependency string and returns a 2-node result list
		[1, None] = ok, no dependencies
		[1, ["x11-base/foobar","sys-apps/oni"] = dependencies must be satisfied
		[0, * ] = parse error
		"""
		if not self.populated:
			self.populate()
		myusesplit=string.split(settings["USE"])
		mysplit=string.split(depstring)
		#convert parenthesis to sublists
		mysplit=dep_parenreduce(mysplit)
		#mysplit can't be None here, so we don't need to check
		mysplit=dep_opconvert(mysplit,myusesplit)
		#if mysplit==None, then we have a parse error (paren mismatch or misplaced ||)
		#up until here, we haven't needed to look at the database tree
		
		if mysplit==None:
			return [0,"Parse Error (parenthesis mismatch or || abuse?)"]
		elif mysplit==[]:
			#dependencies were reduced to nothing
			return [1,[]]
		mysplit2=mysplit[:]
		mysplit2=self.dep_wordreduce(mysplit2)
		if mysplit2==None:
			return [0,"Invalid token"]
		myeval=dep_eval(mysplit2)
		if myeval:
			return [1,[]]
		else:
			mylist=dep_listcleanup(dep_zapdeps(mysplit,mysplit2))
			mydict={}
			for x in mylist:
				mydict[x]=1
			return [1,mydict.keys()]

	def dep_wordreduce(self,mydeplist):
		"""Calls dep_depreduce() on all the items in the deplist"""
		mypos=0
		deplist=mydeplist[:]
		while mypos<len(deplist):
			if type(deplist[mypos])==types.ListType:
				#recurse
				deplist[mypos]=self.dep_wordreduce(deplist[mypos])
			else:
				if deplist[mypos]=="||":
					pass
				else:
					mydep=self.dep_depreduce(deplist[mypos])
					if mydep!=None:
						deplist[mypos]=mydep
					else:
						#encountered invalid string
						return None
			mypos=mypos+1
		return deplist
	
	def dep_depreduce(self,mypkgdep):
		if mypkgdep[0]=="!":
			# !cat/pkg-v
			mybestmatch=self.dep_bestmatch(mypkgdep[1:])
			if mybestmatch:
				return 0
			else:
				return 1
		elif mypkgdep[0]=="=":
			# =cat/pkg-v
			if mypkgdep[-1]=="*":
				if not isspecific(mypkgdep[1:-1]):
					return None
				mycatpkg=catpkgsplit(mypkgdep[1:-1])
				try:
					mynewver=mycatpkg[2]
					mynewsplit=string.split(mycatpkg[2],'.')
					mynewsplit[-1]=`int(mynewsplit[-1])+1`
				except:
					return None
				cmp1=mycatpkg[1:]
				cmp2=[mycatpkg[1],string.join(mynewsplit,"."),"r0"]
				for x in self.getnode(mycatpkg[0]+"/"+mycatpkg[1]):
					if (pkgcmp(x[1][1:],cmp1)>=0) and (pkgcmp(x[1][1:],cmp2)<0):
						return 1
			else:
				return self.exists_specific(mypkgdep[1:])
		elif (mypkgdep[0]=="<") or (mypkgdep[0]==">"):
			# >=cat/pkg-v or <=,>,<
			if mypkgdep[1]=="=":
					cmpstr=mypkgdep[0:2]
					cpv=mypkgdep[2:]
			else:
					cmpstr=mypkgdep[0]
					cpv=mypkgdep[1:]
			if not isspecific(cpv):
				return None
			mycatpkg=catpkgsplit(cpv,0)
			if not mycatpkg:
				#parse error
				return 0
			mykey=mycatpkg[0]+"/"+mycatpkg[1]
			if self.hasnode(mykey):
				for x in self.getnode(mykey):
					if eval("pkgcmp(x[1][1:],mycatpkg[1:])"+cmpstr+"0"):
						return 1
			return 0
		elif mypkgdep[0]=="~":
			if not isspecific(mypkgdep[1:]):
				return None
			cp=catpkgsplit(mypkgdep[1:])
			if not cp:
				return 0
			mykey=cp[0]+"/"+cp[1]
			if self.hasnode(mykey):
				for x in self.getnode(mykey):
					if pkgcmp(x[1][1:],cp[1:])>=0 and (x[1][2]==cp[2]):
						return 1
			return 0
		if not isspecific(mypkgdep):
			# cat/pkg 
			if self.hasnode(mypkgdep):
				return 1
			else:
				return 0
		else:
			return None

	def dep_pkgcat(self,mypkgdep):
		"""tries to find the category of a package dependency that has been provided without
		a category, if it couldn't be found the initial argument in returned"""
		# check if a slash has been provided to
		# seperate the category from the application
		# if not, seperate the deps chars and try
		# to find a matching category
		if not '/' in mypkgdep:
			re_deps=re.compile("^([><=~]+)(.+)$")
			mypkgdep_parts=re_deps.findall(mypkgdep)
			# set default values
			mypkgdep_deps=""
			mypkgdep_package=mypkgdep
			mypkgdep_packagename=mypkgdep
			# try to get the deps chars and package name isolated
			if mypkgdep_parts:
				mypkgdep_deps=mypkgdep_parts[0][0]
				mypkgdep_package=mypkgdep_parts[0][1]
				mypkgdep_package_parts=pkgsplit(mypkgdep_package)
				if mypkgdep_package_parts:
					mypkgdep_packagename=mypkgdep_package_parts[0]
			# try to contructs a full packagename with category
			mypkgdep_withcat = ""
			for cat in categories:
				if self.hasnode(cat+"/"+mypkgdep_packagename):
					mypkgdep_withcat = mypkgdep_deps+cat+"/"+mypkgdep_package
					break
			# if it succeeded, assign it as a result
			if mypkgdep_withcat:
				mypkgdep = mypkgdep_withcat
		return mypkgdep

	def dep_bestmatch(self,mypkgdep):
		"""
		returns best match for mypkgdep in the tree.  Accepts
		a single depstring, such as ">foo/bar-1.0" and finds
		the most recent version of foo/bar that satisfies the
		dependency and returns it, i.e: "foo/bar-1.3".  Works
		for >,<,>=,<=,=,and general deps.  Don't call with a !
		dep, since there is no good match for a ! dep.
		"""
		mypkgdep=self.dep_pkgcat(mypkgdep)

		if (mypkgdep[0]=="="):
			if mypkgdep[-1]=="*":
				if not isspecific(mypkgdep[1:-1]):
					return ""
				mycatpkg=catpkgsplit(mypkgdep[1:-1])
				try:
					mynewver=mycatpkg[2]
					mynewsplit=string.split(mycatpkg[2],'.')
					mynewsplit[-1]=`int(mynewsplit[-1])+1`
				except:
					return "" 
				mynodes=[]
				cmp1=mycatpkg[1:]
				cmp2=[mycatpkg[1],string.join(mynewsplit,"."),"r0"]
				for x in self.getnode(mycatpkg[0]+"/"+mycatpkg[1]):
					if (pkgcmp(x[1][1:],cmp1)>=0) and (pkgcmp(x[1][1:],cmp2)<0):
						mynodes.append(x)
				if len(mynodes)==0:
					return ""
				bestmatch=mynodes[0]
				for x in mynodes[1:]:
					if pkgcmp(x[1][1:],bestmatch[1][1:])>0:
						bestmatch=x
				return bestmatch[0]		
			else:
				if self.exists_specific(mypkgdep[1:]):
					return mypkgdep[1:]
				else:
					return ""
		elif (mypkgdep[0]==">") or (mypkgdep[0]=="<"):
			if mypkgdep[1]=="=":
				cmpstr=mypkgdep[0:2]
				cpv=mypkgdep[2:]
			else:
				cmpstr=mypkgdep[0]
				cpv=mypkgdep[1:]
			if not isspecific(cpv):
				return ""
			mycatpkg=catpkgsplit(cpv)
			if not mycatpkg:
				return ""
			mykey=mycatpkg[0]+"/"+mycatpkg[1]
			if not self.hasnode(mykey):
				return ""
			mynodes=[]
			for x in self.getnode(mykey):
				if eval("pkgcmp(x[1][1:],mycatpkg[1:])"+cmpstr+"0"):
					mynodes.append(x)
			#now we have a list of all nodes that qualify
			if len(mynodes)==0:
				return ""
			bestmatch=mynodes[0]
			for x in mynodes[1:]:
				if pkgcmp(x[1][1:],bestmatch[1][1:])>0:
					bestmatch=x
			return bestmatch[0]		
		elif (mypkgdep[0]=="~"):
			mypkg=mypkgdep[1:]
			if not isspecific(mypkg):
				return ""
			mycp=catpkgsplit(mypkg)
			if not mycp:
				return ""
			mykey=mycp[0]+"/"+mycp[1]
			if not self.hasnode(mykey):
				return ""
			myrev=-1
			for x in self.getnode(mykey):
				if mycp[2]!=x[1][2]:
					continue
				if x[1][3][1:]>myrev:
					myrev=x[1][3][1:]
					mymatch=x[0]
			if myrev==-1:
				return ""
			else:
				return mymatch
		elif not isspecific(mypkgdep):
			if not self.hasnode(mypkgdep):
				return ""
			mynodes=self.getnode(mypkgdep)[:]
			if len(mynodes)==0:
				return ""
			bestmatch=mynodes[0]
			for x in mynodes[1:]:
				if pkgcmp(x[1][1:],bestmatch[1][1:])>0:
					bestmatch=x
			return bestmatch[0]

	def dep_nomatch(self,mypkgdep):
		"""dep_nomatch() has a very specific purpose.  You pass it a dep, like =sys-apps/foo-1.0.
		Then, it scans the sys-apps/foo category and returns a list of sys-apps/foo packages that
		*don't* match.  This method is used to clean the portagetree using entries in the 
		make.profile/packages and profiles/package.mask files.
		It is only intended to process specific deps, but should be robust enough to pass any type
		of string to it and have it not die."""
		mypkgdep=self.dep_pkgcat(mypkgdep)

		returnme=[]
		if (mypkgdep[0]=="="):
			if mypkgdep[-1]=="*":
				if not isspecific(mypkgdep[1:-1]):
					return []
				mycatpkg=catpkgsplit(mypkgdep[1:-1])
				try:
					mynewver=mycatpkg[2]
					mynewsplit=string.split(mycatpkg[2],'.')
					mynewsplit[-1]=`int(mynewsplit[-1])+1`
				except:
					return [] 
				mynodes=[]
				cmp1=mycatpkg[1:]
				cmp2=[mycatpkg[1],string.join(mynewsplit,"."),"r0"]
				for x in self.getnode(mycatpkg[0]+"/"+mycatpkg[1]):
					if not ((pkgcmp(x[1][1:],cmp1)>=0) and (pkgcmp(x[1][1:],cmp2)<0)):
						mynodes.append(x[0])
				return mynodes
			else:
				mycp=catpkgsplit(mypkgdep[1:],1)
				if not mycp:
					#not a specific pkg, or parse error.  keep silent
					return []
				mykey=mycp[0]+"/"+mycp[1]
				if not self.tree.has_key(mykey):
					return []
				x=0
				while x<len(self.tree[mykey]):
					if self.tree[mykey][x][0]!=mypkgdep[1:]:
						returnme.append(self.tree[mykey][x][0])
					x=x+1
		elif (mypkgdep[0]==">") or (mypkgdep[0]=="<"):
			if mypkgdep[1]=="=":
				cmpstr=mypkgdep[0:2]
				cpv=mypkgdep[2:]
			else:
				cmpstr=mypkgdep[0]
				cpv=mypkgdep[1:]
			if not isspecific(cpv):
				return []
			mycatpkg=catpkgsplit(cpv,1)
			if mycatpkg==None:
				#parse error
				return []
			mykey=mycatpkg[0]+"/"+mycatpkg[1]
			if not self.hasnode(mykey):
				return []
			for x in self.getnode(mykey):
				if not eval("pkgcmp(x[1][1:],mycatpkg[1:])"+cmpstr+"0"):
					returnme.append(x[0])
		elif mypkgdep[0]=="~":
			#"~" implies a "bestmatch"
			mycp=catpkgsplit(mypkgdep[1:],1)
			if not mycp:
				return []
			mykey=mycp[0]+"/"+mycp[1]
			if not self.tree.has_key(mykey):
				return []
			mymatch=self.dep_bestmatch(mypkgdep)
			if not mymatch:
				for x in self.tree[mykey]:
					returnme.append(x[0])
			else:
				x=0
				while x<len(self.tree[mykey]):
					if self.tree[mykey][x][0]!=mymatch:
						returnme.append(self.tree[mykey][x][0])
					x=x+1
			#end of ~ section
		else:
			return []
		return returnme

	def dep_match(self,mypkgdep):
		"""
		returns a list of all matches for mypkgdep in the tree.  Accepts
		a single depstring, such as ">foo/bar-1.0" and finds
		all the versions of foo/bar that satisfy the
		dependency and returns them, i.e: ["foo/bar-1.3"].  Works
		for >,<,>=,<=,=,and general deps.  Don't call with a !
		dep, since there is no good match for a ! dep.
		"""
		mypkgdep=self.dep_pkgcat(mypkgdep)

		if (mypkgdep[0]=="="):
			if self.exists_specific(mypkgdep[1:]):
				return [mypkgdep[1:]]
			else:
				return []
		elif (mypkgdep[0]==">") or (mypkgdep[0]=="<"):
			if mypkgdep[1]=="=":
				cmpstr=mypkgdep[0:2]
				cpv=mypkgdep[2:]
			else:
				cmpstr=mypkgdep[0]
				cpv=mypkgdep[1:]
			if not isspecific(cpv):
				return []
			mycatpkg=catpkgsplit(cpv,0)
			if mycatpkg==None:
				#parse error
				return []
			mykey=mycatpkg[0]+"/"+mycatpkg[1]
			if not self.hasnode(mykey):
				return []
			mynodes=[]
			for x in self.getnode(mykey):
				if eval("pkgcmp(x[1][1:],mycatpkg[1:])"+cmpstr+"0"):
					mynodes.append(x[0])
			#now we have a list of all nodes that qualify
			#since we want all nodes that match, return this list
			return mynodes
		elif mypkgdep[0]=="~":
			#"~" implies a "bestmatch"
			return [self.dep_bestmatch(mypkgdep)]
		elif not isspecific(mypkgdep):
			if not self.hasnode(mypkgdep):
				return [] 
			mynodes=[]
			for x in self.getnode(mypkgdep)[:]:
				mynodes.append(x[0])
			return mynodes

class vartree(packagetree):
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self,root="/",virtual=None,clone=None):
		if clone:
			self.root=clone.root
		else:
			self.root=root
		packagetree.__init__(self,virtual,clone)
	def populate(self):
		"populates the local tree (/var/db/pkg)"
		prevmask=os.umask(0)
		if not os.path.isdir(self.root+"var"):
			os.mkdir(self.root+"var",0755)
		if not os.path.isdir(self.root+"var/db"):
			os.mkdir(self.root+"var/db",0755)
		if not os.path.isdir(self.root+"var/db/pkg"):
			os.mkdir(self.root+"var/db/pkg",0755)
		os.umask(prevmask)
		dbdir=self.root+"var/db/pkg"
		origdir=getmycwd()
		os.chdir(dbdir)
		for x in os.listdir(os.getcwd()):
			if not os.path.isdir(os.getcwd()+"/"+x):
				continue
			for y in os.listdir(os.getcwd()+"/"+x):
				if isjustname(y):
					fullpkg=x+"/"+y+"-1.0"
				else:
					fullpkg=x+"/"+y
				mysplit=catpkgsplit(fullpkg,0)
				if mysplit==None:
					print "!!! Error:",self.root+"var/db/pkg/"+x+"/"+y,"is not a valid database entry, skipping..."
					continue
				mykey=x+"/"+mysplit[1]
				if not self.tree.has_key(mykey):
					self.tree[mykey]=[]
				self.tree[mykey].append([fullpkg,mysplit])
		os.chdir(origdir)
		self.populated=1

class portagetree(packagetree):
	"this tree will scan a portage directory located at root (passed to init)"
	def __init__(self,root="/",virtual=None,clone=None):
		if clone:
			self.root=clone.root
			self.portroot=clone.portroot
		else:
			self.root=root
			self.portroot=settings["PORTDIR"]
		packagetree.__init__(self,virtual)
	def populate(self):
		"populates the port tree"
		origdir=getmycwd()
		os.chdir(self.portroot)
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
					if not self.tree.has_key(mykey):
						self.tree[mykey]=[]
					mysplit=catpkgsplit(fullpkg,0)
					if mysplit==None:
						print "!!! Error:",self.portroot+"/"+x+"/"+y,"is not a valid Portage directory, skipping..."
						continue	
					self.tree[mykey].append([fullpkg,mysplit])
		#self.populated must be set here, otherwise dep_match will cause recursive populate() calls
		self.populated=1
		mylines=grabfile("profiles/package.mask")
		for x in mylines:
			matches=self.dep_match(x)
			if matches:
				for y in matches:
					self.zap(y)
		os.chdir(origdir)
		mylines=grabfile(profiledir+"/packages")
		for x in mylines:
			if x[0]=="*":
				x=x[1:]
			matches=self.dep_nomatch(x)
			for y in matches:
				self.zap(y)

	def getdeps(self,pf):
		"returns list of dependencies, if any"
		if not self.populated:
			self.populate()
		if self.exists_specific(pf):
			mysplit=catpkgsplit(pf)
			if mysplit==None:
				#parse error
				return ""
			mydepfile=self.portroot+"/"+mysplit[0]+"/"+mysplit[1]+"/files/depend-"+string.split(pf,"/")[1]
			if os.path.exists(mydepfile):
				myd=open(mydepfile,"r")
				mydeps=myd.readlines()
				myd.close()
				returnme=""
				for x in mydeps:
					returnme=returnme+" "+x[:-1]
				return returnme
		return ""
	def getname(self,pkgname):
		"returns file location for this particular package"
		if not self.populated:
			self.populate()
		pkgname=self.resolve_specific(pkgname)
		if not pkgname:
			return ""
		mysplit=string.split(pkgname,"/")
		psplit=pkgsplit(mysplit[1])
		return self.portroot+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"

class binarytree(packagetree):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self,root="/",virtual=None,clone=None):
		if clone:
			self.root=clone.root
			self.pkgdir=clone.pkgdir
		else:
			self.root=root
			self.pkgdir=settings["PKGDIR"]
		packagetree.__init__(self,virtual)
	def populate(self):
		"popules the binarytree"
		if (not os.path.isdir(self.pkgdir)):
			return 0
		for mypkg in os.listdir(self.pkgdir+"/All"):
			if mypkg[-5:]!=".tbz2":
				continue
			mytbz2=xpak.tbz2(self.pkgdir+"/All/"+mypkg)
			mycat=mytbz2.getfile("CATEGORY")
			if not mycat:
				#old-style or corrupt package
				continue
			mycat=string.strip(mycat)
			fullpkg=mycat+"/"+mypkg[:-5]
			cps=catpkgsplit(fullpkg,0)
			if cps==None:
				print "!!! Error:",mytbz2,"contains corrupt cat/pkg information, skipping..."
				continue
			mykey=mycat+"/"+cps[1]
			if not self.tree.has_key(mykey):
				self.tree[mykey]=[]
			self.tree[mykey].append([fullpkg,cps])
		self.populated=1
	def getname(self,pkgname):
		"returns file location for this particular package"
		mysplit=string.split(pkgname,"/")
		if len(mysplit)==1:
			return self.pkgdir+"/All/"+self.resolve_specific(pkgname)+".tbz2"
		else:
			return self.pkgdir+"/All/"+mysplit[1]+".tbz2"

class dblink:
	"this class provides an interface to the standard text package database"
	def __init__(self,cat,pkg,myroot):
		"create a dblink object for cat/pkg.  This dblink entry may or may not exist"
		self.cat=cat
		self.pkg=pkg
		self.dbdir=myroot+"/var/db/pkg/"+cat+"/"+pkg
		self.myroot=myroot

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir
	
	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)
	
	def create(self):
		"create the skeleton db directory structure.  No contents, virtuals, provides or anything.  Also will create /var/db/pkg if necessary."
		if not os.path.exists(self.dbdir):
			os.makedirs(self.dbdir)
	
	def delete(self):
		"erase this db entry completely"
		if not os.path.exists(self.dbdir):
			return
		for x in os.listdir(self.dbdir):
			os.unlink(self.dbdir+"/"+x)
		os.rmdir(self.dbdir)
	
	def clearcontents(self):
		if os.path.exists(self.dbdir+"/CONTENTS"):
			os.unlink(self.dbdir+"/CONTENTS")
	
	def getcontents(self):
		if not os.path.exists(self.dbdir+"/CONTENTS"):
			return None
		pkgfiles={}
		myc=open(self.dbdir+"/CONTENTS","r")
		mylines=myc.readlines()
		myc.close()
		for line in mylines:
			mydat=string.split(line)
			# we do this so we can remove from non-root filesystems
			# (use the ROOT var to allow maintenance on other partitions)
			mydat[1]=os.path.normpath(root+mydat[1][1:])
			if mydat[0]=="obj":
				#format: type, mtime, md5sum
				pkgfiles[string.join(mydat[1:-2]," ")]=[mydat[0], mydat[-1], mydat[-2]]
			elif mydat[0]=="dir":
				#format: type
				pkgfiles[string.join(mydat[1:])]=[mydat[0] ]
			elif mydat[0]=="sym":
				#format: type, mtime, dest
				x=len(mydat)-1
				splitter=-1
				while(x>=0):
					if mydat[x]=="->":
						splitter=x
						break
					x=x-1
				if splitter==-1:
					return None
				pkgfiles[string.join(mydat[1:splitter]," ")]=[mydat[0], mydat[-1], string.join(mydat[(splitter+1):-1]," ")]
			elif mydat[0]=="dev":
				#format: type
				pkgfiles[string.join(mydat[1:]," ")]=[mydat[0] ]
			elif mydat[0]=="fif":
				#format: type
				pkgfiles[string.join(mydat[1:]," ")]=[mydat[0]]
			else:
				return None
		return pkgfiles
	
	def unmerge(self,pkgfiles=None):
		if not pkgfiles:
			pkgfiles=self.getcontents()
			if not pkgfiles:
				return
		
		#do prerm script
		a=doebuild(self.dbdir+"/"+self.pkg+".ebuild","prerm",self.myroot)
		if a:
			print "!!! pkg_prerm() script failed; exiting."
			sys.exit(a)

		#we do this so we don't unmerge the ebuild file by mistake
		myebuildfile=os.path.normpath(self.dbdir+"/"+self.pkg+".ebuild")
		if os.path.exists(myebuildfile):
			if pkgfiles.has_key(myebuildfile):
				del pkgfiles[myebuildfile]
				
		mykeys=pkgfiles.keys()
		mykeys.sort()
		mykeys.reverse()
		
		#do some config file management prep
		self.protect=[]
		for x in string.split(settings["CONFIG_PROTECT"]):
			ppath=os.path.normpath(self.myroot+"/"+x)+"/"
			if os.path.isdir(ppath):
				self.protect.append(ppath)
				print ">>> Config file management enabled for",ppath
			
		self.protectmask=[]
		for x in string.split(settings["CONFIG_PROTECT_MASK"]):
			ppath=os.path.normpath(self.myroot+"/"+x)+"/"
			if os.path.isdir(ppath):
				self.protectmask.append(ppath)
			#if it doesn't exist, silently skip it
		
		for obj in mykeys:
			obj=os.path.normpath(obj)
			if not os.path.islink(obj):
				#we skip this if we're dealing with a symlink
				#because os.path.exists() will operate on the
				#link target rather than the link itself.
				if not os.path.exists(obj):
					print "--- !found", pkgfiles[obj][0], obj
					continue
			if (pkgfiles[obj][0] not in ("dir","fif","dev")) and (getmtime(obj) != pkgfiles[obj][1]):
				print "--- !mtime", pkgfiles[obj][0], obj
				continue
			if pkgfiles[obj][0]=="dir":
				if not os.path.isdir(obj):
					print "--- !dir  ","dir", obj
					continue
				if os.listdir(obj):
					print "--- !empty","dir", obj
					continue
				os.rmdir(obj)
				print "<<<       ","dir",obj
			elif pkgfiles[obj][0]=="sym":
				if not os.path.islink(obj):
					print "--- !sym  ","sym", obj
					continue
				mydest=os.readlink(obj)
				if os.path.exists(os.path.normpath(self.myroot+mydest)):
					if mydest != pkgfiles[obj][2]:
						print "--- !destn","sym", obj
						continue
				myppath=""
				for ppath in self.protect:
					epath=expandpath(obj)
					if epath[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if epath[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfg   ","sym",obj
					continue
				os.unlink(obj)
				print "<<<       ","sym",obj
			elif pkgfiles[obj][0]=="obj":
				if not os.path.isfile(obj):
					print "--- !obj  ","obj", obj
					continue
				mymd5=md5(obj)
				if mymd5 != string.upper(pkgfiles[obj][2]):
					print "--- !md5  ","obj", obj
					continue
				myppath=""
				for ppath in self.protect:
					epath=expandpath(obj)
					if epath[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if epath[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfg   ","obj",obj
				else:
					os.unlink(obj)
					print "<<<       ","obj",obj
			elif pkgfiles[obj][0]=="fif":
				if not isfifo(obj):
					print "--- !fif  ","fif", obj
					continue
				myppath=""
				for ppath in self.protect:
					epath=expandpath(obj)
					if epath[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if epath[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfg   ","fif",obj
					continue
				os.unlink(obj)
				print "<<<       ","fif",obj
			elif pkgfiles[obj][0]=="dev":
				print "---       ","dev",obj

		#remove provides
		for mycatpkg in self.getelements("PROVIDE"):
			mycat,mypkg=string.split(mycatpkg,"/")
			tcatpkg=self.cat+"/"+self.pkg
			mylink=dblink(mycat,mypkg,self.myroot)
			if not mylink.exists():
				continue
			myvirts=mylink.getelements("VIRTUAL")
			while tcatpkg in myvirts:
				myvirts.remove(tcatpkg)
			if not myvirts:
				#no more virtuals; cleanup time
				if mylink.isregular():
					#just zap the VIRTUAL file, this is also a normal package
					os.unlink(mylink.dbdir+"/VIRTUAL")
				else:
					#this is a pure virtual package, remove the entire db entry
					mylink.delete()
			else:
				mylink.setelements(myvirts,"VIRTUAL")
		
		#do original postrm
		a=doebuild(self.dbdir+"/"+self.pkg+".ebuild","postrm",self.myroot)
		if a:
			print "!!! pkg_postrm() script failed; exiting."
			sys.exit(a)

	def merge(self,mergeroot,inforoot,myroot,mergestart=None,outfile=None):
		global prevmask	
		#myroot=os.environ["ROOT"]
		#myroot should be set to the ROOT of where to merge to.

		if mergestart==None:
			origdir=getmycwd()
			if not os.path.exists(self.dbdir):
				self.create()
				#open contents file if it isn't already open
			mergestart=mergeroot
			print ">>> Updating mtimes..."
			#before merging, it's *very important* to touch all the files !!!
			os.system("(cd "+mergeroot+"; for x in `find`; do  touch -c $x 2>/dev/null; done)")
			print ">>> Merging",self.cat+"/"+self.pkg,"to",myroot
			
		
			#get old contents info for later unmerging
			oldcontents=self.getcontents()
			a=doebuild(inforoot+"/"+self.pkg+".ebuild","preinst",root)
			if a:
				print "!!! pkg_preinst() script failed; exiting."
				sys.exit(a)
			outfile=open(inforoot+"/CONTENTS","w")
		
			#prep for config file management
			self.protect=[]
			for x in string.split(settings["CONFIG_PROTECT"]):
				ppath=os.path.normpath(myroot+"/"+x)+"/"
				if os.path.isdir(ppath):
					self.protect.append(ppath)
			# Don't warn about a missing config file path
			#	else:
			#		print "!!!",ppath,"not found.  Config file management disabled for this directory."
			self.protectmask=[]
			for x in string.split(settings["CONFIG_PROTECT_MASK"]):
				ppath=os.path.normpath(myroot+"/"+x)+"/"
				if os.path.isdir(ppath):
					self.protectmask.append(ppath)
				#if it doesn't exist, silently skip it
				#back up umask, save old one in prevmask (global)
				prevmask=os.umask(0)
		
		mergestart=mergestart
		os.chdir(mergestart)
		cpref=os.path.commonprefix([mergeroot,mergestart])
		relstart=mergestart[len(cpref):]
		myfiles=os.listdir(mergestart)
		
		for x in myfiles:
			relfile=relstart+"/"+x
			rootfile=os.path.normpath(myroot+relfile)
			#symbolic link
			if os.path.islink(x):
				myto=os.readlink(x)
				if os.path.exists(rootfile):
					if (not os.path.islink(rootfile)) and (os.path.isdir(rootfile)):
						print "!!!",rootfile,"->",myto
					else:
						os.unlink(rootfile)
				try:
					os.symlink(myto,rootfile)
					print ">>>",rootfile,"->",myto
					outfile.write("sym "+expandpath(relfile)+" -> "+myto+" "+getmtime(rootfile)+"\n")
				except:
					print "!!!",rootfile,"->",myto
			#directory
			elif os.path.isdir(x):
				mystat=os.stat(x)
				if os.path.exists(rootfile):
					if os.path.islink(rootfile) and os.path.isdir(rootfile):
						#a symlink to an existing directory will work for us; keep it:
						print "---",rootfile+"/"
					elif os.path.isdir(rootfile):
						#a normal directory will work too
						print "---",rootfile+"/"
					else:
						#a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						movefile(rootfile,rootfile+".backup")
						print "bak",rootfile,rootfile+".backup"
						#now create our directory
						os.mkdir(rootfile)
						os.chmod(rootfile,mystat[0])
						os.chown(rootfile,mystat[4],mystat[5])
						print ">>>",rootfile+"/"
				else:				
					os.mkdir(rootfile)
					os.chmod(rootfile,mystat[0])
					os.chown(rootfile,mystat[4],mystat[5])
					print ">>>",rootfile+"/"
				outfile.write("dir "+expandpath(relfile)+"\n")
				#enter directory, recurse
				os.chdir(x)
				self.merge(mergeroot,inforoot,myroot,mergestart+"/"+x,outfile)
				#return to original path
				os.chdir(mergestart)
			#regular file
			elif os.path.isfile(x):
				mymd5=md5(x)
				myppath=""
				rootdir=os.path.dirname(rootfile)
				for ppath in self.protect:
					#the expandpath() means that we will be expanding rootpath first (resolving dir symlinks)
					#before matching against a protection path.
					if expandpath(rootfile)[0:len(ppath)]==ppath:
						myppath=ppath
						#config file management
						for pmpath in self.protectmask:
							#again, dir symlinks are expanded
							if expandpath(rootfile)[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								myppath=""
								break
						if not myppath:
							break	
				moveme=1
				if os.path.exists(rootfile):
					if os.path.islink(rootfile):
						#this is how to cleverly avoid accidentally processing symlinks as dirs or regular files
						pass
					elif os.path.isdir(rootfile):
						#directories do *not* get replaced by files
						moveme=0
						print "!!!",rootfile
					elif os.path.isfile(rootfile):
						#replacing a regular file: we need to do some cfg file management here
						#let's find the right filename for rootfile
						if myppath!="":
							#if the md5's *do* match, just copy it over (fall through to movefile(), below)
							if mymd5!=md5(rootfile):
								pnum=-1
								pmatch=os.path.basename(rootfile)
								#format:
								# ._cfg0000_foo
								# 0123456789012
								mypfile=""
								for pfile in os.listdir(rootdir):
									if pfile[0:5]!="._cfg":
										continue
									if pfile[10:]!=pmatch:
										continue
									try:
										newpnum=string.atoi(pfile[5:9])
										if newpnum>pnum:
											pnum=newpnum
										mypfile=pfile
									except:
										continue
								pnum=pnum+1
								#this next line specifies the normal default rootfile (the next available ._cfgxxxx_ slot
								rootfile=os.path.normpath(rootdir+"/._cfg"+string.zfill(pnum,4)+"_"+pmatch)
								#but, we can override rootfile in a special case:
								#if the last ._cfgxxxx_foo file's md5 matches:
								if mypfile:
									pmd5=md5(rootdir+"/"+mypfile)
									if mymd5==pmd5:
										rootfile=(rootdir+"/"+mypfile)
										#then overwrite the last ._cfgxxxx_foo file rather than creating a new one
										#(for cleanliness)
				else:
					#this is mainly for zapping symbolic links that are dead
					try:
						os.unlink(rootfile)
					except OSError:
						pass
					
					if myppath:
						unlinkme=[]
						pmatch=os.path.basename(rootfile)
						mypfile=""
						for pfile in os.listdir(rootdir):
							if pfile[0:5]!="._cfg":
								continue
							if pfile[10:]!=pmatch:
								continue
							unlinkme.append(rootdir+"/"+pfile)
						for ufile in unlinkme:
							if os.path.isfile(ufile) and not os.path.islink(ufile):
								os.unlink(ufile)
								print "<<<",ufile
				if moveme:
					#moveme=0 is used to avoid copying on top of directories
					if movefile(x,rootfile):
						zing=">>>"
						outfile.write("obj "+expandpath(relfile)+" "+mymd5+" "+getmtime(rootfile)+"\n")
					else:
						zing="!!!"
					print zing,rootfile
			elif isfifo(x):
				#fifo
				zing="!!!"
				if not os.path.exists(rootfile):	
					if movefile(x,rootfile):
						zing=">>>"
				elif isfifo(rootfile):
					os.unlink(rootfile)
					if movefile(x,rootfile):
						zing=">>>"
				print zing+" "+rootfile
				outfile.write("fif "+expandpath(relfile)+"\n")
			else:
				#device nodes, the only other possibility
				if movefile(x,rootfile):
					zing=">>>"
				else:
					zing="!!!"
				print zing+" "+rootfile
				outfile.write("dev "+expandpath(relfile)+"\n")
		if mergestart==mergeroot:
			#restore umask
			os.umask(prevmask)
			#if we opened it, close it	
			outfile.close()
			if (oldcontents):
				print ">>> Safely unmerging already-installed instance..."
				self.unmerge(oldcontents)
				print ">>> original instance of package unmerged safely."	

			os.chdir(inforoot)
			for x in os.listdir("."):
				self.copyfile(x)
			
			#create virtual links
			for mycatpkg in self.getelements("PROVIDE"):
				mycat,mypkg=string.split(mycatpkg,"/")
				mylink=dblink(mycat,mypkg,self.myroot)
				#this will create the link if it doesn't exist
				mylink.create()
				myvirts=mylink.getelements("VIRTUAL")
				if not mycat+"/"+mypkg in myvirts:
					myvirts.append(self.cat+"/"+self.pkg)
					mylink.setelements(myvirts,"VIRTUAL")

			#do postinst script
			a=doebuild(self.dbdir+"/"+self.pkg+".ebuild","postinst",root)
			if a:
				print "!!! pkg_postinst() script failed; exiting."
				sys.exit(a)
			#update environment settings, library paths
			env_update()	
			print ">>>",self.cat+"/"+self.pkg,"merged."
			os.chdir(origdir)
	
	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		myfile=open(self.dbdir+"/"+name,"r")
		mydata=string.split(myfile.read())
		myfile.close()
		return string.join(mydata," ")
	
	def copyfile(self,fname):
		if not os.path.exists(self.dbdir):
			self.create()
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))
	
	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		myfile=open(self.dbdir+"/"+fname,"r")
		mydata=myfile.read()
		myfile.close()
		return mydata

	def setfile(self,fname,data):
		if not os.path.exists(self.dbdir):
			self.create()
		myfile=open(self.dbdir+"/"+fname,"w")
		myfile.write(data)
		myfile.close()
		
	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return [] 
		myelement=open(self.dbdir+"/"+ename,"r")
		mylines=myelement.readlines()
		myreturn=[]
		for x in mylines:
			for y in string.split(x[:-1]):
				myreturn.append(y)
		myelement.close()
		return myreturn
	
	def setelements(self,mylist,ename):
		if not os.path.exists(self.dbdir):
			self.create()
		myelement=open(self.dbdir+"/"+ename,"w")
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()
	
	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(self.dbdir+"/CATEGORY")

def depgrab(myfilename,depmark):
	"""
	Will grab the dependency string from an ebuild file, using
	depmark as a marker (normally DEPEND or RDEPEND)
	"""
	depstring=""
	myfile=open(myfilename,"r")
	mylines=myfile.readlines()
	myfile.close()
	pos=0
	while (pos<len(mylines)):
		if mylines[pos][0:len(depmark)+1]==depmark+"=":
			depstart=string.split(mylines[pos][len(depmark):],'"')
			if len(depstart)==3:
				depstring=depstart[1]
				return string.join(string.split(depstring)," ")
			elif len(depstart)==2:
				depstring=depstart[1]+" "
				pos=pos+1
				while 1:
					mysplit=string.split(mylines[pos],'"')
					depstring=depstring+mysplit[0]+" "
					if len(mysplit)>1:
						return string.join(string.split(depstring)," ")
					pos=pos+1
			elif len(depstart)==1:
				depstring=depstring+mylines[pos][len(depmark)+1:]
				break
			else:
				break
		else:
			pos=pos+1
	return string.join(string.split(depstring)," ")

def cleanup_pkgmerge(mypkg,origdir):
	shutil.rmtree(settings["PKG_TMPDIR"]+"/"+mypkg)
	os.chdir(origdir)

def pkgmerge(mytbz2,myroot):
	"""will merge a .tbz2 file, returning a list of runtime dependencies that must be
		satisfied, or None if there was a merge error.  This code assumes the package
		exists."""
	if mytbz2[-5:]!=".tbz2":
		print "!!! Not a .tbz2 file"
		return None
	mypkg=os.path.basename(mytbz2)[:-5]
	xptbz2=xpak.tbz2(mytbz2)
	pkginfo={}
	mycat=xptbz2.getfile("CATEGORY")
	if not mycat:
		print "!!! CATEGORY info missing from info chunk, aborting..."
		return None
	mycat=mycat.strip()
	mycatpkg=mycat+"/"+mypkg

	tmploc=settings["PKG_TMPDIR"]
	pkgloc=tmploc+"/"+mypkg+"/bin"
	infloc=tmploc+"/"+mypkg+"/inf"
	if os.path.exists(tmploc+"/"+mypkg):
		shutil.rmtree(tmploc+"/"+mypkg,1)
	os.makedirs(pkgloc)
	os.makedirs(infloc)
	print ">>> extracting info"
	xptbz2.unpackinfo(infloc)
	origdir=getmycwd()
	os.chdir(pkgloc)
	print ">>> extracting",mypkg
	notok=os.system("cat "+mytbz2+"| bzip2 -dq | tar xpf -")
	if notok:
		print "!!! Error extracting",mytbz2
		cleanup_pkgmerge(mypkg,origdir)
		return None
	#the merge takes care of pre/postinst and old instance auto-unmerge, virtual/provides updates, etc.
	mylink=dblink(mycat,mypkg,myroot)
	if not mylink.exists():
		mylink.create()
		#shell error code
	mylink.merge(pkgloc,infloc,myroot)
	if not os.path.exists(infloc+"/RDEPEND"):
		returnme=""
	else:
		#get runtime dependencies
		a=open(infloc+"/RDEPEND","r")
		returnme=string.join(string.split(a.read())," ")
		a.close()
	cleanup_pkgmerge(mypkg,origdir)
	return returnme
def ebuild_init():
	"performs db/variable initialization for the ebuild system.  Not required for other scripts."
	global local_virts, root_virts, roottree, localtree, ebuild_initialized, root, virtuals
	local_virts=getvirtuals("/")
	if root=="/":
		root_virts=local_virts
	else:
		root_virts=getvirtuals(root)
	
	localtree=vartree("/",local_virts)	
	if root=="/":
		roottree=localtree
	else:
		roottree=vartree(root,root_virts)
	ebuild_initialized=1
root=getenv("ROOT")
if len(root)==0:
	root="/"
elif root[-1]!="/":
	root=root+"/"
if root != "/":
	if not os.path.exists(root[:-1]):
		print "!!! Error: ROOT",root,"does not exist.  Please correct this."
		print "!!! Exiting."
		print
		sys.exit(1)
	elif not os.path.isdir(root[:-1]):
		print "!!! Error: ROOT",root[:-1],"is not a directory.  Please correct this."
		print "!!! Exiting."
		print
		sys.exit(1)

#create tmp and var/tmp if they don't exist; read config
os.umask(0)
if not os.path.exists(root+"tmp"):
	print ">>> "+root+"tmp doesn't exist, creating it..."
	os.mkdir(root+"tmp",01777)
if not os.path.exists(root+"var/tmp"):
	print ">>> "+root+"var/tmp doesn't exist, creating it..."
	os.mkdir(root+"var",0755)
	os.mkdir(root+"var/tmp",01777)
os.umask(022)
settings=config()
ebuild_initialized=0
profiledir=None
if root!="/":
	if os.path.exists(root+"etc/make.profile/make.defaults"):
		profiledir=root+"etc/make.profile"
if not profiledir:
	if os.path.exists("/etc/make.profile/make.defaults"):
		profiledir="/etc/make.profile"
