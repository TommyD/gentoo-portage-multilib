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
#dependencies.	This should allow the new subpackages system to be integrated 
#seamlessly into our existing dependency hierarchy.
#
#Note: It may also be a good idea to allow a make.conf option so that "sys-apps/foo:run"
#automatically resolves to the master package (for those who prefer complete packages
#rather than installing things piecemeal; a great idea for development boxes where many
#things will depend on "sys-apps/foo:dev" for headers, but the developer may want the
#whole enchilada. (generally, I prefer this approach, though for runtime-only systems
#subpackages make a lot of sense).

VERSION="1.9.6_pre1"

import string,os
from stat import *
from commands import *
import types
import sys
import shlex
import shutil
import xpak
import re
import fcntl
import copy
import signal
import time
import missingos

try:
	import fchksum
	def perform_checksum(filename):
		return fchksum.fmd5t(filename)

except ImportError:
	import md5
	def md5_to_hex(md5sum):
		hexform = ""
		for ix in xrange(len(md5sum)):
			hexform = hexform + "%02x" % ord(md5sum[ix])
		return(string.lower(hexform))
	
	def perform_checksum(filename):
		f = open(filename, 'rb')
		blocksize=32768
		data = f.read(blocksize)
		size = 0L
		sum = md5.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		return (md5_to_hex(sum.digest()),size)

starttime=int(time.time())

#handle ^C interrupts correctly:
def exithandler(signum,frame):
	print "!!! Portage interrupted by SIGINT; exiting."
	#disable sandboxing to prevent problems
	if os.path.exists("/etc/ld.so.preload"):
		os.unlink("/etc/ld.so.preload")
	# 0=send to *everybody* in process group
	os.kill(0,signal.SIGKILL)
	sys.exit(1)
signal.signal(signal.SIGINT,exithandler)

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
	"""this function now turns a [1,[2,3]] list into a [1,2,3] list and returns it."""
	newlist=[]
	for x in mytokens:
		if type(x)==types.ListType:
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist

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

	specials={"KDEDIRS":[],"PATH":[],"CLASSPATH":[],"LDPATH":[],"MANPATH":[],"INFODIR":[],"ROOTPATH":[]}
	env={}

	for x in fns:
		# don't process backup files
		if x[-1]=='~' or x[-4:]==".bak":
			continue
		myconfig=getconfig(root+"etc/env.d/"+x)
		if myconfig==None:
			print "!!! Parsing error in",root+"etc/env.d/"+x
			#parse error
			continue
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

	try:
		myfile=open(myfilename,"r")
	except IOError:
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

def grabdict(myfilename):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a dictionary"""
	newdict={}
	try:
		myfile=open(myfilename,"r")
	except IOError:
		return newdict 
	mylines=myfile.readlines()
	myfile.close()
	for x in mylines:
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		myline=string.split(x)
		if len(myline)<2:
			continue
		newdict[myline[0]]=myline[1:]
	return newdict

def writedict(mydict,myfilename,writekey=1):
	"""Writes out a dict to a file; writekey=0 mode doesn't write out the key and assumes all values are strings,
	not lists."""
	try:
		myfile=open(myfilename,"w")
	except IOError:
		return 0
	if not writekey:
		for x in mydict.values():
			myfile.write(x+"\n")
	else:
		for x in mydict.keys():
			myfile.write(x+" ")
			for y in mydict[x]:
				myfile.write(y+" ")
			myfile.write("\n")
	myfile.close()
	return 1

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

def autouse(myvartree):
	"returns set of USE variables auto-enabled due to packages being installed"
	if profiledir==None:
		return ""
	mylines=grabfile(profiledir+"/use.defaults")
	if not mylines:
		return ""
	myusevars=""
	for x in mylines:
		mysplit=string.split(x)
		if len(mysplit)<2:
			#invalid line
			continue
		myuse=mysplit[0]
		mydep=x[len(mysplit[0]):]
		#check dependencies; tell depcheck() to ignore settings["USE"] since we are still forming it.
		myresult=myvartree.depcheck(mydep,lookatuse=0)
		if myresult[0]==1 and not myresult[1]:
			#deps satisfied, add USE variable...
			myusevars=myusevars+" "+myuse
	return myusevars

class config:
	def __init__(self):
		self.configdict={}
		self.configdict["origenv"]=os.environ.copy()
		self.configdict["backupenv"]={}
		if os.environ.has_key("FEATURES"):
			self.configdict["backupenv"]["FEATURES"]=os.environ["FEATURES"]
		if os.environ.has_key("USE"):
			self.configdict["backupenv"]["USE"]=os.environ["USE"]
		self.populated=0
	
	def use_regenerate(self):
		"regenerate USE variable -- dynamically taking into account any new packages installed (auto option)"
		self.configdict["auto"]={}
		self.configdict["auto"]["USE"]=autouse(db[root]["vartree"])
		mykey="USE"
		mydb=[]
		for x in self.usevaluelist:
			if self.configdict.has_key(x):
				mydb.append(self.configdict[x])
		self.regenerate(mykey,mydb)
		
	def regenerate(self,mykey,myorigdb):
		"dynamically regenerate a cumulative variable that may have changed"
		if self.configdict["backupenv"].has_key(mykey):
			self.configdict["env"][mykey]=self.configdict["backupenv"][mykey]
		mysetting=[]
		#copy our myorigdb so we don't modify it.
		mydb=myorigdb[:]
		#cycle backwards through the db entries
		mydb.reverse()
		for curdb in mydb:
			if curdb.has_key(mykey):
				#expand using only the current config file/db entry
				mysplit=expand(curdb[mykey],curdb).split()
				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".  so USE="-* gnome" will have *just* gnome enabled.
						mysetting=[]
					elif x[0]!="-":
						if not x in mysetting:
							mysetting.append(x)
					else:
						while x[1:] in mysetting:
							mysetting.remove(x[1:])
		self[mykey]=string.join(mysetting," ")
	
	def populate(self):
		self.configdict["conf"]=getconfig("/etc/make.conf")
		self.configdict["globals"]=getconfig("/etc/make.globals")
		self.configdict["env"]=self.configdict["origenv"].copy()
		if not profiledir:
			self.configdict["defaults"]={}
		else:
			self.configdict["defaults"]=getconfig(profiledir+"/make.defaults")
		self.configlist=[self.configdict["env"],self.configdict["conf"],self.configdict["defaults"],self.configdict["globals"]]
		self.populated=1
		useorder=self["USE_ORDER"]
		self.usevaluelist=useorder.split(":")
		# cumulative Portage variables with "-" support: USE and FEATURES
		# use "standard" variable regeneration code to initially set the cumulative FEATURES variable
		self.regenerate("FEATURES",self.configlist)
		# use specialized code for regenerating the cumulative and dynamic USE setting.
		self.use_regenerate()
		# USE doesn't consult make.globals while FEATURES does.
	
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
		"set a value; will be thrown away at reset() time"
		if not self.populated:
			self.populate()
		self.configlist[0][mykey]=myvalue
	
	def reset(self):
		"reset environment to original settings"
		if not self.populated:
			self.populate()
		self.configdict["env"]=self.configdict["origenv"].copy()
		#new code here
		self.regenerate("FEATURES",self.configlist)
		self.use_regenerate()

	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		for x in self.keys(): 
			mydict[x]=self[x]
		return mydict
	
def spawn(mystring,debug=0,free=0):
	"""spawn a subprocess with optional sandbox protection, 
	depending on whether sandbox is enabled.  The "free" argument,
	when set to 1, will disable sandboxing.  This allows us to 
	spawn processes that are supposed to modify files outside of the
	sandbox.  We can't use os.system anymore because it messes up
	signal handling.  Using spawn allows our Portage signal handler
	to work."""
	mypid=os.fork()
	if mypid==0:
		myargs=[]
		if ("sandbox" in features) and (not free):
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
		# If the execve fails, we need to report it, and exit
		# *carefully*
		# report error here
		os._exit(1)
		return # should never get reached
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

def fetch(myuris):
	"fetch files.  Will use digest file if available."
	if ("mirror" in features) and ("nomirror" in settings["RESTRICT"].split()):
		print ">>> \"mirror\" mode and \"nomirror\" restriction enabled; skipping fetch."
		return 1
	mirrors=settings["GENTOO_MIRRORS"].split()
	fetchcommand=settings["FETCHCOMMAND"]
	resumecommand=settings["RESUMECOMMAND"]
	fetchcommand=string.replace(fetchcommand,"${DISTDIR}",settings["DISTDIR"])
	resumecommand=string.replace(resumecommand,"${DISTDIR}",settings["DISTDIR"])
	mydigests=None
	digestfn=settings["FILESDIR"]+"/digest-"+settings["PF"]
	if os.path.exists(digestfn):
		myfile=open(digestfn,"r")
		mylines=myfile.readlines()
		mydigests={}
		for x in mylines:
			myline=string.split(x)
			if len(myline)<2:
				#invalid line
				continue
			mydigests[myline[2]]={"md5":myline[1],"size":string.atol(myline[3])}
	if "fetch" in settings["RESTRICT"].split():
		# fetch is restricted.	Ensure all files have already been downloaded; otherwise,
		# print message and exit.
		gotit=1
		for myuri in myuris:
			myfile=os.path.basename(myuri)
			try:
				mystat=os.stat(settings["DISTDIR"]+"/"+myfile)
			except OSError:
				# file does not exist
				print "!!!",myfile,"not found in",settings["DISTDIR"]+"."
				gotit=0
				break
		if not gotit:
			print ">>>",settings["EBUILD"],"has fetch restriction turned on."
			print ">>> This probably means that this ebuild's files must be downloaded"
			print ">>> manually.  See the comments in the ebuild for more information."
			return 0
		return 1
	locations=mirrors[:]
	filedict={}
	for myuri in myuris:
		myfile=os.path.basename(myuri)
		if not filedict.has_key(myfile):
			filedict[myfile]=[]
			for y in range(0,len(locations)):
				filedict[myfile].append(locations[y]+"/distfiles/"+myfile)
		filedict[myfile].append(myuri)
	for myfile in filedict.keys():
		locfetch=fetchcommand
		docontinue=0
		try:
			mystat=os.stat(settings["DISTDIR"]+"/"+myfile)
			if mydigests!=None and mydigests.has_key(myfile):
				#if we have the digest file, we know the final size and can resume the download.
				if mystat[ST_SIZE]<mydigests[myfile]["size"]:
					print ">>> Resuming download..."
					locfetch=resumecommand
				else:
					#we already have it downloaded, skip.
					#if our file is bigger than the recorded size, digestcheck should catch it.
					docontinue=1
					pass
			else:
				#we don't have the digest file, but the file exists.  Assume it is fully downloaded.
				docontinue=1
				pass
		except OSError:
			pass
		if docontinue:
			#you can't use "continue" when you're inside a "try" block
			continue
		gotit=0
		for loc in filedict[myfile]:
			if loc[:14]=="http://mirror/":
				#generic syntax for a file mirrored directly on a gentoo mirror
				if len(mirrors):
					#we have a mirror specified; use it:
					loci=mirrors[0]+"/distfiles/"+myuri[14:]
				else:
					#no mirrors specified in config files, so use a default:
					myuri="http://www.ibiblio.org/gentoo/distfiles/"+myuri[14:]
			print
			print ">>> Downloading",loc
			myfetch=string.replace(locfetch,"${URI}",loc)
			myfetch=string.replace(myfetch,"${FILE}",myfile)
			myret=spawn(myfetch,free=1)
			if mydigests!=None and mydigests.has_key(myfile):
				try:
					mystat=os.stat(settings["DISTDIR"]+"/"+myfile)
					if mystat[ST_SIZE]==mydigests[myfile]["size"]:
						gotit=1
						break
				except OSError:
					pass
			else:
				if not myret:
					gotit=1
					break
		if not gotit:
			print '!!! Couldn\'t download',myfile+".  Aborting."
			return 0
	return 1

def digestgen(myarchives,overwrite=1):
	"""generates digest file if missing.  Assumes all files are available.	If
	overwrite=1, the digest will only be created if it doesn't exist."""
	if not os.path.isdir(settings["FILESDIR"]):
		os.makedirs(settings["FILESDIR"])
		if "cvs" in features:
			print ">>> Auto-adding files/ dir to CVS..."
			spawn("cd "+settings["O"]+"; cvs add files",free=1)
	myoutfn=settings["FILESDIR"]+"/.digest-"+settings["PF"]
	myoutfn2=settings["FILESDIR"]+"/digest-"+settings["PF"]
	if (not overwrite) and os.path.exists(myoutfn2):
		return
	print ">>> Generating digest file..."
	outfile=open(myoutfn,"w")
	for x in myarchives:
		myfile=settings["DISTDIR"]+"/"+x
		mymd5=perform_md5(myfile)
		mysize=os.stat(myfile)[ST_SIZE]
		#The [:-1] on the following line is to remove the trailing "L"
		outfile.write("MD5 "+mymd5+" "+x+" "+`mysize`[:-1]+"\n")	
	outfile.close()
	movefile(myoutfn,myoutfn2)
	if "cvs" in features:
		print ">>> Auto-adding digest file to CVS..."
		spawn("cd "+settings["FILESDIR"]+"; cvs add digest-"+settings["PF"],free=1)
	print ">>> Computed message digests."
	
def digestcheck(myarchives):
	"Checks md5sums.  Assumes all files have been downloaded."
	if not myarchives:
		#No archives required; don't expect a digest
		return 1
	digestfn=settings["FILESDIR"]+"/digest-"+settings["PF"]
	if not os.path.exists(digestfn):
		if "digest" in features:
			print ">>> No message digest file found.",digestfn
			print ">>> \"digest\" mode enabled; auto-generating new digest..."
			digestgen(myarchives)
			return 1
		else:
			print "!!! No message digest file found.",digestfn
			print "!!! Type \"ebuild foo.ebuild digest\" to generate a digest."
			return 0
	myfile=open(digestfn,"r")
	mylines=myfile.readlines()
	mydigests={}
	for x in mylines:
		myline=string.split(x)
		if len(myline)<2:
			#invalid line
			continue
		mydigests[myline[2]]=[myline[1],myline[3]]
	for x in myarchives:
		if not mydigests.has_key(x):
			if "digest" in features:
				print ">>> No messages digest found for",x+"."
				print ">>> \"digest\" mode enabled; auto-generating new digest..."
				digestgen(myarchives)
				return 1
			else:
				print "!!! No message digest found for",x+"."
				print "!!! Type \"ebuild foo.ebuild digest\" to generate a digest."
				return 0
		mymd5=perform_md5(settings["DISTDIR"]+"/"+x)
		if mymd5 != mydigests[x][0]:
			print
			print "!!!",x+": message digests do not match!"
			print "!!!",x,"is corrupt or incomplete."
			print ">>> our recorded digest:",mydigests[x][0]
			print ">>>  your file's digest:",mymd5
			print ">>> Please delete",settings["DISTDIR"]+"/"+x,"and refetch."
			print
			return 0
		else:
			print ">>> md5 ;-)",x
	return 1

# "checkdeps" support has been depreciated.  Relying on emerge to handle it.
def doebuild(myebuild,mydo,myroot,debug=0):
	global settings
	if not os.path.exists(myebuild):
		print "!!! doebuild:",myebuild,"not found."
		return 1
	if myebuild[-7:]!=".ebuild":
		print "!!! doebuild: ",myebuild,"does not appear to be an ebuild file."
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
	settings["ECLASSDIR"]=settings["PORTDIR"]+"/eclass"
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
	settings["SLOT"]=""
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

	if mydo=="unmerge": 
		return unmerge(settings["CATEGORY"],settings["PF"],myroot)
	
	if mydo not in ["help","clean","prerm","postrm","preinst","postinst","config","touch","setup",
	"depend","fetch","digest","unpack","compile","install","rpm","qmerge","merge","package"]:
		print "!!! Please specify a valid command."
		return 1

	# if any of these are being called, stop now, handle them and stop now.
	if mydo in ["help","clean","prerm","postrm","preinst","postinst","config","touch","setup"]:
		return spawn("/usr/sbin/ebuild.sh "+mydo)
		#initial ebuild.sh bash environment configured
	
	mydbkey="/var/cache/edb/dep/dep-"+os.path.basename(settings["EBUILD"])
	if (not os.path.exists(mydbkey)) or os.stat(mydbkey)[ST_MTIME]<os.stat(settings["EBUILD"])[ST_MTIME]:
		#cached info stale or non-existent
		myso=getstatusoutput("/usr/sbin/ebuild.sh depend")
		if myso[0]!=0:
			print "\n\n!!! Portage had a problem processing this file:"
			print "!!!",settings["EBUILD"]+"\n"+myso[1]+"\n"+"!!! aborting.\n"
			return 1
	if mydo=="depend":
		return 0
	# obtain the dependency, slot and SRC_URI information from the edb cache file
	a=open(mydbkey,"r")
	mydeps=eval(a.readline())
	a.close()

	# get possible slot information from the deps file
	settings["SLOT"]=mydeps[2]
	settings["RESTRICT"]=mydeps[4]	
	# it's fetch time	
	myuris=mydeps[3]
	newuris=flatten(evaluate(tokenize(myuris),string.split(settings["USE"])))	
	alluris=flatten(evaluate(tokenize(myuris),[],1))	
	alist=[]
	aalist=[]
	for x in alluris:
		mya=os.path.basename(x)
		if not mya in alist:
			alist.append(mya)
	for x in newuris:
		mya=os.path.basename(x)
		if not mya in aalist:
			aalist.append(mya)
	settings["A"]=string.join(alist," ")
	settings["AA"]=string.join(aalist," ")
	if "cvs" in features:
		fetchme=alluris
		checkme=aalist
	else:
		fetchme=newuris
		checkme=alist

	if not fetch(fetchme):
		return 1

	if mydo=="fetch":
		return 0

	if "digest" in features:
		#generate digest if it doesn't exist.
		digestgen(checkme,overwrite=0)
		if mydo=="digest":
			return 0
	elif mydo=="digest":
		digestgen(checkme,overwrite=1)
		return 0
		
	if not digestcheck(checkme):
		return 1
	
	#initial dep checks complete; time to process main commands
	
	actionmap={	"unpack":"unpack", 
				"compile":"setup unpack compile",
				"install":"setup unpack compile install",
				"rpm":"setup unpack compile install rpm"
				}
	if mydo in actionmap.keys():	
		if "noauto" in features:
			return spawn("/usr/sbin/ebuild.sh "+mydo)
		else:
			return spawn("/usr/sbin/ebuild.sh "+actionmap[mydo])
	elif mydo=="qmerge": 
		#qmerge is specifically not supposed to do a runtime dep check
		return merge(settings["CATEGORY"],settings["PF"],settings["D"],settings["BUILDDIR"]+"/build-info",myroot)
	elif mydo=="merge":
		retval=spawn("/usr/sbin/ebuild.sh setup unpack compile install")
		if retval: return retval
		return merge(settings["CATEGORY"],settings["PF"],settings["D"],settings["BUILDDIR"]+"/build-info",myroot,myebuild=settings["EBUILD"])
	elif mydo=="package":
		retval=spawn("/usr/sbin/ebuild.sh setup")
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

def isfifo(x):
	mymode=os.lstat(x)[ST_MODE]
	if S_ISLNK(mymode):
		return 0
	return S_ISFIFO(mymode)

expandcache={}

def expandpath(realroot,mypath):
	"""The purpose of this function is to resolve the 'real' path on disk, with all
	symlinks resolved except for the basename, since we may be installing a symlink
	and definitely don't want it expanded.	In fact, the file that we want to install
	doesn't need to exist; just the dirname."""
	global expandcache
	split=string.split(mypath,"/")
	join=string.join(split[:-1],"/")
	try:
		return expandcache[join]+'/'+split[-1]
	except:
		pass
	expandcache[join]=os.path.realpath(join)
	return expandcache[join]

def movefile(src,dest,newmtime=None,sstat=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	
	#implementation note: we may want to try doing a simple rename() first, and fall back
	#to the "hard link shuffle" only if that doesn't work.  We now do the hard-link shuffle
	#for everything.

	try:
		dstat=os.lstat(dest)
		destexists=1
	except:
		#stat the directory for same-filesystem testing purposes
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0
	if sstat==None:
		sstat=os.lstat(src)
	# symlinks have to be handled special
	if S_ISLNK(sstat[ST_MODE]):
		# if destexists, toss it, then call os.symlink, shutil.copystat(src,dest)
		# *real* src
		if destexists:
			try:
				os.unlink(dest)
			except:
				print "!!! couldn't unlink",dest
				# uh oh. oh well
				return None 

		try:
			real_src = os.readlink(src)
		except:
			print "!!! couldn't readlink",src
			return None 
		try:
			os.symlink(real_src,dest)
		except:
			print "!!! couldn't symlink",real_src,"->",dest
			return None 
		try:
			missingos.lchown(dest,sstat[ST_UID],sstat[ST_GID])
		except:
			print "!!! couldn't set uid/gid on",dest
		#the mtime of a symbolic link can only be set at create time.
		#thus, we return the mtime of the symlink (which was set when we created it)
		#so it can be recorded in the package db if necessary.
		return os.lstat(dest)[ST_MTIME]

	if not destexists:
		if sstat[ST_DEV]==dstat[ST_DEV]:
			try:
				os.rename(src,dest)
				if newmtime:
					os.utime(dest,(newmtime,newmtime))
					return newmtime
				else:
					#renaming doesn't change mtimes, so we can return the source mtime:
					return sstat[ST_MTIME]
			except:
				return None 
		else:
			if S_ISCHR(sstat[ST_MODE]) or S_ISBLK(sstat[ST_MODE]) or S_ISFIFO(sstat[ST_MODE]):
				#we don't yet handle special files across filesystems, so we need to fall back to /bin/mv
				a=getstatusoutput("/bin/mv -f "+"'"+src+"' '"+dest+"'")
				if a[0]!=0:
					return None
					#failure
				if newmtime:
					os.utime(dest, (newmtime,newmtime))
					return newmtime
				else:
					#get actual mtime from copied file, since we can't specify an mtime using mv
					finalstat=os.lstat(dest)
					return finalstat[ST_MTIME]
			#not on same fs and a regular file
			try:
				shutil.copyfile(src,dest)
				try:
					missingos.lchown(dest, sstat[ST_UID], sstat[ST_GID])
				except:
					print "!!! couldn't set uid/gid on",dest
				# do chmod after chown otherwise the sticky bits are reset
				os.chmod(dest, S_IMODE(sstat[ST_MODE]))
				if not newmtime:
					os.utime(dest, (sstat[ST_ATIME], sstat[ST_MTIME]))
					returnme=sstat[ST_MTIME]
				else:
					os.utime(dest, (newmtime,newmtime))
					returnme=newmtime
				os.unlink(src)
				return returnme 
			except:
				#copy failure
				return None
	# destination exists, do our "backup plan"
	destnew=dest+"#new#"
	destorig=dest+"#orig#"
	try:
		# make a hard link backup
		os.link(dest,destorig)
	except:
		#backup failure
		print "!!! link fail 1 on",dest,"->",destorig
		destorig=None
	#copy destnew file into place
	if sstat[ST_DEV]==dstat[ST_DEV]:
		#on the same fs
		try:
			os.rename(src,destnew)
		except:
			print "!!! rename fail 1 on",src,"->",destnew
			if destorig:
				os.unlink(destorig)
			return None 
	else:
		#not on same fs
		try:
			shutil.copyfile(src,destnew)
		except OSError, details:
			print '!!! copy',src,'->',destnew,'failed -',details
			return None 
		except:
			#copy failure
			print "!!! copy fail 1 on",src,"->",destnew
			# gotta remove destorig *and* destnew
			if destorig:
				os.unlink(destorig)
			return None
		try:
			os.unlink(src)
		except:
			print "!!! unlink fail 1 on",src
			# gotta remove dest+#orig# *and destnew
			os.unlink(destnew)
			if destorig:
				os.unlink(destorig)
			return None 
	#destination exists, destnew file is in place on the same filesystem
	#update ownership on destnew
	try:
		missingos.lchown(destnew, sstat[ST_UID], sstat[ST_GID])
	except:
		print "!!! couldn't set uid/gid on",dest
	#update perms on destnew
	# do chmod after chown otherwise the sticky bits are reset
	try:
		os.chmod(destnew, S_IMODE(sstat[ST_MODE]))
	except:
		print "!!! chmod fail on",dest
	#update times on destnew
	if not newmtime:
		try:
			os.utime(destnew, (sstat[ST_ATIME], sstat[ST_MTIME]))
		except:
			print "!!! couldn't set times on",destnew
		returnme=sstat[ST_MTIME]
	else:
		try:
			os.utime(destnew, (newmtime,newmtime))
		except:
			print "!!! couldn't set times on",destnew
		returnme=newmtime
	try:
		os.unlink(dest) # scary!
	except:
		# gotta remove destorig *and destnew
		print "!!! unlink fail 1 on",dest
		if destorig:
			os.unlink(destorig)
		os.unlink(destnew)
		return None 
	try:
		os.rename(destnew,dest)
	except:
		#os.rename guarantees to leave dest in place if the rename fails.
		print "!!! rename fail 2 on",destnew,"->",dest
		os.unlink(destnew)
		return None 
	try:
		if destorig:
			os.unlink(destorig)
	except:
		print "!!! unlink fail 1 on",destorig
	return returnme 

def getmtime(x):
	 return `os.lstat(x)[-2]`

def perform_md5(x):
	return perform_checksum(x)[0]

def pathstrip(x,mystart):
    cpref=os.path.commonprefix([x,mystart])
    return [root+x[len(cpref)+1:],x[len(cpref):]]

def merge(mycat,mypkg,pkgloc,infloc,myroot,myebuild=None):
	mylink=dblink(mycat,mypkg,myroot)
	if not mylink.exists():
		mylink.create()
		#shell error code
	mylink.merge(pkgloc,infloc,myroot,myebuild)
	
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
# package (with version) name.	If it is a valid name, pkgsplit will
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
	
# gets virtual package settings

def getvirtuals(myroot):
	myvirts={}
	myvirtfiles=[]
	if profiledir:
		myvirtfiles=[profiledir+"/virtuals"]
	myvirtfiles.append(root+"/var/cache/edb/virtuals")
	for myvirtfn in myvirtfiles:
		if not os.path.exists(myvirtfn):
			continue
		myfile=open(myvirtfn)
		mylines=myfile.readlines()
		for x in mylines:
			mysplit=string.split(x)
			if len(mysplit)<2:
				#invalid line
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
	
	def load(self,mykey):
		"loads a cat/pkg from disk into the tree"
		#stub function for non-incremental caching:
		if not self.populated:
			self.populate()
		if not self.tree.has_key(mykey):
			self.tree[mykey]=[]

	def populate(self):
		"populates the tree with values"
		populated=1
		pass

	def zap(self,mycatpkg):
		"remove a catpkg from the deptree"
		cps=catpkgsplit(mycatpkg,0)
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			#load cat/pkg'skeys from disk into tree
			self.load(mykey)
		x=0
		while x<len(self.tree[mykey]):
			if self.tree[mykey][x][0]==mycatpkg:
				del self.tree[mykey][x]
			x=x+1
		if len(self.tree[mykey])==0:
			self.tree[mykey]=[]

	def inject(self,mycatpkg):
		"add a specific catpkg to the deptree"
		cps=catpkgsplit(mycatpkg,0)
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			self.load(mykey)
		for x in self.tree[mykey]:
			if x[0]==mycatpkg:
				#already in the tree
				return
		self.tree[mykey].append([mycatpkg,cps])
		#new packages mean possible new auto-use settings, so regenerate USE vars
		settings.use_regenerate()
	
	def resolve_key(self,mykey):
		"generates new key, taking into account virtual keys"
		if not self.tree.has_key(mykey):
			self.load(mykey)
		if self.tree.has_key(mykey) and len(self.tree[mykey])==0:
			#no packages correspond to the key
			if self.virtual:
				if self.virtual.has_key(mykey):
					self.load(self.virtual[mykey])
					return self.virtual[mykey]
		return mykey

	def exists_specific(self,myspec):
		myspec=self.resolve_specific(myspec)
		if not myspec:
			return None
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			self.load(mykey)
		for x in self.tree[mykey]:
			if x[0]==myspec: 
				return 1
		return 0

	def exists_specific_cat(self,myspec):
		"give me a specific package, and I'll tell you whether the specific node exists."
		myspec=self.resolve_specific(myspec)
		if not myspec:
			return None
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=cps[0]+"/"+cps[1]
		if not self.tree.has_key(mykey):
			self.load(mykey)
		if len(self.tree[mykey]):
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
		"""Does the particular node (cat/pkg key) exist?"""
		myreskey=self.resolve_key(mykey)
		if self.tree.has_key(myreskey):
			if len(self.tree[myreskey]):
				return 1
		return 0
	
	def getallnodes(self):
		"returns a list of all keys in our tree"
		if not self.populated:
			self.populate()
		mykeys=[]
		for x in self.tree.keys():
			if len(self.tree[x]):
				mykeys.append(x)
		return mykeys

	def getnode(self,nodename):
		nodename=self.resolve_key(nodename)
		if not nodename:
			return []
		if not self.tree.has_key(nodename):
			self.load(nodename)
		return self.tree[nodename]
	
	def depcheck(self,depstring,lookatuse=1):
		"""evaluates a dependency string and returns a 2-node result list
		[1, None] = ok, no dependencies
		[1, ["x11-base/foobar","sys-apps/oni"] = dependencies must be satisfied
		[0, * ] = parse error
		"""
		if lookatuse:
			myusesplit=string.split(settings["USE"])
		else:
			#we are being run by autouse(), don't consult USE vars yet.
			myusesplit=[]
		mysplit=string.split(depstring)
		#convert parenthesis to sublists
		mysplit=dep_parenreduce(mysplit)
		#mysplit can't be None here, so we don't need to check
		mysplit=dep_opconvert(mysplit,myusesplit)
		#if mysplit==None, then we have a parse error (paren mismatch or misplaced ||)
		#up until here, we haven't needed to look at the database tree
		
		if mysplit==None:
			return [0,"Parse Error (parenthesis mismatch?)"]
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
			#catch "! " errors
			if not mypkgdep[1:]:
				return None
			mybestmatch=self.dep_bestmatch(mypkgdep[1:])
			if mybestmatch:
				return 0
			else:
				return 1
		elif mypkgdep[0]=="=":
			# =cat/pkg-v
			if mypkgdep[-1]=="*":
				if not mypkgdep[1:-1]:
					return None
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
				if not mypkgdep[1:]:
					return None
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
			if not mypkgdep[1:]:
				return None
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
			re_deps=re.compile("^([><=~]*)(.+)$")
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
		dependency and returns it, i.e: "foo/bar-1.3".	Works
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
				if string.atoi(x[1][3][1:])>myrev:
					myrev=string.atoi(x[1][3][1:])
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
		*don't* match.	This method is used to clean the portagetree using entries in the 
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
				if not self.hasnode(mykey):
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
			if not self.hasnode(mykey):
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
					if ((pkgcmp(x[1][1:],cmp1)>=0) and (pkgcmp(x[1][1:],cmp2)<0)):
						mynodes.append(x[0])
				return mynodes
			elif self.exists_specific(mypkgdep[1:]):
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
			self.gotcat=copy.deepcopy(clone.gotcat)
		else:
			self.root=root
			self.gotcat={}
		packagetree.__init__(self,virtual,clone)
	def getebuildpath(self,fullpackage):
		cat,package=fullpackage.split("/")
		return self.root+"var/db/pkg/"+fullpackage+"/"+package+".ebuild"
	
	def load(self,mykey):
		if '/' in mykey:
			mycat,mypkg=string.split(mykey,"/")
		else:
			return []
		if not self.tree.has_key(mykey):
			self.tree[mykey]=[]
		#This next line allows us to set root to None and disable loading (for "emptytrees")
		if not self.root:
			return
		if self.gotcat.has_key(mycat):
			return
		if not os.path.isdir(self.root+"/var/db/pkg/"+mycat):
			return
		for x in os.listdir(self.root+"/var/db/pkg/"+mycat):
			if x[0:len(mypkg)]!=mypkg:
				#skip, since we're definitely not interested if the package name doesn't match.
				#note that this isn't a perfect test, but will weed out 99% of the packages we aren't interested in loading.
				continue
			if isjustname(x):
				fullpkg=mycat+"/"+x+"-1.0"
			else:
				fullpkg=mycat+"/"+x
			mysplit=catpkgsplit(fullpkg,0)
			if mysplit==None:
				print "!!! Error:",self.root+"/var/db/pkg/"+mycat+"/"+x,"is not a valid database entry, skipping..."
				continue
			mynewkey=mycat+"/"+mysplit[1]
			if not self.tree.has_key(mynewkey):
				self.tree[mynewkey]=[]
			for y in self.tree[mynewkey]:
				if y[0]==fullpkg:
					#we've already got it, skip.
					continue
			self.tree[mynewkey].append([fullpkg,mysplit])

	def getslot(self,mycatpkg):
		"""Get a slot for a catpkg; assume it exists."""
		if not os.path.exists(self.root+"var/db/pkg/"+mycatpkg+"/SLOT"):
			return ""
		myslotfile=open(self.root+"var/db/pkg/"+mycatpkg+"/SLOT","r")
		myslotvar=string.split(myslotfile.readline())
		myslotfile.close()
		if len(myslotvar):
			return myslotvar[0]
		else:
			return ""
	
	def gettimeval(self,mycatpkg):
		"""Get an integer time value that can be used to compare against other catpkgs; the timeval will try to use
		COUNTER but will also take into account the start time of Portage and use mtimes of CONTENTS files if COUNTER
		doesn't exist.  The algorithm makes it safe to compare the timeval values of COUNTER-enabled and non-COUNTER
		db entries.  Assumes mycatpkg exists."""
		global starttime	
		rootp=self.root+"var/db/pkg/"+mycatpkg
		if not os.path.exists(rootp+"/COUNTER"):
			if not os.path.exists(rootp+"/CONTENTS"):
				return 0
			else:
				return os.stat(rootp+"/CONTENTS")[ST_MTIME]	
		else:
			mycounterfile=open(rootp+"/COUNTER","r")
			mycountervar=string.atoi(string.split(mycounterfile.readline())[0])
			mycounterfile.close()
			return starttime+mycountervar
	
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
		mywd=os.getcwd()
		for x in os.listdir(mywd):
			if not os.path.isdir(mywd+"/"+x):
				continue
			for y in os.listdir(mywd+"/"+x):
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
			self.pkgmaskdict=clone.pkgmaskdict
			self.pkglines=clone.pkglines
		else:
			self.root=root
			self.portroot=settings["PORTDIR"]
			self.pkgmaskdict={}
			self.pkgmasklines=grabfile(self.portroot+"/profiles/package.mask")
			self.pkglines=[]
			#remove '*'s from beginnning of deps
			if profiledir:
				for x in grabfile(profiledir+"/packages"):
					if x[0]=="*":
						self.pkglines.append(x[1:])
					else:
						self.pkglines.append(x)
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
		self.domask()
		
	def domask(self):
		"mask out appropriate entries in our database.	We call this whenever we add to the db."
		for x in self.pkgmasklines:
			matches=self.dep_match(x)
			if matches:
				for y in matches:
					self.zap(y)
		for x in self.pkglines:
			matches=self.dep_nomatch(x)
			for y in matches:
				self.zap(y)

	def getdeps(self,pf):
		"returns list of dependencies, if any"
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
		myebuildpath=self.dbdir+"/"+self.pkg+".ebuild"
		if not os.path.exists(myebuildpath):
			myebuildpath=None
		#do prerm script
		if myebuildpath:
			a=doebuild(myebuildpath,"prerm",self.myroot)
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
				try:
					os.rmdir(obj)
				except OSError:
					#We couldn't remove the dir; maybe it's immutable?
					pass
				print "<<<	 ","dir",obj
			elif pkgfiles[obj][0]=="sym":
				if not os.path.islink(obj):
					print "--- !sym  ","sym", obj
					continue
				if (getmtime(obj) != pkgfiles[obj][1]):
					print "--- !mtime sym",obj
					continue
				mydest=os.readlink(obj)
				if os.path.exists(os.path.normpath(self.myroot+mydest)):
					if mydest != pkgfiles[obj][2]:
						print "--- !destn","sym", obj
						continue
				myppath=""
				for ppath in self.protect:
					if obj[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if obj[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfgpro  ","sym",obj
					continue
				try:
					os.unlink(obj)
				except OSError:
					#immutable?
					pass
				print "<<<	 ","sym",obj
			elif pkgfiles[obj][0]=="obj":
				if not os.path.isfile(obj):
					print "--- !obj  ","obj", obj
					continue
				mymd5=perform_md5(obj)
				# string.lower is needed because db entries used to be in upper-case.  The
				# string.lower allows for backwards compatibility.
				if mymd5 != string.lower(pkgfiles[obj][2]):
					print "--- !md5  ","obj", obj
					continue
				myppath=""
				for ppath in self.protect:
					if obj[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if obj[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfgpro  ","obj",obj
				else:
					try:
						os.unlink(obj)
					except OSError:
						pass		
					print "<<<	 ","obj",obj
			elif pkgfiles[obj][0]=="fif":
				if not isfifo(obj):
					print "--- !fif  ","fif", obj
					continue
				myppath=""
				for ppath in self.protect:
					if obj[0:len(ppath)]==ppath:
						masked=0
						#config file management
						for pmpath in self.protectmask:
							if obj[0:len(pmpath)]==pmpath:
								#skip, it's in the mask
								masked=1
								break
						if not masked: 
							myppath=ppath
							break
				if myppath:
					print "--- cfgpro  ","fif",obj
					continue
				try:
					os.unlink(obj)
				except OSError:
					pass
				print "<<<	 ","fif",obj
			elif pkgfiles[obj][0]=="dev":
				print "---	 ","dev",obj

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		db[self.myroot]["vartree"].zap(self.cat+"/"+self.pkg)
		#remove stale virtual entries (mappings for packages that no longer exist)
		newvirts={}
		myvirts=grabdict(self.myroot+"var/cache/edb/virtuals")
		for myvirt in myvirts.keys():
			newvirts[myvirt]=[]
			for mykey in myvirts[myvirt]:
				if db[self.myroot]["vartree"].hasnode(mykey):
					newvirts[myvirt].append(mykey)
			if newvirts[myvirt]==[]:
				del newvirts[myvirt]
		writedict(newvirts,self.myroot+"var/cache/edb/virtuals")
		
		#do original postrm
		if myebuildpath:
			a=doebuild(myebuildpath,"postrm",self.myroot)
			if a:
				print "!!! pkg_postrm() script failed; exiting."
				sys.exit(a)
	
	def treewalk(self,srcroot,destroot,inforoot,myebuild):
		# srcroot = ${D}; destroot=where to merge, ie. ${ROOT}, inforoot=root of db entry,
		# secondhand = list of symlinks that have been skipped due to their target not existing (will merge later),
		"this is going to be the new merge code"
		if not os.path.exists(self.dbdir):
			self.create()
		# print ">>> Updating mtimes..."
		# before merging, it's *very important* to touch all the files
		# this ensures that their mtime is current and unmerging works correctly
		# spawn("(cd "+srcroot+"; for x in `find`; do  touch -c $x 2>/dev/null; done)",free=1)
		print ">>> Merging",self.cat+"/"+self.pkg,"to",destroot
		# get current counter value
		edbpath=destroot+"/var/cache/edb/"
		counterpath=edbpath+"counter"
		packagecounter=long(0)
		globalcounterfile=None
		if not os.path.exists(edbpath):
			os.makedirs(edbpath)
		if os.path.exists(counterpath):
			globalcounterfile=open(counterpath, "r+")
			fcntl.flock(globalcounterfile.fileno(), fcntl.LOCK_EX)
			packagecounter=long(globalcounterfile.readline())
		else:
			globalcounterfile=open(counterpath, "w")
			fcntl.flock(globalcounterfile.fileno(), fcntl.LOCK_EX)
		packagecounter=packagecounter+1
		# write package counter
		localcounterfile=open(inforoot+"/COUNTER","w")
		localcounterfile.write(str(packagecounter))
		localcounterfile.close()
		# update global counter
		globalcounterfile.seek(0,0)
		globalcounterfile.truncate(0);
		globalcounterfile.write(str(packagecounter))
		fcntl.flock(globalcounterfile.fileno(), fcntl.LOCK_UN)
		globalcounterfile.close()
		#This next line just ends up confusing people and I don't think it's absolutely necessary;
		#commented out (drobbins)
		#print ">>> Package will have counter",packagecounter
		# get old contents info for later unmerging
		oldcontents=self.getcontents()
		# run preinst script
		if myebuild:
			# if we are merging a new ebuild, use *its* pre/postinst rather than using the one in /var/db/pkg 
			# (if any).
			a=doebuild(myebuild,"preinst",root)
		else:
			a=doebuild(inforoot+"/"+self.pkg+".ebuild","preinst",root)
		if a:
			print "!!! pkg_preinst() script failed; exiting."
			sys.exit(a)
		# open CONTENTS file (possibly overwriting old one) for recording
		outfile=open(inforoot+"/CONTENTS","w")
		# prep for config file management
		self.protect=[]
		# self.protect records any paths in CONFIG_PROTECT that are real directories and exist
		for x in string.split(settings["CONFIG_PROTECT"]):
			ppath=os.path.normpath(destroot+"/"+x)+"/"
			if os.path.isdir(ppath):
				self.protect.append(ppath)
		self.protectmask=[]
		# self.protectmask records any paths in CONFIG_PROTECT_MASK that are real directories and exist
		for x in string.split(settings["CONFIG_PROTECT_MASK"]):
			ppath=os.path.normpath(destroot+"/"+x)+"/"
			if os.path.isdir(ppath):
				self.protectmask.append(ppath)
		cfgfiledict={}
		#if we have a file containing previously-merged config file md5sums, grab it.
		if os.path.exists(destroot+"/var/cache/edb/config"):
			cfgfiledict=grabdict(destroot+"/var/cache/edb/config")
		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		mymtime=int(time.time())
		prevmask=os.umask(0)
		secondhand=[]	
		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		self.mergeme(srcroot,destroot,outfile,secondhand,"",cfgfiledict,mymtime)
		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen=0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that couldn't get merged will be
			# added to thirdhand.
			thirdhand=[]
			self.mergeme(srcroot,destroot,outfile,thirdhand,secondhand,cfgfiledict,mymtime)
			#swap hands
			lastlen=len(secondhand)
			# our thirdhand now becomes our secondhand.  It's ok to throw away secondhand since 
			# thirdhand contains all the stuff that couldn't be merged.
			secondhand=thirdhand
		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			self.mergeme(srcroot,destroot,outfile,None,secondhand,cfgfiledict,mymtime)
			
		#restore umask
		os.umask(prevmask)
		#if we opened it, close it	
		outfile.close()
		print
		if (oldcontents):
			print ">>> Safely unmerging already-installed instance..."
			self.unmerge(oldcontents)
			print ">>> original instance of package unmerged safely."	
		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in os.listdir(inforoot):
			self.copyfile(inforoot+"/"+x)
		
		#write out our collection of md5sums
		writedict(cfgfiledict,destroot+"/var/cache/edb/config")
		
		#create virtual links
		myprovides=self.getelements("PROVIDE")
		if myprovides:
			myvkey=self.cat+"/"+pkgsplit(self.pkg)[0]
			myvirts=grabdict(destroot+"var/cache/edb/virtuals")
			for mycatpkg in self.getelements("PROVIDE"):
				if isspecific(mycatpkg):
					#convert a specific virtual like dev-lang/python-2.2 to dev-lang/python
					mysplit=catpkgsplit(mycatpkg)
					mycatpkg=mysplit[0]+"/"+mysplit[1]
				if myvirts.has_key(mycatpkg):
					if myvkey not in myvirts[mycatpkg]:
						myvirts[mycatpkg][0:0]=[myvkey]
				else:
					myvirts[mycatpkg]=[myvkey]
			writedict(myvirts,destroot+"var/cache/edb/virtuals")
			
		#do postinst script
		if myebuild:
			# if we are merging a new ebuild, use *its* pre/postinst rather than using the one in /var/db/pkg 
			# (if any).
			a=doebuild(myebuild,"postinst",root)
		else:
			a=doebuild(inforoot+"/"+self.pkg+".ebuild","postinst",root)
		if a:
			print "!!! pkg_postinst() script failed; exiting."
			sys.exit(a)
		#update environment settings, library paths
		env_update()	
		print ">>>",self.cat+"/"+self.pkg,"merged."

	def mergeme(self,srcroot,destroot,outfile,secondhand,stufftomerge,cfgfiledict,thismtime):
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if type(stufftomerge)==types.StringType:
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist=os.listdir(srcroot+stufftomerge)
			offset=stufftomerge
			# We need mydest defined up here to calc. protection paths.  This is now done once per
			# directory rather than once per file merge.  This should really help merge performance.
			mytruncpath="/"+offset+"/"
			myppath=""
			for ppath in self.protect:
				#before matching against a protection path.
				if mytruncpath[0:len(ppath)]==ppath:
					myppath=ppath
					#config file management
					for pmpath in self.protectmask:
						#again, dir symlinks are expanded
						if mytruncpath[0:len(pmpath)]==pmpath:
						#skip, it's in the mask
							myppath=""
							break
					if not myppath:
						break	
			myppath=(myppath!="")
		else:
			mergelist=stufftomerge
			offset=""
		for x in mergelist:
			mysrc=srcroot+offset+x
			mydest=destroot+offset+x
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest="/"+offset+x
			# stat file once, test using S_* macros many times (faster that way)
			mystat=os.lstat(mysrc)
			mymode=mystat[ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir 
			try:
				mydmode=os.lstat(mydest)[ST_MODE]
			except:
				#dest file doesn't exist
				mydmode=None
			
			if S_ISLNK(mymode):
				# we are merging a symbolic link
				myto=os.readlink(mysrc)
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto=os.path.normpath(os.path.join(destroot,myto))
				if mydmode!=None:
					#destination exists
					if (not S_ISLNK(mydmode)) and (S_ISDIR(mydmode)):
						# directory in the way: we can't merge a symlink over a directory
						print "!!!",mydest,"->",myto
						# we won't merge this, continue with next file...
						continue
				# if secondhand==None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand!=None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				mymtime=movefile(mysrc,mydest,thismtime,mystat)
				if mymtime!=None:
					print ">>>",mydest,"->",myto
					outfile.write("sym "+myrealdest+" -> "+myto+" "+`mymtime`+"\n")
				else:
					print "!!!",mydest,"->",myto
			elif S_ISDIR(mymode):
				# we are merging a directory
				if mydmode!=None:
					# destination exists
					if S_ISLNK(mydmode) or S_ISDIR(mydmode):
						# a symlink to an existing directory will work for us; keep it:
						print "---",mydest+"/"
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						movefile(mydest,mydest+".backup")
						print "bak",mydest,mydest+".backup"
						#now create our directory
						os.mkdir(mydest)
						os.chmod(mydest,mystat[0])
						os.chown(mydest,mystat[4],mystat[5])
						print ">>>",mydest+"/"
				else:
					#destination doesn't exist
					os.mkdir(mydest)
					os.chmod(mydest,mystat[0])
					os.chown(mydest,mystat[4],mystat[5])
					print ">>>",mydest+"/"
				outfile.write("dir "+myrealdest+"\n")
				# recurse and merge this directory
				self.mergeme(srcroot,destroot,outfile,secondhand,offset+x+"/",cfgfiledict,thismtime)
			elif S_ISREG(mymode):
				# we are merging a regular file
				mymd5=perform_md5(mysrc)
				# calculate config file protection stuff
				mydestdir=os.path.dirname(mydest)	
				moveme=1
				zing="!!!"
				if mydmode!=None:
					# destination file exists
					if S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						moveme=0
						print "!!!",mydest
					elif S_ISREG(mydmode):
						# install of destination is blocked by an existing regular file; now, config file
						# management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if myppath:
							# we have a protection path; enable config file management.
							destmd5=perform_md5(mydest)
							if cfgfiledict.has_key(myrealdest):
								#this file has been merged in the past, either as the original file or as a ._cfg extension of original.
								#we can skip the merging of this file.  But we need to do one thing first, called "cycling".  Let's say that 
								#since the last merge on this file, the user has copied /etc/._cfg0000_foo to /etc/foo.  The ._cfg had
								#position 4 in our md5 list (in cfgfiledict).  Now that the file has been moved into place, we want to
								#*throw away* md5s 0-3.  Reasoning?  By doing this, we discard expired md5sums, and also allow a *new*
								#package to merge a "classic" version of the file (consider if the new version was buggy, so we reverted
								#to the original... without this important code, the new "original" would not get merged since it had
								#been merged before.
								if destmd5 in cfgfiledict[myrealdest]:
									cfgfiledict[myrealdest]=cfgfiledict[myrealdest][cfgfiledict[myrealdest].index(destmd5):]
							if mymd5==destmd5:
								#file already in place (somehow) ... no need to merge this file -- avoid clutter....
								zing="---"
								moveme=0
							elif cfgfiledict.has_key(myrealdest) and (mymd5 in cfgfiledict[myrealdest]):
								#ok, now that we've cycled cfgfiledict (see big paragraph above), it's safe to simply not merge this file
								#if it has been merged by us in the past.  Thanks to the cycling, we can be do this with some assurance
								#that we are not being overly zealous in our desire to avoid merging files unnecessarily.
								zing="---"
								moveme=0
							else:	
								#don't overwrite --
								# the files are not identical (from an md5 perspective); we cannot simply overwrite.
								pnum=-1
								# set pmatch to the literal filename only
								pmatch=os.path.basename(mydest)
								# config protection filename format:
								# ._cfg0000_foo
								# positioning (for reference):
								# 0123456789012
								mypfile=""
								for pfile in os.listdir(mydestdir):
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
								# mypfile is set to the name of the most recent cfg management file currently on disk.
								# if their md5sums match, we overwrite the mypfile rather than creating a new .cfg file.
								# this keeps on-disk cfg management clutter to a minimum.
								cleanup=0
								if mypfile:
									pmd5=perform_md5(mydestdir+"/"+mypfile)
									if mymd5==pmd5:
										mydest=(mydestdir+"/"+mypfile)
										cleanup=1
								if not cleanup:
									# md5sums didn't match, so we create a new filename for merging.
									# we now have pnum set to the official 4-digit config that should be used for the file
									# we need to install.  Set mydest to this new value.
									mydest=os.path.normpath(mydestdir+"/._cfg"+string.zfill(pnum,4)+"_"+pmatch)
								#add to our md5 list for future reference (will get written to /var/cache/edb/config)
								if not cfgfiledict.has_key(myrealdest):
									cfgfiledict[myrealdest]=[]
								if mymd5 not in cfgfiledict[myrealdest]:
									cfgfiledict[myrealdest].append(mymd5)
								#don't record more than 16 md5sums
								if len(cfgfiledict[myrealdest])>16:
									del cfgfiledict[myrealdest][0]
				# whether config protection or not, we merge the new file the same way.  Unless moveme=0 (blocking directory)
				if moveme:
					mymtime=movefile(mysrc,mydest,thismtime,mystat)
					if mymtime!=None:
						zing=">>>"
						outfile.write("obj "+myrealdest+" "+mymd5+" "+`mymtime`+"\n")
				print zing,mydest
			else:
				# we are merging a fifo or device node
				zing="!!!"
				if mydmode==None:
					#destination doesn't exist
					if movefile(mysrc,mydest,thismtime,mystat)!=None:
						zing=">>>"
						if S_ISFIFO(mymode):
							#we don't record device nodes in CONTENTS, although we do merge them.
							outfile.write("fif "+myrealdest+"\n")
				print zing+" "+mydest
	
	def merge(self,mergeroot,inforoot,myroot,myebuild=None):
		self.treewalk(mergeroot,myroot,inforoot,myebuild)

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

def cleanup_pkgmerge(mypkg,origdir):
	shutil.rmtree(settings["PKG_TMPDIR"]+"/"+mypkg)
	os.chdir(origdir)

def pkgmerge(mytbz2,myroot):
	"""will merge a .tbz2 file, returning a list of runtime dependencies that must be
		satisfied, or None if there was a merge error.	This code assumes the package
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
	pkgloc=tmploc+"/"+mypkg+"/bin/"
	infloc=tmploc+"/"+mypkg+"/inf/"
	if os.path.exists(tmploc+"/"+mypkg):
		shutil.rmtree(tmploc+"/"+mypkg,1)
	os.makedirs(pkgloc)
	os.makedirs(infloc)
	print ">>> extracting info"
	xptbz2.unpackinfo(infloc)
	origdir=getmycwd()
	os.chdir(pkgloc)
	print ">>> extracting",mypkg
	notok=spawn("cat "+mytbz2+"| bzip2 -dq | tar xpf -",free=1)
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
		print "!!! Error: ROOT",root[:-1],"is not a directory.	Please correct this."
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
profiledir=None
if os.path.exists("/etc/make.profile/make.defaults"):
	profiledir="/etc/make.profile"
else:
	print ">>> Note: /etc/make.profile isn't available; an 'emerge sync' will probably fix this."
#from here on in we can assume that profiledir is set to something valid
db={}
virts=getvirtuals("/")
db["/"]={"virtuals":virts,"vartree":vartree("/",virts)}
if root!="/":
	virts=getvirtuals(root)
	db[root]={"virtuals":virts,"vartree":vartree(root,virts)}
#We need to create the vartree first, then load our settings, and then set up our other trees
settings=config()
#continue setting up other trees
db["/"]["porttree"]=portagetree("/",virts)
db["/"]["bintree"]=binarytree("/",virts)
if root!="/":
	db[root]["porttree"]=portagetree(root,virts)
	db[root]["bintree"]=binarytree(root,virts)

#,"porttree":portagetree(root,virts),"bintree":binarytree(root,virts)}
features=settings["FEATURES"].split()
#getting categories from an external file now
if os.path.exists(settings["PORTDIR"]+"/profiles/categories"):
	categories=grabfile(settings["PORTDIR"]+"/profiles/categories")
else:
	categories=[]


