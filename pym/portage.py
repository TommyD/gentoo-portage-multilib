# portage.py -- core Portage functionality
# Copyright 1998-2003 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2
# $Header$

VERSION="2.0.50_pre17"

VDB_PATH="var/db/pkg"

import sys,string,os,re,types,shlex,shutil,xpak,fcntl,signal
import time,cPickle,atexit,grp,traceback,commands,pwd,cvstree,copy

import getbinpkg
import portage_dep

from output import *

from stat import *
from commands import *
from select import *
from time import sleep
from random import shuffle

signal.signal(signal.SIGCHLD, signal.SIG_DFL)

noiselimit = 0
def writemsg(mystr,noiselevel=0):
	"""Prints out warning and debug messages based on the noiselimit setting"""
	global noiselimit
	if noiselevel <= noiselimit:
		sys.stderr.write(mystr)
		sys.stderr.flush()

def load_mod(name):
	modname = string.join(string.split(name,".")[:-1],".")
	mod = __import__(modname)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def best_from_dict(key, top_dict, key_order, EmptyOnError=1, FullCopy=1, AllowEmpty=1):
	for x in key_order:
		if top_dict.has_key(x) and top_dict[x].has_key(key):
			if FullCopy:
				return copy.deepcopy(top_dict[x][key])
			else:
				return top_dict[x][key]
	if EmptyOnError:
		return ""
	else:
		raise KeyError, "Key not found in list; '%s'" % key

def lockdir(mydir):
	return lockfile(mydir,wantnewlockfile=1)
def unlockdir(mylock):
	return unlockfile(mylock)

def lockfile(mypath,wantnewlockfile=0,unlinkfile=0):
	"""Creates all dirs upto, the given dir. Creates a lockfile
	for the given directory as the file: directoryname+'.portage_lockfile'."""
	import fcntl

	if not mypath:
		raise ValueError, "Empty path given"

	if mypath[-1] == '/':
		mypath = mypath[:-1]

	if type(mypath) == types.IntType:
		lockfilename    = '[Only fd given]'
		wantnewlockfile = 0
		unlinkfile      = 0
	elif wantnewlockfile:
		lockfilename = mypath+".portage_lockfile"
		unlinkfile   = 1
	else:
		lockfilename = mypath
	
	if type(mypath) == types.StringType:
		if not os.path.exists(os.path.dirname(mypath)):
			raise IOError, "Base path does not exist '%s'" % os.path.dirname(mypath)
		myfd = os.open(lockfilename, os.O_CREAT|os.O_WRONLY,0660)

	elif type(mypath) == types.IntType:
		myfd = mypath

	else:
		raise ValueError, "Unknown type passed in '%s': '%s'" % (type(mypath),mypath)

	fcntl.flock(myfd,fcntl.LOCK_EX)
	if not os.path.exists(lockfilename):
		# The file was deleted on us... Keep trying to make one...
		os.close(myfd)
		writemsg("lockfile recurse\n",1)
		lockfilename,myfd,unlinkfile = lockfile(mypath,wantnewlockfile,unlinkfile)

	writemsg(str((lockfilename,myfd,unlinkfile))+"\n",1)
	return (lockfilename,myfd,unlinkfile)

def unlockfile(mytuple):
	import fcntl

	lockfilename,myfd,unlinkfile = mytuple
	
	if not os.path.exists(lockfilename):
		writemsg("lockfile does not exist '%s'\n" % lockfile,1)
		return None

	try:
		if myfd == None:
			myfd = os.open(lockfilename, os.O_WRONLY,0660)
			unlinkfile = 1
		fcntl.flock(myfd,fcntl.LOCK_UN)
	except Exception, e:
		raise IOError, "Failed to unlock file '%s'\n" % lockfilename

	try:
		fcntl.flock(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
		# We won the lock, so there isn't competition for it.
		# We can safely delete the file.
		writemsg("Got the lockfile...\n",1)
		if unlinkfile:
			#writemsg("Unlinking...\n")
			os.unlink(lockfilename)
			writemsg("Unlinked lockfile...\n",1)
		fcntl.flock(myfd,fcntl.LOCK_UN)
	except Exception, e:
		# We really don't care... Someone else has the lock.
		# So it is their problem now.
		writemsg("Failed to get lock... someone took it.\n",1)
		writemsg(str(e)+"\n",1)
		pass
	os.close(myfd)
			
	return 1

def unique_array(array):
	"""Takes an array and makes sure each element is unique."""
	mya = []
	for x in array:
		if x not in mya:
			mya.append(x)
	return mya
									

ostype=os.uname()[0]
if ostype=="Linux":
	userland="GNU"

	if "lchown" in dir(os):
		# Included in python-2.3
		lchown=os.lchown
	else:
		import missingos
		lchown=missingos.lchown

	os.environ["XARGS"]="xargs -r"
elif ostype=="Darwin":
	userland="BSD"
	lchown=os.chown
	os.environ["XARGS"]="xargs"	
else:
	writemsg(red("Operating system")+" \""+ostype+"\" "+red("currently unsupported. Exiting.")+"\n")
	sys.exit(1)
	
os.environ["USERLAND"]=userland

#Secpass will be set to 1 if the user is root or in the portage group.
uid=os.getuid()
secpass=0
wheelgid=0
if uid==0:
	secpass=2
try:
	wheelgid=grp.getgrnam("wheel")[2]
	if (not secpass) and (wheelgid in os.getgroups()):
		secpass=1
except KeyError:
	writemsg("portage initialization: your system doesn't have a 'wheel' group.\n")
	writemsg("Please fix this as it is a normal system requirement. 'wheel' is GID 10\n")
	writemsg("'emerge baselayout' and an 'etc-update' should remedy this problem.\n")
	pass

#Discover the uid and gid of the portage user/group
try:
	portage_uid=pwd.getpwnam("portage")[2]
	portage_gid=grp.getgrnam("portage")[2]
	if (secpass==0):
		secpass=1
except KeyError:
	portage_uid=0
	portage_gid=wheelgid
	writemsg("\n")
	writemsg(  red("portage: 'portage' user or group missing. Please update baselayout\n"))
	writemsg(  red("         and merge portage user(250) and group(250) into your passwd\n"))
	writemsg(  red("         and group files. Non-root compilation is disabled until then.\n"))
	writemsg(      "         Also note that non-root/wheel users will need to be added to\n")
	writemsg(      "         the portage group to do portage commands.\n")
	writemsg("\n")
	writemsg(      "         For the defaults, line 1 goes into passwd, and 2 into group.\n")
	writemsg(green("         portage:x:250:250:portage:/var/tmp/portage:/bin/false\n"))
	writemsg(green("         portage::250:portage\n"))
	writemsg("\n")

if (uid!=0) and (portage_gid not in os.getgroups()):
	writemsg("\n")
	writemsg(red("*** You are not in the portage group. You may experience cache problems\n"))
	writemsg(red("*** due to permissions preventing the creation of the on-disk cache.\n"))
	writemsg(red("*** Please add this user to the portage group if you wish to use portage.\n"))
	writemsg("\n")

incrementals=["USE","FEATURES","ACCEPT_KEYWORDS","ACCEPT_LICENSE","CONFIG_PROTECT_MASK","CONFIG_PROTECT","PRELINK_PATH","PRELINK_PATH_MASK"]
stickies=["KEYWORDS_ACCEPT","USE","CFLAGS","CXXFLAGS","MAKEOPTS","EXTRA_ECONF","EXTRA_EMAKE"]

def getcwd():
	"this fixes situations where the current directory doesn't exist"
	try:
		return os.getcwd()
	except:
		os.chdir("/")
		return "/"
getcwd()

def abssymlink(symlink):
	"This reads symlinks, resolving the relative symlinks, and returning the absolute."
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)

def suffix_array(array,suffix,doblanks=1):
	"""Appends a given suffix to each element in an Array/List/Tuple.
	Returns a List."""
	if type(array) not in [types.ListType, types.TupleType]:
		raise TypeError, "List or Tuple expected. Got %s" % type(array)
	newarray=[]
	for x in array:
		if x or doblanks:
			newarray.append(x + suffix)
		else:
			newarray.append(x)
	return newarray

def prefix_array(array,prefix,doblanks=1):
	"""Prepends a given prefix to each element in an Array/List/Tuple.
	Returns a List."""
	if type(array) not in [types.ListType, types.TupleType]:
		raise TypeError, "List or Tuple expected. Got %s" % type(array)
	newarray=[]
	for x in array:
		if x or doblanks:
			newarray.append(prefix + x)
		else:
			newarray.append(x)
	return newarray

dircache={}
def cacheddir (mypath, ignorecvs, ignorelist, EmptyOnError):

	if dircache.has_key(mypath):
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cached_mtime, list, ftype = -1, [], []
	if os.path.isdir(mypath):
		mtime = os.stat(mypath)[ST_MTIME]
	else:
		if EmptyOnError:
			return [], []
		return None, None
	if mtime != cached_mtime:
		list = os.listdir(mypath)
		ftype = []
		for x in list:
			if os.path.isfile(mypath+"/"+x):
				ftype.append(0)
			elif os.path.isdir(mypath+"/"+x):
				ftype.append(1)
			else:
				ftype.append(2)
		dircache[mypath] = mtime, list, ftype

	ret_list = []
	ret_ftype = []
	for x in range(0, len(list)):
		if not ((list[x] in ignorelist) or \
			(ignorecvs and (len(list[x]) > 2) and 
			(list[x][:2]==".#"))):
				ret_list.append(list[x])
				ret_ftype.append(ftype[x])

	return ret_list, ret_ftype
		

def listdir (mypath,
			 recursive=False,
			 filesonly=False,
			 ignorecvs=False,
			 ignorelist=[],
			 EmptyOnError=False):

	list, ftype = cacheddir(mypath, ignorecvs, ignorelist, EmptyOnError)

	if not filesonly and not recursive:
		return list

	if recursive:
		x=0
		while x<len(ftype):
			if ftype[x]==1 and \
			   not (ignorecvs and (len(list[x])>=3) and (("/"+list[x][-3:])=="/CVS")) and \
				 not (ignorecvs and (len(list[x])>=4) and (("/"+list[x][-4:])=="/.svn")):

				l,f = cacheddir(mypath+"/"+list[x],
								  ignorecvs,
								  ignorelist,
								  EmptyOnError)
								  
				l=l[:]
				for y in range(0,len(l)):
					l[y]=list[x]+"/"+l[y]
				list=list+l
				ftype=ftype+f
			x=x+1
	if filesonly:
		rlist=[]
		for x in range(0,len(ftype)):
			if ftype[x]==0:
				rlist=rlist+[list[x]]
	else:
		rlist=list
			
	return rlist

prelink_capable=0
try:
	import fchksum
	def perform_checksum(filename, calc_prelink=prelink_capable):
		if calc_prelink and prelink_capable:
			# Create non-prelinked temporary file to md5sum.
			mylock = lockfile("/tmp/portage-prelink.tmp", wantnewlockfile=1)
			prelink_tmpfile="/tmp/portage-prelink.tmp"
			try:
				shutil.copy2(filename,prelink_tmpfile)
			except Exception,e:
				writemsg("!!! Unable to copy file '"+str(filename)+"'.\n")
				writemsg("!!! "+str(e)+"\n")
				sys.exit(1)
			spawn("/usr/sbin/prelink --undo "+prelink_tmpfile+" &>/dev/null", settings, free=1)
			retval = fchksum.fmd5t(prelink_tmpfile)
			os.unlink(prelink_tmpfile)
			unlockfile(mylock)
			return retval
		else:
			return fchksum.fmd5t(filename)
except ImportError:
	import md5
	def perform_checksum(filename, calc_prelink=prelink_capable):
		mylock = lockfile("/tmp/portage-prelink.tmp", wantnewlockfile=1)
		prelink_tmpfile="/tmp/portage-prelink.tmp"
		myfilename=filename
		if calc_prelink and prelink_capable:
			# Create non-prelinked temporary file to md5sum.
			# Raw data is returned on stdout, errors on stderr.
			# Non-prelinks are just returned.
			try:
				shutil.copy2(filename,prelink_tmpfile)
			except Exception,e:
				writemsg("!!! Unable to copy file '"+str(filename)+"'.\n")
				writemsg("!!! "+str(e)+"\n")
				sys.exit(1)
			spawn("/usr/sbin/prelink --undo "+prelink_tmpfile+" &>/dev/null", settings, free=1)
			myfilename=prelink_tmpfile

		f = open(myfilename, 'rb')
		blocksize=32768
		data = f.read(blocksize)
		size = 0L
		sum = md5.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		if calc_prelink and prelink_capable:
			os.unlink(prelink_tmpfile)
		unlockfile(mylock)
		return (sum.hexdigest(),size)

starttime=long(time.time())
features=[]

def exithandler(signum,frame):
	"""Handles ^C interrupts in a sane manner"""
	global features,secpass
	#remove temp sandbox files
#	if (secpass==2) and ("sandbox" in features):
#		mypid=os.fork()
#		if mypid==0:
#			myargs=[]
#			mycommand="/usr/lib/portage/bin/testsandbox.sh"
#			myargs=["testsandbox.sh","0"]
#			myenv={}
#			os.execve(mycommand,myargs,myenv)
#			os._exit(1)
#			sys.exit(1)
#		retval=os.waitpid(mypid,0)[1]
#		if retval==0:
#			if os.path.exists("/tmp/sandboxpids.tmp"):
#				os.unlink("/tmp/sandboxpids.tmp")
	# 0=send to *everybody* in process group
	portageexit()
	atexit.register(None)
	signal.signal(signum, signal.SIG_DFL)
	os.kill(0,signum)
	sys.exit(1)

def tokenize(mystring):
	"""breaks a string like 'foo? (bar) oni? (blah (blah))'
	into embedded lists; returns None on paren mismatch"""

	# This function is obsoleted.
	# Use dep_parenreduce

	newtokens=[]
	curlist=newtokens
	prevlists=[]
	level=0
	accum=""
	for x in mystring:
		if x=="(":
			if accum:
				curlist.append(accum)
				accum=""
			prevlists.append(curlist)
			curlist=[]
			level=level+1
		elif x==")":
			if accum:
				curlist.append(accum)
				accum=""
			if level==0:
				writemsg("!!! tokenizer: Unmatched left parenthesis in:\n'"+str(mystring)+"'\n")
				return None
			newlist=curlist
			curlist=prevlists.pop()
			curlist.append(newlist)
			level=level-1
		elif x in string.whitespace:
			if accum:
				curlist.append(accum)
				accum=""
		else:
			accum=accum+x
	if accum:
		curlist.append(accum)
	if (level!=0):
		writemsg("!!! tokenizer: Exiting with unterminated parenthesis in:\n'"+str(mystring)+"'\n")
		return None
	return newtokens

def flatten(mytokens):
	"""this function now turns a [1,[2,3]] list into
	a [1,2,3] list and returns it."""
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
		if myparent and (not myparent in self.dict[mykey][1]):
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
	
	def allnodes(self):
		"returns all nodes in the dictionary"
		return self.dict.keys()
	
	def firstzero(self):
		"returns first node with zero references, or NULL if no such node exists"
		for x in self.okeys:
			if self.dict[x][0]==0:
				return x
		return None

	def depth(self, mykey):
		depth=0
		while (self.dict[mykey][1]):
			depth=depth+1
			mykey=self.dict[mykey][1][0]
		return depth

	def allzeros(self):
		"returns all nodes with zero references, or NULL if no such node exists"
		zerolist = []
		for x in self.dict.keys():
			if self.dict[x][0]==0:
				zerolist.append(x)
		return zerolist

	def hasallzeros(self):
		"returns 0/1, Are all nodes zeros? 1 : 0"
		zerolist = []
		for x in self.dict.keys():
			if self.dict[x][0]!=0:
				return 0
		return 1

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

def env_update(makelinks=1):
	global root
	if not os.path.exists(root+"etc/env.d"):
		prevmask=os.umask(0)
		os.makedirs(root+"etc/env.d",0755)
		os.umask(prevmask)
	fns=listdir(root+"etc/env.d",EmptyOnError=1)
	fns.sort()
	pos=0
	while (pos<len(fns)):
		if len(fns[pos])<=2:
			del fns[pos]
			continue
		if (fns[pos][0] not in string.digits) or (fns[pos][1] not in string.digits):
			del fns[pos]
			continue
		pos=pos+1

	specials={
	  "KDEDIRS":[],"PATH":[],"CLASSPATH":[],"LDPATH":[],"MANPATH":[],
		"INFODIR":[],"INFOPATH":[],"ROOTPATH":[],"CONFIG_PROTECT":[],
		"CONFIG_PROTECT_MASK":[],"PRELINK_PATH":[],"PRELINK_PATH_MASK":[],
		"PYTHONPATH":[], "ADA_INCLUDE_PATH":[], "ADA_OBJECTS_PATH":[]
	}
	colon_seperated = [
		"ADA_INCLUDE_PATH", "ADA_OBJECTS_PATH",
		"LDPATH",           "PATH",
		"PRELINK_PATH",     "PRELINK_PATH_MASK",
		"PYTHON_PATH",
	]
	
	env={}

	for x in fns:
		# don't process backup files
		if x[-1]=='~' or x[-4:]==".bak":
			continue
		myconfig=getconfig(root+"etc/env.d/"+x)
		if myconfig==None:
			writemsg("!!! Parsing error in "+str(root)+"etc/env.d/"+str(x)+"\n")
			#parse error
			continue
		# process PATH, CLASSPATH, LDPATH
		for myspec in specials.keys():
			if myconfig.has_key(myspec):
				if myspec in colon_seperated:
					specials[myspec].extend(string.split(varexpand(myconfig[myspec]),":"))
				else:
					specials[myspec].append(varexpand(myconfig[myspec]))
				del myconfig[myspec]
		# process all other variables
		for myenv in myconfig.keys():
			env[myenv]=varexpand(myconfig[myenv])
			
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
	#	os.rename(root+"etc/ld.so.conf",root+"etc/ld.so.conf.bak")
	# Where is the new ld.so.conf generated? (achim)
	else:
		oldld=None

	ld_cache_update=False
	newld=specials["LDPATH"]
	if (oldld!=newld):
		#ld.so.conf needs updating and ldconfig needs to be run
		myfd=open(root+"etc/ld.so.conf","w")
		myfd.write("# ld.so.conf autogenerated by env-update; make all changes to\n")
		myfd.write("# contents of /etc/env.d directory\n")
		for x in specials["LDPATH"]:
			myfd.write(x+"\n")
		myfd.close()
		ld_cache_update=True

	# Update prelink.conf if we are prelink-enabled
	if prelink_capable:
		newprelink=open(root+"etc/prelink.conf","w")
		newprelink.write("# prelink.conf autogenerated by env-update; make all changes to\n")
		newprelink.write("# contents of /etc/env.d directory\n")
	
		for x in ["/bin","/sbin","/usr/bin","/usr/sbin","/lib","/usr/lib"]:
			newprelink.write("-l "+x+"\n");
		for x in specials["LDPATH"]+specials["PATH"]+specials["PRELINK_PATH"]:
			if not x:
				continue
			plmasked=0
			for y in specials["PRELINK_PATH_MASK"]:
				if y[-1]!='/':
					y=y+"/"
				if y==x[0:len(y)]:
					plmasked=1
					break
			if not plmasked:
				newprelink.write("-h "+x+"\n")
		newprelink.close()

	if not mtimedb.has_key("ldpath"):
		mtimedb["ldpath"]={}

	for x in specials["LDPATH"]+['/usr/lib','/lib']:
		try:
			newldpathtime=os.stat(x)[ST_MTIME]
		except:
			newldpathtime=0
		if mtimedb["ldpath"].has_key(x):
			if mtimedb["ldpath"][x]==newldpathtime:
				pass
			else:
				mtimedb["ldpath"][x]=newldpathtime
				ld_cache_update=True
		else:
			mtimedb["ldpath"][x]=newldpathtime
			ld_cache_update=True

	if (ld_cache_update):
		# We can't update links if we haven't cleaned other versions first, as
		# an older package installed ON TOP of a newer version will cause ldconfig
		# to overwrite the symlinks we just made. -X means no links. After 'clean'
		# we can safely create links.
		writemsg(">>> Regenerating "+str(root)+"etc/ld.so.cache...\n")
		if makelinks:
			getstatusoutput("cd / ; /sbin/ldconfig -r "+root)
		else:
			getstatusoutput("cd / ; /sbin/ldconfig -X -r "+root)
			
	del specials["LDPATH"]

	penvnotice  = "# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.\n"
	penvnotice += "# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES\n"
	cenvnotice  = penvnotice[:];
	penvnotice += "# GO INTO /etc/profile NOT /etc/profile.env\n\n"
	cenvnotice += "# GO INTO /etc/csh.cshrc NOT /etc/csh.env\n\n"

	#create /etc/profile.env for bash support
	outfile=open(root+"/etc/profile.env","w")
	outfile.write(penvnotice)

	for path in specials.keys():
		if len(specials[path])==0:
			continue
		outstring="export "+path+"='"
		if path in ["CONFIG_PROTECT","CONFIG_PROTECT_MASK"]:
			for x in specials[path][:-1]:
				outstring += x+" "
		else:
			for x in specials[path][:-1]:
				outstring=outstring+x+":"
		outstring=outstring+specials[path][-1]+"'"
		outfile.write(outstring+"\n")
	
	#create /etc/profile.env
	for x in env.keys():
		if type(env[x])!=types.StringType:
			continue
		outfile.write("export "+x+"='"+env[x]+"'\n")
	outfile.close()
	
	#create /etc/csh.env for (t)csh support
	outfile=open(root+"/etc/csh.env","w")
	outfile.write(cenvnotice)
	
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
	if os.path.exists("/sbin/depscan.sh"):	
		spawn("/sbin/depscan.sh",settings,free=1)

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

def grab_stacked(basename, locations, handler, incrementals=[], incremental_lines=0, all_must_exist=0):
	final_list = None
	final_dict = None
	for loc in locations:
		stuff = handler(loc+"/"+basename)
		if type(stuff)==types.ListType:
			if final_list == None:
				final_list = []
			for y in stuff:
				if y:
					if incremental_lines and y[0]=='-':
						while y[1:] in final_list:
							del final_list[final_list.index(y[1:])]
					else:
						if y not in final_list:
							final_list.append(y)
		elif type(stuff)==types.DictType:
			if final_dict == None:
				final_dict = {}
			for y in stuff.keys():
				if not final_dict.has_key(y):
					final_dict[y] = stuff[y]
				else:
					for thing in stuff[y]:
						if thing:
							if thing[0] == '-':
								if thing[1:] in final_dict[y]:
									del final_dict[y][final_dict[y].index(thing[1:])]
							else:
								if thing not in final_dict[y]:
									final_dict[y].append(thing)
		elif (stuff == None):
			if all_must_exist:
				return None
		else:
			raise ValueError, "Unknown type for '%s'\n" % stuff

	if final_list == None:
		return final_dict
	else:
		return final_list

def grabdict(myfilename,juststrings=0,empty=0):
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
		if x[0] == "#":
			continue
		myline=string.split(x)
		if len(myline)<2 and empty==0:
			continue
		if len(myline)<1 and empty==1:
			continue
		if juststrings:
			newdict[myline[0]]=string.join(myline[1:])
		else:
			newdict[myline[0]]=myline[1:]
	return newdict

def grabdict_package(myfilename,juststrings=0):
	pkgs=grabdict(myfilename, juststrings, empty=1)
	for x in pkgs.keys():
		if not isvalidatom(x):
			del(pkgs[x])
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, x))
	return pkgs

def grabints(myfilename):
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
		if len(myline)!=2:
			continue
		newdict[myline[0]]=string.atoi(myline[1])
	return newdict

def writeints(mydict,myfilename):
	try:
		myfile=open(myfilename,"w")
	except IOError:
		return 0
	for x in mydict.keys():
		myfile.write(x+" "+`mydict[x]`+"\n")
	myfile.close()
	return 1

def writedict(mydict,myfilename,writekey=1):
	"""Writes out a dict to a file; writekey=0 mode doesn't write out
	the key and assumes all values are strings, not lists."""
	try:
		myfile=open(myfilename,"w")
	except IOError:
		writemsg("Failed to open file for writedict(): "+str(myfilename)+"\n")
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
	try:
		f=open(mycfg,'r')
	except IOError:
		return None
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
				writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n")
				raise Exception("ParseError: Unexpected EOF: "+str(mycfg)+": on/before line "+str(lex.lineno))
			else:
				return mykeys
		elif (equ!='='):
			#invalid token
			#lex.error_leader(self.filename,lex.lineno)
			if not tolerant:
				writemsg("!!! Invalid token (not \"=\") "+str(equ)+"\n")
				raise Exception("ParseError: Invalid token (not '='): "+str(mycfg)+": line "+str(lex.lineno))
			else:
				return mykeys
		val=lex.get_token()
		if (val==''):
			#unexpected end of file
			#lex.error_leader(self.filename,lex.lineno)
			if not tolerant:
				writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n")
				raise Exception("ParseError: Unexpected EOF: "+str(mycfg)+": line "+str(lex.lineno))
			else:
				return mykeys
		mykeys[key]=varexpand(val,mykeys)
	return mykeys

#cache expansions of constant strings
cexpand={}
def varexpand(mystring,mydict={}):
	try:
		return cexpand[" "+mystring]
	except KeyError:
		pass
	"""
	new variable expansion code.  Removes quotes, handles \n, etc.
	This code is used by the configfile code, as well as others (parser)
	This would be a good bunch of code to port to C.
	"""
	numvars=0
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
			if (mystring[pos]=="\n"):
				#convert newlines to spaces
				newstring=newstring+" "
				pos=pos+1
			elif (mystring[pos]=="\\"):
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
				if mystring[pos]=="{":
					pos=pos+1
					braced=True
				else:
					braced=False
				myvstart=pos
				validchars=string.ascii_letters+string.digits+"_"
				while mystring[pos] in validchars:
					if (pos+1)>=len(mystring):
						if braced:
							cexpand[mystring]=""
							return ""
						else:
							pos=pos+1
							break
					pos=pos+1
				myvarname=mystring[myvstart:pos]
				if braced:
					if mystring[pos]!="}":
						cexpand[mystring]=""
						return ""
					else:
						pos=pos+1
				if len(myvarname)==0:
					cexpand[mystring]=""
					return ""
				numvars=numvars+1
				if mydict.has_key(myvarname):
					newstring=newstring+mydict[myvarname] 
			else:
				newstring=newstring+mystring[pos]
				pos=pos+1
		else:
			newstring=newstring+mystring[pos]
			pos=pos+1
	if numvars==0:
		cexpand[mystring]=newstring[1:]
	return newstring[1:]	

# returns a tuple.  (version[string], error[string])
# They are pretty much mutually exclusive.
# Either version is a string and error is none, or
# version is None and error is a string
#
def ExtractKernelVersion(base_dir):
	lines = []
	pathname = os.path.join(base_dir, 'Makefile')
	try:
		f = open(pathname, 'r')
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))

	try:
		for i in range(4):
			lines.append(f.readline())
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))
		
	lines = map(string.strip, lines)

	version = ''

	for line in lines:
		# split on the '=' then remove annoying whitespace
		items = string.split(line, '=')
		items = map(string.strip, items)
		if items[0] == 'VERSION' or \
			items[0] == 'PATCHLEVEL':
			version += items[1]
			version += "."
		elif items[0] == 'SUBLEVEL':
			version += items[1]
		elif items[0] == 'EXTRAVERSION' and \
			items[-1] != items[0]:
			version += items[1]

	return (version,None)

aumtime=0

def autouse(myvartree,use_cache=1):
	"returns set of USE variables auto-enabled due to packages being installed"
	global usedefaults
	if profiledir==None:
		return ""
	myusevars=""
	for myuse in usedefaults:
		mydep = string.join(usedefaults[myuse])
		#check dependencies; tell depcheck() to ignore settings["USE"] since we are still forming it.
		myresult=dep_check(mydep,myvartree.dbapi,None,use="no",use_cache=use_cache)
		if myresult[0]==1 and not myresult[1]:
			#deps satisfied, add USE variable...
			myusevars=myusevars+" "+myuse
	return myusevars

def check_config_instance(test):
	if not test or (str(test.__class__) != 'portage.config'):
		raise TypeError, "Invalid type for config object: %s" % test.__class__

class config:
	def __init__(self, clone=None, mycpv=None, config_profile_path=None, config_incrementals=None):

		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []

		if clone:
			self.incrementals = copy.deepcopy(clone.incrementals)
			self.profile_path = copy.deepcopy(clone.profile_path)

			self.module_priority = copy.deepcopy(clone.module_priority)
			self.modules         = copy.deepcopy(clone.modules)

			self.packages = copy.deepcopy(clone.packages)
			self.virtuals = copy.deepcopy(clone.virtuals)

			self.use_defs = copy.deepcopy(clone.use_defs)
			self.usemask  = copy.deepcopy(clone.usemask)

			self.configlist = copy.deepcopy(clone.configlist)
			self.configlist[-1] = os.environ.copy()
			self.configdict = { "globals":   self.configlist[0],
			                    "defaults":  self.configlist[1],
			                    "conf":      self.configlist[2],
			                    "pkg":       self.configlist[3],
			                    "auto":      self.configlist[4],
			                    "backupenv": self.configlist[5],
			                    "env":       self.configlist[6] }
			self.backupenv  = copy.deepcopy(clone.backupenv)
			self.pusedict   = copy.deepcopy(clone.pusedict)
			self.categories = copy.deepcopy(clone.categories)
			self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
			self.pmaskdict = copy.deepcopy(clone.pmaskdict)
			self.punmaskdict = copy.deepcopy(clone.punmaskdict)
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.lookuplist = copy.deepcopy(clone.lookuplist)
			self.uvlist     = copy.deepcopy(clone.uvlist)
		else:
			if not config_profile_path:
				global profiledir
				writemsg("config_profile_path not specified to class config\n")
				self.profile_path = profiledir[:]
			else:
				self.profile_path = config_profile_path[:]

			if not config_incrementals:
				global incrementals
				writemsg("incrementals not specified to class config\n")
				self.incrementals = copy.deepcopy(incrementals)
			else:
				self.incrementals = copy.deepcopy(config_incrementals)
			
			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"]    = getconfig("/etc/portage/modules")
			if self.modules["user"] == None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "portage_db_flat.database",
				"portdbapi.auxdbmodule":  "portage_db_flat.database",
				"eclass_cache.dbmodule":  "portage_db_cpickle.database",
			}
			
			self.usemask=[]
			self.configlist=[]
			self.backupenv={}
			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ globals, defaults, conf, pkg, auto, backupenv (incrementals), origenv ]

			# The symlink might not exist or might not be a symlink.
			try:
				self.profiles=[abssymlink(self.profile_path)]
			except:
				self.profiles=[self.profile_path]

			mypath = self.profiles[0]
			while os.path.exists(mypath+"/parent"):
				mypath = os.path.normpath(mypath+"///"+grabfile(mypath+"/parent")[0])
				if os.path.exists(mypath):
					self.profiles.insert(0,mypath)

			if os.environ.has_key("PORTAGE_CALLER") and os.environ["PORTAGE_CALLER"] == "repoman":
				pass
			else:
				if os.path.exists("/etc/portage/profile"):
					self.profiles.append("/etc/portage/profile")

			self.packages = grab_stacked("packages", self.profiles, grabfile, incremental_lines=1)
			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				mycatpkg=dep_getkey(x)
				if not self.prevmaskdict.has_key(mycatpkg):
					self.prevmaskdict[mycatpkg]=[x]
				else:
					self.prevmaskdict[mycatpkg].append(x)

			# get virtuals
			self.virtuals = self.getvirtuals('/')

			# get profile-masked use flags -- INCREMENTAL Child over parent
			self.usemask  = grab_stacked("use.mask", self.profiles, grabfile, incremental_lines=1)
			self.use_defs = grab_stacked("use.defaults", self.profiles, grabdict)

			try:
				self.mygcfg  = grab_stacked("make.globals", self.profiles+["/etc"], getconfig)
				if self.mygcfg == None:
					self.mygcfg = {}
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
				writemsg("!!! Errors in this file should be reported on bugs.gentoo.org.\n")
				sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.mygcfg = {}
			if self.profiles:
				try:
					self.mygcfg = grab_stacked("make.defaults", self.profiles, getconfig)
					if self.mygcfg == None:
						self.mygcfg = {}
				except Exception, e:
					writemsg("!!! %s\n" % (e))
					writemsg("!!! 'rm -Rf /usr/portage/profiles; emerge sync' may fix this. If it does\n")
					writemsg("!!! not then please report this to bugs.gentoo.org and, if possible, a dev\n")
					writemsg("!!! on #gentoo (irc.freenode.org)\n")
					sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			try:
				self.mygcfg=getconfig("/etc/make.conf")
				if self.mygcfg == None:
					self.mygcfg = {}
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
				sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

			#backup-env (for recording our calculated incremental variables:)
			self.backupenv = os.environ.copy()
			self.configlist.append(self.backupenv) # XXX Why though?
			self.configdict["backupenv"]=self.configlist[-1]

			self.configlist.append(os.environ.copy())
			self.configdict["env"]=self.configlist[-1]


			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			if os.environ.has_key("PORTAGE_CALLER") and os.environ["PORTAGE_CALLER"] == "repoman":
				# repoman shouldn't use local settings.
				locations = [self["PORTDIR"] + "/profiles"]
				self.pusedict = {}
				self.pkeywordsdict = {}
				self.punmaskdict = {}
			else:
				locations = [self["PORTDIR"] + "/profiles", "/etc/portage"]

				# Never set anything in this. It's for non-originals.
				self.pusedict=grabdict_package("/etc/portage/package.use")

				#package.keywords
				pkgdict=grabdict_package("/etc/portage/package.keywords")
				for key in pkgdict.keys():
					# default to ~arch if no specific keyword is given
					if not pkgdict[key]:
						mykeywordlist = []
						groups = self.configdict["defaults"]["ACCEPT_KEYWORDS"].split()
						for keyword in groups:
							if not keyword[0] in "~-":
								mykeywordlist.append("~"+keyword)
						pkgdict[key] = mykeywordlist
				self.pkeywordsdict = pkgdict

				#package.unmask
				pkgunmasklines = grabdict_package("/etc/portage/package.unmask")
				self.punmaskdict = {}
				for x in pkgunmasklines:
					mycatpkg=dep_getkey(x)
					if self.punmaskdict.has_key(mycatpkg):
						self.punmaskdict[mycatpkg].append(x)
					else:
						self.punmaskdict[mycatpkg]=[x]

			#getting categories from an external file now
			self.categories = grab_stacked("categories", locations, grabfile)
					
			#package.mask
			pkgmasklines = grab_stacked("package.mask", locations, grabdict_package)
			self.pmaskdict = {}
			for x in pkgmasklines:
				mycatpkg=dep_getkey(x)
				if self.pmaskdict.has_key(mycatpkg):
					self.pmaskdict[mycatpkg].append(x)
				else:
					self.pmaskdict[mycatpkg]=[x]

		self.lookuplist=self.configlist[:]
		self.lookuplist.reverse()
	
		useorder=self["USE_ORDER"]
		if not useorder:
			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			useorder="env:pkg:conf:auto:defaults"
		useordersplit=useorder.split(":")

		self.uvlist=[]
		for x in useordersplit:
			if self.configdict.has_key(x):
				if "PKGUSE" in self.configdict[x].keys():
					del self.configdict[x]["PKGUSE"] # Delete PkgUse, Not legal to set.
				#prepend db to list to get correct order
				self.uvlist[0:0]=[self.configdict[x]]		

		self.configdict["env"]["PORTAGE_GID"]=str(portage_gid)
		self.backupenv["PORTAGE_GID"]=str(portage_gid)

		if not self["PORTAGE_CACHEDIR"]:
			#the auxcache is the only /var/cache/edb/ entry that stays at / even when "root" changes.
			self["PORTAGE_CACHEDIR"]="/var/cache/edb/dep/"
			self.backup_changes("PORTAGE_CACHEDIR")

		overlays = string.split(self["PORTDIR_OVERLAY"])
		if overlays:
			new_ov=[]
			for ov in overlays:
				ov=os.path.normpath(ov)
				if os.path.isdir(ov):
					new_ov.append(ov)
				else:
					writemsg(red("!!! Invalid PORTDIR_OVERLAY (not a dir): "+ov+"\n"))
			self["PORTDIR_OVERLAY"] = string.join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")

		self.regenerate()
		if mycpv:
			self.setcpv(mycpv)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		return load_mod(best_mod)
			
	def lock(self):
		self.locked = 1

	def unlock(self):
		self.locked = 0
	
	def modifying(self):
		if self.locked:
			raise Exception, "Configuration is locked."
	
	def backup_changes(self,key=None):
		if key and self.configdict["env"].has_key(key):
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError, "No such key defined in environment: %s" % key
	
	def reset(self,keeping_pkg=0,use_cache=1):
		"reset environment to original settings"
		for x in self.configlist[-1].keys():
			if x not in self.backupenv.keys():
				del self.configlist[-1][x]
		for x in self.backupenv.keys():
			self.configdict["env"][x] = self.backupenv[x]
		else:
			del self.configdict["env"][x]
		self.modifiedkeys = []
		if not keeping_pkg:
			for x in self.configdict["pkg"].keys():
				del self.configdict["pkg"][x]
		self.regenerate(use_cache=use_cache)

	def load_infodir(self,infodir):
		if self.configdict.has_key("pkg"):
			for x in self.configdict["pkg"].keys():
				del self.configdict["pkg"][x]
		else:
			writemsg("No pkg setup for settings instance?\n")
			sys.exit(17)
		
		if os.path.exists(infodir):
			if os.path.exists(infodir+"/environment"):
				self.configdict["pkg"]["PORT_ENV_FILE"] = infodir+"/environment"

			myre = re.compile('^[A-Z]+$')
			for filename in listdir(infodir,filesonly=1,EmptyOnError=1):
				if myre.match(filename):
					try:
						mydata = string.strip(open(infodir+"/"+filename).read())
						if len(mydata)<2048:
							if filename == "USE":
								self.configdict["pkg"][filename] = "-* "+mydata
							else:
								self.configdict["pkg"][filename] = mydata
					except:
						writemsg("!!! Unable to read file: %s\n" % infodir+"/"+filename)
						pass
			return 1
		return 0

	def setcpv(self,mycpv,use_cache=1):
		self.modifying()
		self.mycpv = mycpv
		self.pusekey = best_match_to_list(self.mycpv, self.pusedict.keys())
		if self.pusekey:
			self.puse = string.join(self.pusedict[self.pusekey])
		else:
			self.puse = ""
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE
		self.reset(keeping_pkg=1,use_cache=use_cache)

	def regenerate(self,useonly=0,use_cache=1):
		global incrementals,usesplit,profiledir

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals=incrementals
		for mykey in myincrementals:
			if mykey=="USE":
				mydbs=self.uvlist
				# XXX Global usage of db... Needs to go away somehow.
				if db.has_key(root) and db[root].has_key("vartree"):
					self.configdict["auto"]["USE"]=autouse(db[root]["vartree"],use_cache=use_cache)
				else:
					self.configdict["auto"]["USE"]=""
			else:
				mydbs=self.configlist[:-1]

			myflags=[]
			for curdb in mydbs:
				if not curdb.has_key(mykey):
					continue
				#variables are already expanded
				mysplit=curdb[mykey].split()
				
				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags=[]
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(red("USE flags should not start with a '+': %s\n" % x))
						x=x[1:]

					if (x[0]=="-"):
						if (x[1:] in myflags):
							# Unset/Remove it.
							del myflags[myflags.index(x[1:])]
						continue

					# We got here, so add it now.
					if x not in myflags:
						myflags.append(x)

			myflags.sort()
			#store setting in last element of configlist, the original environment:
			self.configlist[-1][mykey]=string.join(myflags," ")
			del myflags

		#cache split-up USE var in a global
		usesplit=[]

		for x in string.split(self.configlist[-1]["USE"]):
			if x not in self.usemask:
				usesplit.append(x)

		if self.has_key("USE_EXPAND"):
			for var in string.split(self["USE_EXPAND"]):
				if self.has_key(var):
					for x in string.split(self[var]):
						mystr = string.lower(var)+"_"+x
						if mystr not in usesplit:
							usesplit.append(mystr)

		# Pre-Pend ARCH variable to USE settings so '-*' in env doesn't kill arch.
		if profiledir:
			if self.configdict["defaults"].has_key("ARCH"):
				if self.configdict["defaults"]["ARCH"]:
					if self.configdict["defaults"]["ARCH"] not in usesplit:
						usesplit.insert(0,self.configdict["defaults"]["ARCH"])

		self.configlist[-1]["USE"]=string.join(usesplit," ")


	def getvirtuals(self, myroot):
		myvirts     = {}

		# This breaks catalyst/portage when setting to a fresh/empty root.
		# Virtuals cannot be calculated because there is nothing to work
		# from. So the only ROOT prefixed dir should be local configs.
		#myvirtdirs  = prefix_array(self.profiles,myroot+"/")
		myvirtdirs = copy.deepcopy(self.profiles)

		# repoman doesn't need local virtuals.
		if os.environ.has_key("PORTAGE_CALLER") and os.environ["PORTAGE_CALLER"] == "repoman":
			pass
		else:
			myvirtdirs.insert(0,myroot+"/var/cache/edb")

		return grab_stacked("virtuals",myvirtdirs,grabdict)
	
	def __getitem__(self,mykey):
		if mykey=="CONFIG_PROTECT_MASK":
			suffix=" /etc/env.d"
		else:
			suffix=""
		for x in self.lookuplist:
			if x == None:
				writemsg("!!! lookuplist is null.\n")
			elif x.has_key(mykey):
				return x[mykey]+suffix
		return suffix

	def has_key(self,mykey):
		for x in self.lookuplist:
			if x.has_key(mykey):
				return 1 
		return 0
	
	def keys(self):
		mykeys=[]
		for x in self.lookuplist:
			for y in x.keys():
				if y not in mykeys:
					mykeys.append(y)
		return mykeys

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		self.modifying()
		self.modifiedkeys += [mykey]
		self.configdict["env"][mykey]=myvalue
	
	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		for x in self.keys(): 
			mydict[x]=self[x]
		if not mydict.has_key("HOME") and mydict.has_key("BUILD_PREFIX"):
			writemsg("*** HOME not set. Setting to "+mydict["BUILD_PREFIX"]+"\n")
			mydict["HOME"]=mydict["BUILD_PREFIX"]
		return mydict

# XXX fd_pipes should be a way for a process to communicate back.
# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring,mysettings,debug=0,free=0,droppriv=0,fd_pipes=None):
	"""spawn a subprocess with optional sandbox protection, 
	depending on whether sandbox is enabled.  The "free" argument,
	when set to 1, will disable sandboxing.  This allows us to 
	spawn processes that are supposed to modify files outside of the
	sandbox.  We can't use os.system anymore because it messes up
	signal handling.  Using spawn allows our Portage signal handler
	to work."""

	check_config_instance(mysettings)

	droppriv=(droppriv and ("userpriv" in features) and \
	         ("nouserpriv" not in string.split(mysettings["RESTRICT"])))
	
	myargs=[]
	if ("sandbox" in features) and (not free):
		mycommand="/usr/lib/portage/bin/sandbox"
		myargs=["["+mysettings["PF"]+"] sandbox",mystring]
	else:
		mycommand="/bin/bash"
		if debug:
			myargs=["["+mysettings["PF"]+"] bash","-x","-c",mystring]
		else:
			myargs=["["+mysettings["PF"]+"] bash","-c",mystring]

	mypid=os.fork()
	if mypid==0:
		if fd_pipes:
			os.dup2(fd_pipes[0], 0) # stdin  -- (Read)/Write
			os.dup2(fd_pipes[1], 1) # stdout -- Read/(Write)
			os.dup2(fd_pipes[2], 2) # stderr -- Read/(Write)
		if droppriv:
			if portage_gid and portage_uid:
				#drop root privileges, become the 'portage' user
				os.setgid(portage_gid)
				os.setgroups([portage_gid])
				os.setuid(portage_uid)
				os.umask(002)
				try:
					os.chown("/tmp/sandboxpids.tmp",uid,portage_gid)
					os.chmod("/tmp/sandboxpids.tmp",0664)
				except:
					pass
			else:
				writemsg("portage: Unable to drop root for "+str(mystring)+"\n")

		os.execve(mycommand,myargs,mysettings.environ())
		# If the execve fails, we need to report it, and exit
		# *carefully* --- report error here
		os._exit(1)
		sys.exit(1)
		return # should never get reached

	retval=os.waitpid(mypid,0)[1]
	if (retval & 0xff)==0:
		return (retval >> 8) # return exit code
	else:
		return ((retval & 0xff) << 8) # interrupted by signal

def fetch(myuris, mysettings, listonly=0, fetchonly=0):
	"fetch files.  Will use digest file if available."
	if ("mirror" in features) and ("nomirror" in mysettings["RESTRICT"].split()):
		print ">>> \"mirror\" mode and \"nomirror\" restriction enabled; skipping fetch."
		return 1
	global thirdpartymirrors
	
	check_config_instance(mysettings)
	
	custommirrors=grabdict("/etc/portage/mirrors")

	mymirrors=[]
	
	# local mirrors are always added
	if custommirrors.has_key("local"):
		mymirrors += custommirrors["local"]

	if ("nomirror" in mysettings["RESTRICT"].split()):
		# We don't add any mirrors.
		pass
	else:
		for x in mysettings["GENTOO_MIRRORS"].split():
			if x:
				if x[-1] == '/':
					mymirrors += [x[:-1]]
				else:
					mymirrors += [x]
	
	fetchcommand=mysettings["FETCHCOMMAND"]
	resumecommand=mysettings["RESUMECOMMAND"]
	fetchcommand=string.replace(fetchcommand,"${DISTDIR}",mysettings["DISTDIR"])
	resumecommand=string.replace(resumecommand,"${DISTDIR}",mysettings["DISTDIR"])
	mydigests=None
	digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]
	if os.path.exists(digestfn):
		myfile=open(digestfn,"r")
		mylines=myfile.readlines()
		mydigests={}
		for x in mylines:
			myline=string.split(x)
			if len(myline)<4:
				#invalid line
				print "!!! The digest",digestfn,"appears to be corrupt.  Aborting."
				return 0
			try:
				mydigests[myline[2]]={"md5":myline[1],"size":string.atol(myline[3])}
			except ValueError:
				print "!!! The digest",digestfn,"appears to be corrupt.  Aborting."

	fsmirrors = []
	for x in range(len(mymirrors)-1,-1,-1):
		if mymirrors[x] and mymirrors[x][0]=='/':
			fsmirrors += [mymirrors[x]]
			del mymirrors[x]

	for myuri in myuris:
		myfile=os.path.basename(myuri)
		try:
			destdir = mysettings["DISTDIR"]+"/"
			if not os.path.exists(destdir+myfile):
				for mydir in fsmirrors:
					if os.path.exists(mydir+"/"+myfile):
						writemsg("Local mirror has file: %s\n" % myfile)
						shutil.copyfile(mydir+"/"+myfile,destdir+"/"+myfile)
						break
		except (OSError,IOError),e:
			# file does not exist
			print "!!!",myfile,"not found in",mysettings["DISTDIR"]+"."
			gotit=0

	if "fetch" in mysettings["RESTRICT"].split():
		# fetch is restricted.	Ensure all files have already been downloaded; otherwise,
		# print message and exit.
		gotit=1
		for myuri in myuris:
			myfile=os.path.basename(myuri)
			try:
				mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
			except (OSError,IOError),e:
				# file does not exist
				print "!!!",myfile,"not found in",mysettings["DISTDIR"]+"."
				gotit=0
		if not gotit:
			print
			print "!!!",mysettings["CATEGORY"]+"/"+mysettings["PF"],"has fetch restriction turned on."
			print "!!! This probably means that this ebuild's files must be downloaded"
			print "!!! manually.  See the comments in the ebuild for more information."
			print
			spawn("/usr/sbin/ebuild.sh nofetch",mysettings)
			return 0
		return 1
	locations=mymirrors[:]
	filedict={}
	for myuri in myuris:
		myfile=os.path.basename(myuri)
		if not filedict.has_key(myfile):
			filedict[myfile]=[]
			for y in range(0,len(locations)):
				filedict[myfile].append(locations[y]+"/distfiles/"+myfile)
		if myuri[:9]=="mirror://":
			eidx = myuri.find("/", 9)
			if eidx != -1:
				mirrorname = myuri[9:eidx]
				# Try user-defined mirrors first
				if custommirrors.has_key(mirrorname):
					for cmirr in custommirrors[mirrorname]:
						filedict[myfile].append(cmirr+"/"+myuri[eidx+1:])
						# remove the mirrors we tried from the list of official mirrors
						if cmirr.strip() in thirdpartymirrors[mirrorname]:
							thirdpartymirrors[mirrorname].remove(cmirr)
				# now try the official mirrors
				if thirdpartymirrors.has_key(mirrorname):
					try:
						shuffle(thirdpartymirrors[mirrorname])
					except:
						writemsg(red("!!! YOU HAVE A BROKEN PYTHON/GLIBC.\n"))
						writemsg(    "!!! You are most likely on a pentium4 box and have specified -march=pentium4\n")
						writemsg(    "!!! or -fpmath=sse2. GCC was generating invalid sse2 instructions in versions\n")
						writemsg(    "!!! prior to 3.2.3. Please merge the latest gcc or rebuid python with either\n")
						writemsg(    "!!! -march=pentium3 or set -mno-sse2 in your cflags.\n\n\n")
						time.sleep(10)
						
					for locmirr in thirdpartymirrors[mirrorname]:
						filedict[myfile].append(locmirr+"/"+myuri[eidx+1:])		
		else:
				filedict[myfile].append(myuri)
	for myfile in filedict.keys():
		if listonly:
			fetched=0
			writemsg("\n")
		for loc in filedict[myfile]:
			if listonly:
				writemsg(loc+" ")
				continue
			try:
				mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
				if mydigests!=None and mydigests.has_key(myfile):
					#if we have the digest file, we know the final size and can resume the download.
					if mystat[ST_SIZE]<mydigests[myfile]["size"]:
						fetched=1
					else:
						#we already have it downloaded, skip.
						#if our file is bigger than the recorded size, digestcheck should catch it.
						if not fetchonly:
							fetched=2
						else:
							# Check md5sum's at each fetch for fetchonly.
							mymd5=perform_md5(mysettings["DISTDIR"]+"/"+myfile)
							if mymd5 != mydigests[myfile]["md5"]:
								writemsg("!!! Previously fetched file: "+str(myfile)+" MD5 FAILED! Refetching...\n")
								os.unlink(mysettings["DISTDIR"]+"/"+myfile)
								fetched=0
							else:
								writemsg(">>> Previously fetched file: "+str(myfile)+" MD5 ;-)\n")
								fetched=2
								break #No need to keep looking for this file, we have it!
				else:
					#we don't have the digest file, but the file exists.  Assume it is fully downloaded.
					fetched=2
			except (OSError,IOError),e:
				writemsg("An exception was caught(1)...\nFailing the download: %s.\n" % (str(e)),1)
				fetched=0
			if fetched!=2:
				#we either need to resume or start the download
				#you can't use "continue" when you're inside a "try" block
				if fetched==1:
					#resume mode:
					writemsg(">>> Resuming download...\n")
					locfetch=resumecommand
				else:
					#normal mode:
					locfetch=fetchcommand
				writemsg(">>> Downloading "+str(loc)+"\n")
				myfetch=string.replace(locfetch,"${URI}",loc)
				myfetch=string.replace(myfetch,"${FILE}",myfile)
				myret=spawn(myfetch,mysettings,free=1)
				
				if mydigests!=None and mydigests.has_key(myfile):
					try:
						mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
						# no exception?  file exists. let digestcheck() report
						# an appropriately for size or md5 errors
						os.chown(mysettings["DISTDIR"]+"/"+myfile,os.getuid(),portage_gid)
						os.chmod(mysettings["DISTDIR"]+"/"+myfile,0664)
						if (mystat[ST_SIZE]<mydigests[myfile]["size"]):
							# Fetch failed... Try the next one... Kill 404 files though.
							if (mystat[ST_SIZE]<100000) and (len(myfile)>4) and not ((myfile[-5:]==".html") or (myfile[-4:]==".htm")):
								html404=re.compile("<title>.*(not found|404).*</title>",re.I|re.M)
								try:
									if html404.search(open(mysettings["DISTDIR"]+"/"+myfile).read()):
										try:
											os.unlink(mysettings["DISTDIR"]+"/"+myfile)
											writemsg(">>> Deleting invalid distfile. (Improper 404 redirect from server.)\n")
										except:
											pass
								except:
									pass
							continue
						if not fetchonly:
							fetched=2
							break
						else:
							# File is the correct size--check the MD5 sum for the fetched
							# file NOW, for those users who don't have a stable/continuous
							# net connection. This way we have a chance to try to download
							# from another mirror...
							mymd5=perform_md5(mysettings["DISTDIR"]+"/"+myfile)
							if mymd5 != mydigests[myfile]["md5"]:
								writemsg("!!! Fetched file: "+str(myfile)+" MD5 FAILED! Removing corrupt distfile...\n")
								os.unlink(mysettings["DISTDIR"]+"/"+myfile)
								fetched=0
							else:
								writemsg(">>> "+str(myfile)+" MD5 ;-)\n")
								fetched=2
								break
					except (OSError,IOError),e:
						writemsg("An exception was caught(2)...\nFailing the download: %s.\n" % (str(e)),1)
						fetched=0
				else:
					if not myret:
						fetched=2
						break
					elif mydigests!=None:
						writemsg("No digest file available and download failed.\n")

		if (fetched!=2) and not listonly:
			writemsg("!!! Couldn't download "+str(myfile)+". Aborting.\n")
			return 0
	return 1


def digestCreate(myfiles,basedir):
	"""Takes a list of files and the directory they are in and returns the
	dict of dict[filename]=[md5,size]
	returns None on error."""
	mydigests={}
	for x in myfiles:
		print "<<<",x
		myfile=os.path.normpath(basedir+"///"+x)
		if not os.access(myfile, os.R_OK):
			print "!!! Given file does not appear to be readable. Does it exist?"
			print "!!! File:",myfile
			return None
		mymd5=perform_md5(myfile)
		mysize=os.stat(myfile)[ST_SIZE]
		mydigests[x]=[mymd5,mysize]
	return mydigests


def digestgen(myarchives,mysettings,overwrite=1,manifestonly=0):
	"""generates digest file if missing.  Assumes all files are available.	If
	overwrite=0, the digest will only be created if it doesn't already exist."""

	# archive files
	basedir=mysettings["DISTDIR"]+"/"
	digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]

	# portage files -- p(ortagefiles)basedir
	pbasedir=mysettings["O"]+"/"
	manifestfn=pbasedir+"Manifest"

	if not manifestonly:
		if not os.path.isdir(mysettings["FILESDIR"]):
			os.makedirs(mysettings["FILESDIR"])
		mycvstree=cvstree.getentries(pbasedir, recursive=1)

		if ("cvs" in features) and os.path.exists(pbasedir+"/CVS"):
			if not cvstree.isadded(mycvstree,"files"):
				if "autoaddcvs" in features:
					print ">>> Auto-adding files/ dir to CVS..."
					spawn("cd "+pbasedir+"; cvs add files",mysettings,free=1)
				else:
					print "--- Warning: files/ is not added to cvs."

		if (not overwrite) and os.path.exists(digestfn):
			return 1

		print green(">>> Generating digest file...")
		mydigests=digestCreate(myarchives, basedir)
		if mydigests==None: # There was a problem, exit with an errorcode.
			return 0

		try:
			outfile=open(digestfn, "w+")
		except Exception, e:
			print "!!! Filesystem error skipping generation. (Read-Only?)"
			print "!!!",e
			return 0
		for myarchive in myarchives:
			mymd5=mydigests[myarchive][0]
			mysize=mydigests[myarchive][1]
			outfile.write("MD5 "+mymd5+" "+myarchive+" "+str(mysize)+"\n")	
		outfile.close()
		try:
			os.chown(digestfn,os.getuid(),portage_gid)
			os.chmod(digestfn,0664)
		except Exception,e:
			print e

	print green(">>> Generating manifest file...")
	mypfiles=listdir(pbasedir,recursive=1,filesonly=1,ignorecvs=1,EmptyOnError=1)
	if "Manifest" in mypfiles:
		del mypfiles[mypfiles.index("Manifest")]

	mydigests=digestCreate(mypfiles, pbasedir)
	if mydigests==None: # There was a problem, exit with an errorcode.
		return 0

	try:
		outfile=open(manifestfn, "w+")
	except Exception, e:
		print "!!! Filesystem error skipping generation. (Read-Only?)"
		print "!!!",e
		return 0
	for mypfile in mypfiles:
		mymd5=mydigests[mypfile][0]
		mysize=mydigests[mypfile][1]
		outfile.write("MD5 "+mymd5+" "+mypfile+" "+str(mysize)+"\n")	
	outfile.close()
	try:
		os.chown(manifestfn,os.getuid(),portage_gid)
		os.chmod(manifestfn,0664)
	except Exception,e:
		print e

	if "cvs" in features and os.path.exists(pbasedir+"/CVS"):
		mycvstree=cvstree.getentries(pbasedir, recursive=1)
		myunaddedfiles=""
		if not manifestonly and not cvstree.isadded(mycvstree,digestfn):
			if digestfn[:len(pbasedir)]==pbasedir:
				myunaddedfiles=digestfn[len(pbasedir):]+" "
			else:
				myunaddedfiles=digestfn+" "
		if not cvstree.isadded(mycvstree,manifestfn[len(pbasedir):]):
			if manifestfn[:len(pbasedir)]==pbasedir:
				myunaddedfiles+=manifestfn[len(pbasedir):]+" "
			else:
				myunaddedfiles+=manifestfn
		if myunaddedfiles:
			if "autoaddcvs" in features:
				print blue(">>> Auto-adding digest file(s) to CVS...")
				spawn("cd "+pbasedir+"; cvs add "+myunaddedfiles,mysettings,free=1)
			else:
				print "--- Warning: digests are not yet added into CVS."
	print darkgreen(">>> Computed message digests.")
	print
	return 1


def digestParseFile(myfilename):
	"""(filename) -- Parses a given file for entries matching:
	MD5 MD5_STRING_OF_HEX_CHARS FILE_NAME FILE_SIZE
	Ignores lines that do not begin with 'MD5' and returns a
	dict with the filenames as keys and [md5,size] as the values."""
	try:
		myfile=open(myfilename,"r")
		mylines=myfile.readlines()
	except:
		return None
	mydigests={}
	for x in mylines:
		myline=string.split(x)
		if len(myline)!=4:
			#invalid line
			continue
		if myline[0]!='MD5': # Ignore non-md5 lines.
			continue
		mydigests[myline[2]]=[myline[1],myline[3]]
	return mydigests

# XXXX strict was added here to fix a missing name error.
# XXXX It's used below, but we're not paying attention to how we get it?
def digestCheckFiles(myfiles, mydigests, basedir, note="", strict=0):
	"""(fileslist, digestdict, basedir) -- Takes a list of files and a dict
	of their digests and checks the digests against the indicated files in
	the basedir given. Returns 1 only if all files exist and match the md5s.
	"""
	for x in myfiles:
		if not mydigests.has_key(x):
			print
			print red("!!! No message digest entry found for file \""+x+".\"")
			print "!!! Most likely a temporary problem. Try 'emerge sync' again later."
			print "!!! If you are certain of the authenticity of the file then you may type"
			print "!!! the following to generate a new digest:"
			print "!!!   ebuild /usr/portage/category/package/package-version.ebuild digest"
			return 0
		myfile=basedir+"/"+x
		if not os.path.exists(myfile):
			if strict:
				print "!!! File does not exist:",myfile
				return 0
			continue
		mymd5=perform_md5(myfile)
		if mymd5 != mydigests[x][0]:
			print
			print red("!!! File is corrupt or incomplete. (Digests do not match)")
			print green(">>> our recorded digest:"),mydigests[x][0]
			print green(">>>  your file's digest:"),mymd5
			print red("!!! File does not exist:"),myfile
			print
			return 0
		else:
			print ">>> md5 "+note+" ;-)",x
	return 1


def digestcheck(myfiles, mysettings, strict=0):
	"""Checks md5sums.  Assumes all files have been downloaded."""

	# archive files
	basedir=mysettings["DISTDIR"]+"/"
	digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]

	# portage files -- p(ortagefiles)basedir
	pbasedir=mysettings["O"]+"/"
	manifestfn=pbasedir+"Manifest"

	if not (os.path.exists(digestfn) and os.path.exists(manifestfn)):
		if "digest" in features:
			print ">>> No package digest/Manifest file found."
			print ">>> \"digest\" mode enabled; auto-generating new digest..."
			return digestgen(myfiles,mysettings)
		else:
			if not os.path.exists(manifestfn):
				if strict:
					print red("!!! No package manifest found:"),manifestfn
					return 0
				else:
					print "--- No package manifest found:",manifestfn
			if not os.path.exists(digestfn):
				print "!!! No package digest file found:",digestfn
				print "!!! Type \"ebuild foo.ebuild digest\" to generate it."
				return 0

	mydigests=digestParseFile(digestfn)
	if mydigests==None:
		print "!!! Failed to parse digest file:",digestfn
		return 0
	mymdigests=digestParseFile(manifestfn)
	if "strict" not in features:
		# XXX: Remove this when manifests become mainstream.
		pass
	elif mymdigests==None:
			print "!!! Failed to parse manifest file:",manifestfn
			if strict:
				return 0
	else:
		# Check the portage-related files here.
		mymfiles=listdir(pbasedir,recursive=1,filesonly=1,ignorecvs=1,EmptyOnError=1)
		for x in range(len(mymfiles)-1,-1,-1):
			if mymfiles[x]=='Manifest': # We don't want the manifest in out list.
				del mymfiles[x]
				continue
			if mymfiles[x] not in mymdigests.keys():
				print red("!!! Security Violation: A file exists that is not in the manifest.")
				print "!!! File:",mymfiles[x]
				if strict:
					return 0
	
		if not digestCheckFiles(mymfiles, mymdigests, pbasedir, "files  ", strict):
			if strict:
				print ">>> Please ensure you have sync'd properly. Please try '"+bold("emerge sync")+"' and"
				print ">>> optionally examine the file(s) for corruption. "+bold("A sync will fix most cases.")
				print
				return 0
			else:
				print "--- Manifest check failed. 'strict' not enabled; ignoring."
				print
	
	# Just return the status, as it's the last check.
	return digestCheckFiles(myfiles, mydigests, basedir, "src_uri", strict)

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo,actionmap,mysettings,debug,alwaysdep=0):
	if alwaysdep or ("noauto" not in features):
		# process dependency first
		if "dep" in actionmap[mydo].keys():
			retval=spawnebuild(actionmap[mydo]["dep"],actionmap,mysettings,debug,alwaysdep)
			if retval:
				return retval
	# spawn ebuild.sh
	mycommand="/usr/sbin/ebuild.sh "
	return spawn(mycommand + mydo,mysettings,debug,
				actionmap[mydo]["args"][0],
				actionmap[mydo]["args"][1])

def doebuild(myebuild,mydo,myroot,mysettings,debug=0,listonly=0,fetchonly=0,cleanup=0,dbkey=None,use_cache=1):
	global db
	
	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if mysettings.configdict["pkg"].has_key("CATEGORY"):
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat         = os.path.basename(os.path.normpath(pkg_dir+"/.."))
	mypv        = os.path.basename(ebuild_path)[:-7]
	mycpv       = cat+"/"+mypv

	mysplit=pkgsplit(mypv,0)
	if mysplit==None:
		writemsg("!!! Error: PF is null '%s'; exiting.\n" % mypv)
		return 1

	mysettings.reset(use_cache=use_cache)
	mysettings.setcpv(mycpv,use_cache=use_cache)
	
	if mydo not in ["help","clean","prerm","postrm","preinst","postinst",
	                "config","touch","setup","depend","fetch","digest",
	                "unpack","compile","install","rpm","qmerge","merge",
	                "package","unmerge", "manifest"]:
		writemsg("!!! doebuild: Please specify a valid command.\n");
		return 1

	if not os.path.exists(myebuild):
		writemsg("!!! doebuild: "+str(myebuild)+" not found for "+str(mydo)+"\n")
		return 1

	if debug: # Otherwise it overrides emerge's settings.
		# We have no other way to set debug... debug can't be passed in
		# due to how it's coded... Don't overwrite this so we can use it.
		mysettings["PORTAGE_DEBUG"]=str(debug)

	mysettings["ROOT"]     = myroot
	mysettings["STARTDIR"] = getcwd()

	mysettings["EBUILD"]   = ebuild_path
	mysettings["O"]        = pkg_dir
	mysettings["CATEGORY"] = cat
	mysettings["FILESDIR"] = pkg_dir+"/files"
	mysettings["PF"]       = mypv
	
	mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"
	mysettings["SANDBOX_LOG"] = mycpv.replace("/", "_-_")

	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	mysettings["SLOT"]=""

	if mysettings.has_key("PATH"):
		mysplit=string.split(mysettings["PATH"],":")
	else:
		mysplit=[]
	if not "/usr/lib/portage/bin" in mysplit:
		mysettings["PATH"]="/usr/lib/portage/bin:"+mysettings["PATH"]

	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/portage-pkg"
	mysettings["BUILDDIR"]     = mysettings["BUILD_PREFIX"]+"/"+mysettings["PF"]

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if (mydo!="depend") or not mysettings.has_key("KV"):
		mykv,err1=ExtractKernelVersion(root+"usr/src/linux")
		if mykv:
			# Regular source tree
			mysettings["KV"]=mykv
		else:
			mysettings["KV"]=""

	if (mydo!="depend") or not mysettings.has_key("KVERS"):
		myso=os.uname()[2]
		mysettings["KVERS"]=myso[1]

	# get possible slot information from the deps file
	if mydo=="depend":
		if mysettings.has_key("PORTAGE_DEBUG") and mysettings["PORTAGE_DEBUG"]=="1":
			# XXX: This needs to use a FD for saving the output into a file.
			# XXX: Set this up through spawn
			pass
		mysettings["dbkey"] = dbkey
		return spawn("/usr/sbin/ebuild.sh depend",mysettings)

	# Build directory creation isn't required for any of these.
	if mydo not in ["fetch","digest","manifest"]:
		# Should be ok again to set $T, as sandbox does not depend on it
		mysettings["T"]=mysettings["BUILDDIR"]+"/temp"
		if cleanup or mydo=="setup":
			if os.path.exists(mysettings["T"]):
				shutil.rmtree(mysettings["T"])
		if not os.path.exists(mysettings["T"]):
			os.makedirs(mysettings["T"])
		os.chown(mysettings["T"],portage_uid,portage_gid)
		os.chmod(mysettings["T"],06770)

		try:
			if ("nouserpriv" not in string.split(mysettings["RESTRICT"])):
				if ("userpriv" in features) and (portage_uid and portage_gid):
					mysettings["HOME"]=mysettings["BUILD_PREFIX"]+"/homedir"
					if (secpass==2):
						if os.path.exists(mysettings["HOME"]):
							spawn("rm -Rf "+mysettings["HOME"],mysettings, free=1)
						if not os.path.exists(mysettings["HOME"]):
							os.makedirs(mysettings["HOME"])
				elif ("userpriv" in features):
					print "!!! Disabling userpriv from features... Portage UID/GID not valid."
					del features[features.index("userpriv")]
		except Exception, e:
			print "!!! Couldn't empty HOME:",mysettings["HOME"]
			print "!!!",e

		try:
			# no reason to check for depend since depend returns above.
			if not os.path.exists(mysettings["BUILD_PREFIX"]):
				os.makedirs(mysettings["BUILD_PREFIX"])
			os.chown(mysettings["BUILD_PREFIX"],portage_uid,portage_gid)
			if not os.path.exists(mysettings["BUILDDIR"]):
				os.makedirs(mysettings["BUILDDIR"])
			os.chown(mysettings["BUILDDIR"],portage_uid,portage_gid)
		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Perhaps: rm -Rf",mysettings["BUILD_PREFIX"]
			print "!!!",str(e)
			return 1

		try:
			if ("userpriv" in features) and ("ccache" in features):
				if (not mysettings.has_key("CCACHE_DIR")) or (mysettings["CCACHE_DIR"]==""):
					mysettings["CCACHE_DIR"]=mysettings["PORTAGE_TMPDIR"]+"/ccache"
				if not os.path.exists(mysettings["CCACHE_DIR"]):
					os.makedirs(mysettings["CCACHE_DIR"])
				if not os.path.exists(mysettings["HOME"]):
					os.makedirs(mysettings["HOME"])
				os.chown(mysettings["HOME"],portage_uid,portage_gid)
				os.chmod(mysettings["HOME"],06770)
		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Perhaps: rm -Rf",mysettings["BUILD_PREFIX"]
			print "!!!",str(e)
			return 1

		try:
			mystat=os.stat(mysettings["CCACHE_DIR"])
			if (mystat[ST_GID]!=portage_gid) or ((mystat[ST_MODE]&02070)!=02070):
				print "*** Adjusting ccache permissions for portage user..."
				os.chown(mysettings["CCACHE_DIR"],portage_uid,portage_gid)
				os.chmod(mysettings["CCACHE_DIR"],02770)
				spawn("chown -R "+str(portage_uid)+":"+str(portage_gid)+" "+mysettings["CCACHE_DIR"],mysettings, free=1)
				spawn("chmod -R g+rw "+mysettings["CCACHE_DIR"],mysettings, free=1)
		except:
			pass
			
		if "distcc" in features:
			try:
				if (not mysettings.has_key("DISTCC_DIR")) or (mysettings["DISTCC_DIR"]==""):
					mysettings["DISTCC_DIR"]=mysettings["PORTAGE_TMPDIR"]+"/portage/.distcc"
				if not os.path.exists(mysettings["DISTCC_DIR"]):
					os.makedirs(mysettings["DISTCC_DIR"])
					os.chown(mysettings["DISTCC_DIR"],portage_uid,portage_gid)
					os.chmod(mysettings["DISTCC_DIR"],02775)
				for x in ("/lock", "/state"):
					if not os.path.exists(mysettings["DISTCC_DIR"]+x):
						os.mkdir(mysettings["DISTCC_DIR"]+x)
						os.chown(mysettings["DISTCC_DIR"]+x,portage_uid,portage_gid)
						os.chmod(mysettings["DISTCC_DIR"]+x,02775)
			except OSError, e:
				writemsg("\n!!! File system problem when setting DISTCC_DIR directory permissions.\n")
				writemsg(  "!!! DISTCC_DIR="+str(mysettings["DISTCC_DIR"]+"\n"))
				writemsg(  "!!! "+str(e)+"\n\n")
				time.sleep(5)
				features.remove("distcc")
				mysettings["DISTCC_DIR"]=""

		mysettings["WORKDIR"]=mysettings["BUILDDIR"]+"/work"
		mysettings["D"]=mysettings["BUILDDIR"]+"/image/"

		if mysettings.has_key("PORT_LOGDIR"):
			if os.access(mysettings["PORT_LOGDIR"]+"/",os.W_OK):
				try:
					os.chown(mysettings["BUILD_PREFIX"],portage_uid,portage_gid)
					os.chmod(mysettings["PORT_LOGDIR"],06770)
					if not mysettings.has_key("LOG_PF") or (mysettings["LOG_PF"] != mysettings["PF"]):
						mysettings["LOG_PF"]=mysettings["PF"]
						mysettings["LOG_COUNTER"]=str(db[myroot]["vartree"].dbapi.get_counter_tick_core("/"))
				except ValueError, e:
					mysettings["PORT_LOGDIR"]=""
					print "!!! Unable to chown/chmod PORT_LOGDIR. Disabling logging."
					print "!!!",e
			else:
				print "!!! Cannot create log... No write access / Does not exist"
				print "!!! PORT_LOGDIR:",mysettings["PORT_LOGDIR"]
				mysettings["PORT_LOGDIR"]=""

		if mydo=="unmerge":
			return unmerge(mysettings["CATEGORY"],mysettings["PF"],myroot,mysettings)

	# if any of these are being called, handle them -- running them out of the sandbox -- and stop now.
	if mydo in ["help","clean","setup"]:
		return spawn("/usr/sbin/ebuild.sh "+mydo,mysettings,debug,free=1)
	elif mydo in ["prerm","postrm","preinst","postinst","config"]:
		mysettings.load_infodir(pkg_dir)
		return spawn("/usr/sbin/ebuild.sh "+mydo,mysettings,debug,free=1)
	
	try: 
		mysettings["SLOT"], mysettings["RESTRICT"] = db["/"]["porttree"].dbapi.aux_get(mycpv,["SLOT","RESTRICT"])
	except (IOError,KeyError):
		print red("doebuild():")+" aux_get() error; aborting."
		sys.exit(1)

	newuris, alist=db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings)
	alluris, aalist=db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings,all=1)
	mysettings["A"]=string.join(alist," ")
	mysettings["AA"]=string.join(aalist," ")
	if ("cvs" in features) or ("mirror" in features):
		fetchme=alluris
		checkme=aalist
	else:
		fetchme=newuris
		checkme=alist

	try:
		if not os.path.exists(mysettings["DISTDIR"]):
			os.makedirs(mysettings["DISTDIR"])
		if not os.path.exists(mysettings["DISTDIR"]+"/cvs-src"):
			os.makedirs(mysettings["DISTDIR"]+"/cvs-src")
	except OSError, e:
		print "!!! File system problem. (Bad Symlink?)"
		print "!!! Fetching may fail:",str(e)

	try:
		mystat=os.stat(mysettings["DISTDIR"]+"/cvs-src")
		if (mystat[ST_GID]!=portage_gid) or ((mystat[ST_MODE]&02770)!=02770):
			print "*** Adjusting cvs-src permissions for portage user..."
			os.chown(mysettings["DISTDIR"]+"/cvs-src",0,portage_gid)
			os.chmod(mysettings["DISTDIR"]+"/cvs-src",02770)
			spawn("chgrp -R "+str(portage_gid)+" "+mysettings["DISTDIR"]+"/cvs-src", free=1)
			spawn("chmod -R g+rw "+mysettings["DISTDIR"]+"/cvs-src", free=1)
	except:
		pass

	if not fetch(fetchme, mysettings, listonly, fetchonly):
		return 1

	if "digest" in features:
		#generate digest if it doesn't exist.
		if mydo=="digest":
			return (not digestgen(checkme,mysettings,overwrite=1))
		else:
			digestgen(checkme,mysettings,overwrite=0)
	elif mydo=="digest":
		#since we are calling "digest" directly, recreate the digest even if it already exists
		return (not digestgen(checkme,mysettings,overwrite=1))
	if mydo=="manifest":
		return (not digestgen(checkme,mysettings,overwrite=1,manifestonly=1))
	
	if not digestcheck(checkme, mysettings, ("strict" in features)):
		return 1
	
	if mydo=="fetch":
		return 0

	#initial dep checks complete; time to process main commands

	nosandbox=(("userpriv" in features) and ("usersandbox" not in features))
	actionmap={
			  "depend": {                 "args":(0,1)},         # sandbox  / portage
			  "setup":  {                 "args":(1,0)},         # without  / root
			 "unpack":  {"dep":"setup",   "args":(0,1)},         # sandbox  / portage
			"compile":  {"dep":"unpack",  "args":(nosandbox,1)}, # optional / portage
			"install":  {"dep":"compile", "args":(0,0)},         # sandbox  / root
			    "rpm":  {"dep":"install", "args":(0,0)},         # sandbox  / root
    	"package":  {"dep":"install", "args":(0,0)},         # sandbox  / root
	}
	
	if mydo in actionmap.keys():	
		if mydo=="package":
			for x in ["","/"+mysettings["CATEGORY"],"/All"]:
				if not os.path.exists(mysettings["PKGDIR"]+x):
					os.makedirs(mysettings["PKGDIR"]+x)
		# REBUILD CODE FOR TBZ2 --- XXXX
		return spawnebuild(mydo,actionmap,mysettings,debug)
	elif mydo=="qmerge": 
		#qmerge is specifically not supposed to do a runtime dep check
		return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,mysettings)
	elif mydo=="merge":
		retval=spawnebuild("install",actionmap,mysettings,debug,1)
		if retval:
			return retval
		return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,mysettings,myebuild=mysettings["EBUILD"])
	else:
		print "!!! Unknown mydo:",mydo
		sys.exit(1)

expandcache={}

def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	global lchown 	
	try:
		if not sstat:
			sstat=os.lstat(src)
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except:
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if destexists:
		if S_ISLNK(dstat[ST_MODE]):
			try:
				os.unlink(dest)
				destexists=0
			except Exception, e:
				pass

	if S_ISLNK(sstat[ST_MODE]):
		try:
			target=os.readlink(src)
			if mysettings and mysettings["D"]:
				if target.find(mysettings["D"])==0:
					target=target[len(mysettings["D"]):]
			if destexists and not S_ISDIR(dstat[ST_MODE]):
				os.unlink(dest)
			if selinux_enabled:
				sid = selinux.get_lsid(src)
				selinux.secure_symlink(target,dest,sid)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat[ST_UID],sstat[ST_GID])
			return os.lstat(dest)[ST_MTIME]
		except Exception, e:
			print "!!! failed to properly create symlink:"
			print "!!!",dest,"->",target
			print "!!!",e
			return None

	renamefailed=1
	if sstat[ST_DEV]==dstat[ST_DEV] or selinux_enabled:
		try:
			if selinux_enabled:
				ret=selinux.secure_rename(src,dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except Exception, e:
			import errno
			if e[0]!=errno.EXDEV:
				# Some random error.
				print "!!! Failed to move",src,"to",dest
				print "!!!",e
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		didcopy=0
		if S_ISREG(sstat[ST_MODE]):
			try: # For safety copy then move it over.
				if selinux_enabled:
					selinux.secure_copy(src,dest+"#new")
					selinux.secure_rename(dest+"#new",dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except Exception, e:
				print '!!! copy',src,'->',dest,'failed.'
				print "!!!",e
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			if selinux_enabled:
				a=getstatusoutput("/bin/mv -c -f "+"'"+src+"' '"+dest+"'")
			else:
				a=getstatusoutput("/bin/mv -f "+"'"+src+"' '"+dest+"'")
				if a[0]!=0:
					print "!!! Failed to move special file:"
					print "!!! '"+src+"' to '"+dest+"'"
					print "!!!",a
					return None # failure
		try:
			if didcopy:
				lchown(dest,sstat[ST_UID],sstat[ST_GID])
				os.chmod(dest, S_IMODE(sstat[ST_MODE])) # Sticky is reset on chown
				os.unlink(src)
		except Exception, e:
			print "!!! Failed to chown/chmod/unlink in movefile()"
			print "!!!",dest
			print "!!!",e
			return None

	if newmtime:
		os.utime(dest,(newmtime,newmtime))
	else:
		os.utime(dest, (sstat[ST_ATIME], sstat[ST_MTIME]))
		newmtime=sstat[ST_MTIME]
	return newmtime

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, calc_prelink)[0]

def merge(mycat,mypkg,pkgloc,infloc,myroot,mysettings,myebuild=None):
	mylink=dblink(mycat,mypkg,myroot,mysettings)
	return mylink.merge(pkgloc,infloc,myroot,myebuild)
	
def unmerge(cat,pkg,myroot,mysettings,mytrimworld=1):
	mylink=dblink(cat,pkg,myroot,mysettings)
	if mylink.exists():
		mylink.unmerge(trimworld=mytrimworld,cleanup=1)
	mylink.delete()

def relparse(myver):
	"converts last version part into three components"
	number=0
	suffix=0
	endtype=0
	endnumber=0
	
	mynewver=string.split(myver,"_")
	myver=mynewver[0]

	#normal number or number with letter at end
	divider=len(myver)-1
	if myver[divider:] not in "1234567890":
		#letter at end
		suffix=ord(myver[divider:])
		number=string.atof(myver[0:divider])
	else:
		number=string.atof(myver)  

	if len(mynewver)==2:
		#an endversion
		for x in endversion_keys:
			elen=len(x)
			if mynewver[1][:elen] == x:
				match=1
				endtype=endversion[x]
				try:
					endnumber=string.atof(mynewver[1][elen:])
				except:
					endnumber=0
				break
	return [number,suffix,endtype,endnumber]

#returns 1 if valid version string, else 0
# valid string in format: <v1>.<v2>...<vx>[a-z,_{endversion}[vy]]
# ververify doesn't do package rev.

vercache={}
def ververify(myorigval,silent=1):
	try:
		return vercache[myorigval]
	except KeyError:
		pass
	if len(myorigval)==0:
		if not silent:
			print "!!! Name error: package contains empty \"-\" part."
		return 0
	myval=string.split(myorigval,'.')
	if len(myval)==0:
		if not silent:
			print "!!! Name error: empty version string."
		vercache[myorigval]=0
		return 0
	#all but the last version must be a numeric
	for x in myval[:-1]:
		if not len(x):
			if not silent:
				print "!!! Name error in",myorigval+": two decimal points in a row"
			vercache[myorigval]=0
			return 0
		try:
			foo=string.atoi(x)
		except:
			if not silent:
				print "!!! Name error in",myorigval+": \""+x+"\" is not a valid version component."
			vercache[myorigval]=0
			return 0
	if not len(myval[-1]):
			if not silent:
				print "!!! Name error in",myorigval+": two decimal points in a row"
			vercache[myorigval]=0
			return 0
	try:
		foo=string.atoi(myval[-1])
		vercache[myorigval]=1
		return 1
	except:
		pass
	#ok, our last component is not a plain number or blank, let's continue
	if myval[-1][-1] in string.lowercase:
		try:
			foo=string.atoi(myval[-1][:-1])
			return 1
			vercache[myorigval]=1
			# 1a, 2.0b, etc.
		except:
			pass
	#ok, maybe we have a 1_alpha or 1_beta2; let's see
	#ep="endpart"
	ep=string.split(myval[-1],"_")
	if len(ep)!=2:
		if not silent:
			print "!!! Name error in",myorigval
		vercache[myorigval]=0
		return 0
	try:
		foo=string.atoi(ep[0][-1])
		chk=ep[0]
	except:
		# because it's ok last char is not numeric. example: foo-1.0.0a_pre1
		chk=ep[0][:-1]

	try:
		foo=string.atoi(chk)
	except:
		#this needs to be numeric or numeric+single letter,
		#i.e. the "1" in "1_alpha" or "1a_alpha"
		if not silent:
			print "!!! Name error in",myorigval+": characters before _ must be numeric or numeric+single letter"
		vercache[myorigval]=0
		return 0
	for mye in endversion_keys:
		if ep[1][0:len(mye)]==mye:
			if len(mye)==len(ep[1]):
				#no trailing numeric; ok
				vercache[myorigval]=1
				return 1
			else:
				try:
					foo=string.atoi(ep[1][len(mye):])
					vercache[myorigval]=1
					return 1
				except:
					#if no endversions work, *then* we return 0
					pass	
	if not silent:
		print "!!! Name error in",myorigval
	vercache[myorigval]=0
	return 0

def isvalidatom(atom):
	mycpv_cps = catpkgsplit(dep_getcpv(atom))
	operator = get_operator(atom)
	if operator:
		if mycpv_cps and mycpv_cps[0] != "null":
			# >=cat/pkg-1.0
			return 1 
		else:
			# >=cat/pkg or >=pkg-1.0 (no category)
			return 0
	if mycpv_cps:
		# cat/pkg-1.0
		return 0

	if (len(string.split(atom, '/'))==2):
		# cat/pkg
		return 1
	else:
		return 0

def isjustname(mypkg):
	myparts=string.split(mypkg,'-')
	for x in myparts:
		if ververify(x):
			return 0
	return 1

iscache={}
def isspecific(mypkg):
	"now supports packages with no category"
	try:
		return iscache[mypkg]
	except:
		pass
	mysplit=string.split(mypkg,"/")
	if not isjustname(mysplit[-1]):
			iscache[mypkg]=1
			return 1
	iscache[mypkg]=0
	return 0

# This function can be used as a package verification function, i.e.
# "pkgsplit("foo-1.2-1") will return None if foo-1.2-1 isn't a valid
# package (with version) name.	If it is a valid name, pkgsplit will
# return a list containing: [ pkgname, pkgversion(norev), pkgrev ].
# For foo-1.2-1, this list would be [ "foo", "1.2", "1" ].  For 
# Mesa-3.0, this list would be [ "Mesa", "3.0", "0" ].
pkgcache={}

def pkgsplit(mypkg,silent=1):
	try:
		if not pkgcache[mypkg]:
			return None
		return pkgcache[mypkg][:]
	except KeyError:
		pass
	myparts=string.split(mypkg,'-')
	if len(myparts)<2:
		if not silent:
			print "!!! Name error in",mypkg+": missing a version or name part."
		pkgcache[mypkg]=None
		return None
	for x in myparts:
		if len(x)==0:
			if not silent:
				print "!!! Name error in",mypkg+": empty \"-\" part."
			pkgcache[mypkg]=None
			return None
	#verify rev
	revok=0
	myrev=myparts[-1]
	if len(myrev) and myrev[0]=="r":
		try:
			string.atoi(myrev[1:])
			revok=1
		except: 
			pass
	if revok:
		if ververify(myparts[-2]):
			if len(myparts)==2:
				pkgcache[mypkg]=None
				return None
			else:
				for x in myparts[:-2]:
					if ververify(x):
						pkgcache[mypkg]=None
						return None
						#names can't have versiony looking parts
				myval=[string.join(myparts[:-2],"-"),myparts[-2],myparts[-1]]
				pkgcache[mypkg]=myval
				return myval
		else:
			pkgcache[mypkg]=None
			return None

	elif ververify(myparts[-1],silent):
		if len(myparts)==1:
			if not silent:
				print "!!! Name error in",mypkg+": missing name part."
			pkgcache[mypkg]=None
			return None
		else:
			for x in myparts[:-1]:
				if ververify(x):
					if not silent:
						print "!!! Name error in",mypkg+": multiple version parts."
					pkgcache[mypkg]=None
					return None
			myval=[string.join(myparts[:-1],"-"),myparts[-1],"r0"]
			pkgcache[mypkg]=myval[:]
			return myval
	else:
		pkgcache[mypkg]=None
		return None

catcache={}
def catpkgsplit(mydata,silent=1):
	"returns [cat, pkgname, version, rev ]"
	try:
		if not catcache[mydata]:
			return None
		return catcache[mydata][:]
	except KeyError:
		pass
	mysplit=mydata.split("/")
	p_split=None
	if len(mysplit)==1:
		retval=["null"]
		p_split=pkgsplit(mydata,silent)
	elif len(mysplit)==2:
		retval=[mysplit[0]]
		p_split=pkgsplit(mysplit[1],silent)
	if not p_split:
		catcache[mydata]=None
		return None
	retval.extend(p_split)
	catcache[mydata]=retval
	return retval

# vercmp:
# This takes two version strings and returns an integer to tell you whether
# the versions are the same, val1>val2 or val2>val1.
vcmpcache={}
def vercmp(val1,val2):
	if val1==val2:
		#quick short-circuit
		return 0
	valkey=val1+" "+val2
	try:
		return vcmpcache[valkey]
		try:
			return -vcmpcache[val2+" "+val1]
		except KeyError:
			pass
	except KeyError:
		pass
	
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

	# extend version numbers
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
		for y in range(0,4):
			myret=cmp1[y]-cmp2[y]
			if myret != 0:
				vcmpcache[valkey]=myret
				return myret
	vcmpcache[valkey]=0
	return 0


def pkgcmp(pkg1,pkg2):
	"""if returnval is less than zero, then pkg2 is newer than pkg1, zero if equal and positive if older."""
	if pkg1[0] != pkg2[0]:
		return None
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

def dep_opconvert(mysplit,myuse,mysettings):
	"Does dependency operator conversion"
	
	#check_config_instance(mysettings)
	
	mypos=0
	newsplit=[]
	while mypos<len(mysplit):
		if type(mysplit[mypos])==types.ListType:
			newsplit.append(dep_opconvert(mysplit[mypos],myuse,mysettings))
			mypos += 1
		elif mysplit[mypos]==")":
			#mismatched paren, error
			return None
		elif mysplit[mypos]=="||":
			if ((mypos+1)>=len(mysplit)) or (type(mysplit[mypos+1])!=types.ListType):
				# || must be followed by paren'd list
				return None
			try:
				mynew=dep_opconvert(mysplit[mypos+1],myuse,mysettings)
			except Exception, e:
				print "!!! Unable to satisfy OR dependency:",string.join(mysplit," || ")
				raise e
			mynew[0:0]=["||"]
			newsplit.append(mynew)
			mypos += 2
		elif mysplit[mypos][-1]=="?":
			#uses clause, i.e "gnome? ( foo bar )"
			#this is a quick and dirty hack so that repoman can enable all USE vars:
			if (len(myuse)==1) and (myuse[0]=="*") and mysettings:
				# enable it even if it's ! (for repoman) but kill it if it's
				# an arch variable that isn't for this arch. XXX Sparc64?
				k=mysplit[mypos][:-1]
				if k[0]=="!":
					k=k[1:]
				if (k not in archlist and k not in mysettings.usemask) or \
							 (k in archlist and k==mysettings["ARCH"] and \
								mysplit[mypos][0]!="!"):
					enabled=1
				else:
					enabled=0
			else:
				if mysplit[mypos][0]=="!":
					myusevar=mysplit[mypos][1:-1]
					if myusevar in myuse:
						enabled=0
					else:
						enabled=1
				else:
					myusevar=mysplit[mypos][:-1]
					if myusevar in myuse:
						enabled=1
					else:
						enabled=0
			if (mypos+2<len(mysplit)) and (mysplit[mypos+2]==":"):
				#colon mode
				if enabled:
					#choose the first option
					if type(mysplit[mypos+1])==types.ListType:
						newsplit.append(dep_opconvert(mysplit[mypos+1],myuse,mysettings))
					else:
						newsplit.append(mysplit[mypos+1])
				else:
					#choose the alternate option
					if type(mysplit[mypos+1])==types.ListType:
						newsplit.append(dep_opconvert(mysplit[mypos+3],myuse,mysettings))
					else:
						newsplit.append(mysplit[mypos+3])
				mypos += 4
			else:
				#normal use mode
				if enabled:
					if type(mysplit[mypos+1])==types.ListType:
						newsplit.append(dep_opconvert(mysplit[mypos+1],myuse,mysettings))
					else:
						newsplit.append(mysplit[mypos+1])
				#otherwise, continue.
				mypos += 2
		else:
			#normal item
			newsplit.append(mysplit[mypos])
			mypos += 1
	return newsplit

def dep_virtual(mysplit):
	"Does virtual dependency conversion"

	newsplit=[]
	for x in mysplit:
		if type(x)==types.ListType:
			newsplit.append(dep_virtual(x))
		else:
			mykey=dep_getkey(x)
			if virts.has_key(mykey):
				if len(virts[mykey])==1:
					a=string.replace(x, mykey, virts[mykey][0])
				else:
					a=['||']
					for y in virts[mykey]:
						a.append(string.replace(x, mykey, y))
				newsplit.append(a)
			else:
				newsplit.append(x)
	return newsplit

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

def dep_zapdeps(unreduced,reduced,vardbapi=None,use_binaries=0):
	"""Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies."""
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if unreduced==[] or unreduced==['||'] :
		return []
	if unreduced[0]=="||":
		if dep_eval(reduced):
			#deps satisfied, return empty list.
			return []
		else:
			#try to find an installed dep.
			### We use fakedb when --update now, so we can't use local vardbapi here.
			### This should be fixed in the feature.
			### see bug 45468.
			##if vardbapi:
			##	mydbapi=vardbapi
			##else:
			##	mydbapi=db[root]["vartree"].dbapi
			mydbapi=db[root]["vartree"].dbapi

			if db["/"].has_key("porttree"):
				myportapi=db["/"]["porttree"].dbapi
			else:
				myportapi=None

			if use_binaries and db["/"].has_key("bintree"):
				mybinapi=db["/"]["bintree"].dbapi
				writemsg("Using bintree...\n",2)
			else:
				mybinapi=None

			x=1
			candidate=[]
			while x<len(reduced):
				writemsg("x: %s, reduced[x]: %s\n" % (x,reduced[x]), 2)
				if (type(reduced[x])==types.ListType):
					newcand = dep_zapdeps(unreduced[x], reduced[x], vardbapi=vardbapi, use_binaries=use_binaries)
					candidate.append(newcand)
				else:
					if (reduced[x]==False):
						candidate.append([unreduced[x]])
					else:
						candidate.append([])
				x+=1

			#use installed and no-masked package(s) in portage.
			for x in candidate:
				match=1
				for pkg in x:
					if not mydbapi.match(pkg):
						match=0
						break
					if myportapi:
						if not myportapi.match(pkg):
							match=0
							break
				if match:
					writemsg("Installed match: %s\n" % (x), 2)
					return x

			# Use binary packages if available.
			if mybinapi:
				for x in candidate:
					match=1
					for pkg in x:
						if not mybinapi.match(pkg):
							match=0
							break
						else:
							writemsg("Binary match: %s\n" % (pkg), 2)
					if match:
						writemsg("Binary match final: %s\n" % (x), 2)
						return x

			#use no-masked package(s) in portage tree
			if myportapi:
				for x in candidate:
					match=1
					for pkg in x:
						if not myportapi.match(pkg):
							match=0
							break
					if match:
						writemsg("Porttree match: %s\n" % (x), 2)
						return x

			#none of the no-masked pkg, use the first one
			writemsg("Last resort candidate: %s\n" % (candidate[0]), 2)
			return candidate[0]
	else:
		if dep_eval(reduced):
			#deps satisfied, return empty list.
			return []
		else:
			returnme=[]
			x=0
			while x<len(reduced):
				if type(reduced[x])==types.ListType:
					returnme+=dep_zapdeps(unreduced[x],reduced[x], vardbapi=vardbapi, use_binaries=use_binaries)
				else:
					if reduced[x]==False:
						returnme.append(unreduced[x])
				x += 1
			return returnme

def dep_getkey(mydep):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	if mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	if isspecific(mydep):
		mysplit=catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0]+"/"+mysplit[1]
	else:
		return mydep

def dep_getcpv(mydep):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	if mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	return mydep

def cpv_getkey(mycpv):
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	mylen=len(myslash)
	if mylen==2:
		return myslash[0]+"/"+mysplit[0]
	elif mylen==1:
		return mysplit[0]
	else:
		return mysplit

def key_expand(mykey,mydb=None,use_cache=1):
	mysplit=mykey.split("/")
	if len(mysplit)==1:
		if mydb and type(mydb)==types.InstanceType:
			for x in settings.categories:
				if mydb.cp_list(x+"/"+mykey,use_cache=use_cache):
					return x+"/"+mykey
			if virts_p.has_key(mykey):
				return(virts_p[mykey][0])
		return "null/"+mykey
	elif mydb:
		if type(mydb)==types.InstanceType:
			if (not mydb.cp_list(mykey,use_cache=use_cache)) and virts and virts.has_key(mykey):
				return virts[mykey][0]
		return mykey

def cpv_expand(mycpv,mydb=None,use_cache=1):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	if len(myslash)>2:
		# this is illegal case.
		mysplit=[]
		mykey=mycpv
	elif len(myslash)==2:
		if mysplit:
			mykey=myslash[0]+"/"+mysplit[0]
		else:
			mykey=mycpv
		if mydb:
			writemsg("mydb.__class__: %s\n" % (mydb.__class__), 1)
			if type(mydb)==types.InstanceType:
				if (not mydb.cp_list(mykey,use_cache=use_cache)) and virts and virts.has_key(mykey):
					writemsg("virts[%s]: %s\n" % (str(mykey),virts[mykey]), 1)
					mykey_orig = mykey[:]
					for vkey in virts[mykey]:
						if mydb.cp_list(vkey,use_cache=use_cache):
							mykey = vkey
							writemsg("virts chosen: %s\n" % (mykey), 1)
							break
					if mykey == mykey_orig:
						mykey=virts[mykey][0]
						writemsg("virts defaulted: %s\n" % (mykey), 1)
			#we only perform virtual expansion if we are passed a dbapi
	else:
		#specific cpv, no category, ie. "foo-1.0"
		if mysplit:
			myp=mysplit[0]
		else:
			# "foo" ?
			myp=mycpv
		mykey=None
		matches=[]
		if mydb:
			for x in settings.categories:
				if mydb.cp_list(x+"/"+myp,use_cache=use_cache):
					matches.append(x+"/"+myp)
		if (len(matches)>1):
			raise ValueError, matches
		elif matches:
			mykey=matches[0]

		if not mykey and type(mydb)!=types.ListType:
			if virts_p.has_key(myp):
				mykey=virts_p[myp][0]
			#again, we only perform virtual expansion if we have a dbapi (not a list)				
		if not mykey:
			mykey="null/"+myp
	if mysplit:
		if mysplit[2]=="r0":
			return mykey+"-"+mysplit[1]
		else:
			return mykey+"-"+mysplit[1]+"-"+mysplit[2]
	else:
		return mykey

def dep_transform(mydep,oldkey,newkey):
	origdep=mydep
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	prefix=""
	postfix=""
	if mydep[-1]=="*":
		mydep=mydep[:-1]
		postfix="*"
	if mydep[:2] in [ ">=", "<=" ]:
		prefix=mydep[:2]
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~!":
		prefix=mydep[:1]
		mydep=mydep[1:]
	if mydep==oldkey:
		return prefix+newkey+postfix
	else:
		return origdep

def dep_expand(mydep,mydb=None,use_cache=1):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	prefix=""
	postfix=""
	if mydep[-1]=="*":
		mydep=mydep[:-1]
		postfix="*"
	if mydep[:2] in [ ">=", "<=" ]:
		prefix=mydep[:2]
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~!":
		prefix=mydep[:1]
		mydep=mydep[1:]
	return prefix+cpv_expand(mydep,mydb,use_cache=use_cache)+postfix

def dep_check(depstring,mydbapi,mysettings,use="yes",mode=None,myuse=None,use_cache=1,use_binaries=0):
	"""Takes a depend string and parses the condition."""

	#check_config_instance(mysettings)

	if use=="all":
		#enable everything (for repoman)
		myusesplit=["*"]
	elif use=="yes":
		if myuse==None:
			#default behavior
			myusesplit = string.split(mysettings["USE"])
		else:
			myusesplit = myuse
			# We've been given useflags to use.
			#print "USE FLAGS PASSED IN."
			#print myuse
			#if "bindist" in myusesplit:
			#	print "BINDIST is set!"
			#else:
			#	print "BINDIST NOT set."
	else:
		#we are being run by autouse(), don't consult USE vars yet.
		# WE ALSO CANNOT USE SETTINGS
		myusesplit=[]
		
	#convert parenthesis to sublists
	mysplit = portage_dep.paren_reduce(depstring)

	# XXX -- This is waiting for the "a? b : c" deps to be removed.
	mysplit=dep_opconvert(mysplit,myusesplit,mysettings)
	#if mysettings:
	#	mymasks = mysettings.usemask+archlist
	#	while mysettings["ARCH"] in mymasks:
	#		del mymasks[mymasks.index(mysettings["ARCH"])]
	#	mysplit = portage_dep.use_reduce(mysplit,myusesplit,masklist=mymasks)
	#else:
	#	mysplit = portage_dep.use_reduce(mysplit,myusesplit)

	#convert virtual dependencies to normal packages.
	mysplit=dep_virtual(mysplit)
	#if mysplit==None, then we have a parse error (paren mismatch or misplaced ||)
	#up until here, we haven't needed to look at the database tree

	if mysplit==None:
		return [0,"Parse Error (parentheses mismatch?)"]
	elif mysplit==[]:
		#dependencies were reduced to nothing
		return [1,[]]
	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mydbapi,mode,use_cache=use_cache)
	if mysplit2==None:
		return [0,"Invalid token"]
	
	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)
	myeval=dep_eval(mysplit2)
	writemsg("myeval:   %s\n" % (myeval), 1)
	
	if myeval:
		return [1,[]]
	else:
		myzaps = dep_zapdeps(mysplit,mysplit2,vardbapi=mydbapi,use_binaries=use_binaries)
		mylist = flatten(myzaps)
		writemsg("myzaps:   %s\n" % (myzaps), 1)
		writemsg("mylist:   %s\n" % (mylist), 1)
		#remove duplicates
		mydict={}
		for x in mylist:
			mydict[x]=1
		writemsg("mydict:   %s\n" % (mydict), 1)
		return [1,mydict.keys()]

def dep_wordreduce(mydeplist,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	mypos=0
	deplist=mydeplist[:]
	while mypos<len(deplist):
		if type(deplist[mypos])==types.ListType:
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		else:
			if mode:
				mydep=mydbapi.xmatch(mode,deplist[mypos])
			else:
				mydep=mydbapi.match(deplist[mypos],use_cache=use_cache)
			if mydep!=None:
				tmp=(len(mydep)>=1)
				if deplist[mypos][0]=="!":
					tmp=not tmp
				deplist[mypos]=tmp
			else:
				#encountered invalid string
				return None
		mypos=mypos+1
	return deplist

def getmaskingstatus(mycpv):
	global portdb
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if not portdb.cpv_exists(mycpv):
		raise KeyError("CPV %s does not exist" % mycpv)
	mycp=mysplit[0]+"/"+mysplit[1]
	
	rValue = []

	# profile checking
	if profiledir:
		syslist = []
		for l in grabfile(profiledir+"/packages"):
			if l[0] == "*":
				syslist.append(l[1:])
			else:
				syslist.append(l)
		for pkg in syslist:
			if pkg.find(mysplit[0]+"/"+mysplit[1]) >= 0 and not match_to_list(mycpv, [pkg]):
				rValue.append("profile")
				break
	
	# package.mask checking
	maskdict=settings.pmaskdict
	unmaskdict=settings.punmaskdict
	if maskdict.has_key(mycp):
		for x in maskdict[mycp]:
			if mycpv in portdb.xmatch("match-all", x):
				unmask=0
				if unmaskdict.has_key(mycp):
					for z in unmaskdict[mycp]:
						if mycpv in portdb.xmatch("match-all",z):
							unmask=1
							break
				if unmask==0:
					rValue.append("package.mask")

	# keywords checking
	mygroups = portdb.aux_get(mycpv, ["KEYWORDS"])[0].split()
	pgroups=groups[:]
	myarch = settings["ARCH"]
	pkgdict = settings.pkeywordsdict

	for mykey in pkgdict:
		if portdb.xmatch("bestmatch-list", mykey, None, None, [mycpv]):
			pgroups.extend(pkgdict[mykey])

	kmask = "missing"

	for keyword in pgroups:
		if keyword in mygroups:
			kmask=None

	if kmask:
		for gp in mygroups:
			if gp=="*":
				kmask=None
				break
			elif gp=="-*":
				kmask="-*"
				break
			elif gp=="-"+myarch:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch:
				kmask="~"+myarch
				break

	if kmask:
		rValue.append(kmask+" keyword")
	return rValue

def fixdbentries(old_value, new_value, dbdir):
	"""python replacement for the fixdbentries script, replaces old_value 
	with new_value for package names in files in dbdir."""
	for myfile in [f for f in os.listdir(dbdir) if not f == "CONTENTS"]:
		f = open(dbdir+"/"+myfile, "r")
		mycontent = f.read()
		f.close()
		if not mycontent.count(old_value):
			continue
		old_value = re.escape(old_value);
		mycontent = re.sub(old_value+"$", new_value, mycontent)
		mycontent = re.sub(old_value+"(\s)", new_value+"\1", mycontent)
		mycontent = re.sub(old_value+"(-[^a-zA-Z])", new_value+"\1", mycontent)
		mycontent = re.sub(old_value+"([^a-zA-Z0-9-])", new_value+"\1", mycontent)
		f = open(dbdir+"/"+myfile, "w")
		f.write(mycontent)
		f.close()

class packagetree:
	def __init__(self,virtual,clone=None):
		if clone:
			self.tree=clone.tree.copy()
			self.populated=clone.populated
			self.virtual=clone.virtual
			self.dbapi=None
		else:
			self.tree={}
			self.populated=0
			self.virtual=virtual
			self.dbapi=None
		
	def resolve_key(self,mykey):
		return key_expand(mykey,self.dbapi)
	
	def dep_nomatch(self,mypkgdep):
		mykey=dep_getkey(mypkgdep)
		nolist=self.dbapi.cp_list(mykey)
		mymatch=self.dbapi.match(mypkgdep)
		if not mymatch:
			return nolist
		for x in mymatch:
			if x in nolist:
				nolist.remove(x)
		return nolist

	def depcheck(self,mycheck,use="yes",myusesplit=None):
		return dep_check(mycheck,self.dbapi,use=use,myusesplit=myusesplit)

	def populate(self):
		"populates the tree with values"
		populated=1
		pass

def best(mymatches):
	"accepts None arguments; assumes matches are valid."
	global bestcount
	if mymatches==None:
		return "" 
	if not len(mymatches):
		return "" 
	bestmatch=mymatches[0]
	p2=catpkgsplit(bestmatch)[1:]
	for x in mymatches[1:]:
		p1=catpkgsplit(x)[1:]
		if pkgcmp(p1,p2)>0:
			bestmatch=x
			p2=catpkgsplit(bestmatch)[1:]
	return bestmatch		

def match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Searches list for entries that matches the package.
	"""
	matches=[]
	for x in mylist:
		if match_from_list(x,[mypkg]):
			if x not in matches:
				matches.append(x)
	return matches

def best_match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Returns the most specific entry (assumed to be the longest one)
	that matches the package given.
	"""
	# XXX Assumption is wrong sometimes.
	maxlen = 0
	bestm  = None
	for x in match_to_list(mypkg,mylist):
		if len(x) > maxlen:
			maxlen = len(x)
			bestm  = x
	return bestm

def catsplit(mydep):
	return mydep.split("/", 1)
	
def get_operator(mydep):
	"""
	returns '~', '=', '>', '<', '=*', '>=', or '<='
	"""
	if mydep[0] == "~":
		operator = "~"
	elif mydep[0] == "=":
		if mydep[-1] == "*":
			operator = "=*"
		else:
			operator = "="
	elif mydep[0] in "><":
		if len(mydep) > 1 and mydep[1] == "=":
			operator = mydep[0:2]
		else:
			operator = mydep[0]
	else:
		operator = None

	return operator


def match_from_list(mydep,candidate_list):
	if mydep[0] == "!":
		mydep = mydep[1:]

	mycpv     = dep_getcpv(mydep)
	mycpv_cps = catpkgsplit(mycpv) # Can be None if not specific

	if not mycpv_cps:
		cat,pkg = catsplit(mycpv)
		ver     = None
		rev     = None
	else:
		cat,pkg,ver,rev = mycpv_cps
		if mydep == mycpv:
			raise KeyError, "Specific key requires an operator (%s) (try adding an '=')" % (mydep)

	if ver and rev:
		operator = get_operator(mydep)
		if not operator:
			writemsg("!!! Invanlid atom: %s\n" % mydep)
			return []
	else:
		operator = None

	mylist = []

	if operator == None:
		for x in candidate_list:
			xs = pkgsplit(x)
			if xs == None:
				if x != mycpv:
					continue
			elif xs[0] != mycpv:
				continue
			mylist.append(x)

	elif operator == "=": # Exact match
		if mycpv in candidate_list:
			mylist = [mycpv]
	
	elif operator == "=*": # glob match
		# The old verion ignored _tag suffixes... This one doesn't.
		for x in candidate_list:
			if x[0:len(mycpv)] == mycpv:
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = catpkgsplit(x)
			if xs[0:2] != mycpv_cps[0:2]:
				continue
			if xs[2] != ver:
				continue
			mylist.append(x)

	elif operator in [">", ">=", "<", "<="]:
		for x in candidate_list:
			try:
				result = pkgcmp(pkgsplit(x), [cat+"/"+pkg,ver,rev])
			except:
				writemsg("\nInvalid package name: %s\n" % x)
				sys.exit(73)
			if result == None:
				continue
			elif operator == ">":
				if result > 0:
					mylist.append(x)
			elif operator == ">=":
				if result >= 0:
					mylist.append(x)
			elif operator == "<":
				if result < 0:
					mylist.append(x)
			elif operator == "<=":
				if result <= 0:
					mylist.append(x)
			else:
				raise KeyError, "Unknown operator: %s" % mydep
	else:
		raise KeyError, "Unknown operator: %s" % mydep
	

	return mylist
				

def match_from_list_original(mydep,mylist):
	"""(dep,list)
	Reduces the list down to those that fit the dep
	"""
	mycpv=dep_getcpv(mydep)
	if isspecific(mycpv):
		cp_key=catpkgsplit(mycpv)
		if cp_key==None:
			return []
	else:
		cp_key=None
	#Otherwise, this is a special call; we can only select out of the ebuilds specified in the specified mylist
	if (mydep[0]=="="):
		if cp_key==None:
			return []
		if mydep[-1]=="*":
			#example: "=sys-apps/foo-1.0*"
			try:
				#now, we grab the version of our dependency...
				mynewsplit=string.split(cp_key[2],'.')
				#split it...
				mynewsplit[-1]=`int(mynewsplit[-1])+1`
				#and increment the last digit of the version by one.
				#We don't need to worry about _pre and friends because they're not supported with '*' deps.
				new_v=string.join(mynewsplit,".")+"_alpha0"
				#new_v will be used later in the code when we do our comparisons using pkgcmp()
			except:
				#erp, error.
				return [] 
			mynodes=[]
			cmp1=cp_key[1:]
			cmp1[1]=cmp1[1]+"_alpha0"
			cmp2=[cp_key[1],new_v,"r0"]
			for x in mylist:
				cp_x=catpkgsplit(x)
				if cp_x==None:
					#hrm, invalid entry.  Continue.
					continue
				#skip entries in our list that do not have matching categories
				if cp_key[0]!=cp_x[0]:
					continue
				# ok, categories match. Continue to next step.	
				if ((pkgcmp(cp_x[1:],cmp1)>=0) and (pkgcmp(cp_x[1:],cmp2)<0)):
					# entry is >= the version in specified in our dependency, and <= the version in our dep + 1; add it:
					mynodes.append(x)
			return mynodes
		else:
			# Does our stripped key appear literally in our list?  If so, we have a match; if not, we don't.
			if mycpv in mylist:
				return [mycpv]
			else:
				return []
	elif (mydep[0]==">") or (mydep[0]=="<"):
		if cp_key==None:
			return []
		if (len(mydep)>1) and (mydep[1]=="="):
			cmpstr=mydep[0:2]
		else:
			cmpstr=mydep[0]
		mynodes=[]
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
				#invalid entry; continue.
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if eval("pkgcmp(cp_x[1:],cp_key[1:])"+cmpstr+"0"):
				mynodes.append(x)
		return mynodes
	elif mydep[0]=="~":
		if cp_key==None:
			return []
		myrev=-1
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
				#invalid entry; continue
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if cp_key[2]!=cp_x[2]:
				#if version doesn't match, skip it
				continue
			if string.atoi(cp_x[3][1:])>myrev:
				myrev=string.atoi(cp_x[3][1:])
				mymatch=x
		if myrev==-1:
			return []
		else:
			return [mymatch]
	elif cp_key==None:
		if mydep[0]=="!":
			return []
			#we check ! deps in emerge itself, so always returning [] is correct.
		mynodes=[]
		cp_key=mycpv.split("/")
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
				#invalid entry; continue
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if cp_key[1]!=cp_x[1]:
				continue
			mynodes.append(x)
		return mynodes
	else:
		return []


class portagetree:
	def __init__(self,root="/",virtual=None,clone=None):
		global portdb
		if clone:
			self.root=clone.root
			self.portroot=clone.portroot
			self.pkglines=clone.pkglines
		else:
			self.root=root
			self.portroot=settings["PORTDIR"]
			self.virtual=virtual
			self.dbapi=portdb

	def dep_bestmatch(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("bestmatch-visible",mydep)
		if mymatch==None:
			return ""
		return mymatch

	def dep_match(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("match-visible",mydep)
		if mymatch==None:
			return []
		return mymatch

	def exists_specific(self,cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def getname(self,pkgname):
		"returns file location for this particular package (DEPRECATED)"
		if not pkgname:
			return ""
		mysplit=string.split(pkgname,"/")
		psplit=pkgsplit(mysplit[1])
		return self.portroot+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"

	def resolve_specific(self,myspec):
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey=key_expand(cps[0]+"/"+cps[1],self.dbapi)
		mykey=mykey+"-"+cps[2]
		if cps[3]!="r0":
			mykey=mykey+"-"+cps[3]
		return mykey

	def depcheck(self,mycheck,use="yes",myusesplit=None):
		return dep_check(mycheck,self.dbapi,use=use,myusesplit=myusesplit)


class dbapi:
	def __init__(self):
		pass
	
	def cp_list(self,cp,use_cache=1):
		return

	def aux_get(self,mycpv,mylist):
		"stub code for returning auxiliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		pass

	def match(self,origdep,use_cache=1):
		mydep=dep_expand(origdep,self)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		return match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))

	def match2(self,mydep,mykey,mylist):
		writemsg("DEPRECATED: dbapi.match2\n")
		match_from_list(mydep,mylist)

	def counter_tick(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,1,mycpv)

	def get_counter_tick_core(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,0,mycpv)+1

	def counter_tick_core(self,myroot,incrementing=1,mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		cpath=myroot+"var/cache/edb/counter"
		changed=0
		min_counter = 0
		if mycpv:
			mysplit = pkgsplit(mycpv)
			for x in self.match(mysplit[0],use_cache=0):
				# fixed bug #41062
				if x==mycpv:
					continue
				try:
					old_counter = long(self.aux_get(x,["COUNTER"])[0])
					writemsg("COUNTER '%d' '%s'\n" % (old_counter, x),1)
				except:
					old_counter = 0
					writemsg("!!! BAD COUNTER in '%s'\n" % (x))
				if old_counter > min_counter:
					min_counter = old_counter

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption.
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except (ValueError,OverflowError):
				try:
					counter=long(commands.getoutput("for FILE in $(find /"+VDB_PATH+" -type f -name COUNTER); do echo $(<${FILE}); done | sort -n | tail -n1 | tr -d '\n'"))
					writemsg("!!! COUNTER was corrupted; resetting to value of %d\n" % counter)
					changed=1
				except (ValueError,OverflowError):
					writemsg("!!! COUNTER data is corrupt in pkg db. The values need to be\n")
					writemsg("!!! corrected/normalized so that portage can operate properly.\n")
					writemsg("!!! A simple solution is not yet available so try #gentoo on IRC.\n")
					sys.exit(2)
			cfile.close()
		else:
			try:
				counter=long(commands.getoutput("for FILE in $(find /"+VDB_PATH+" -type f -name COUNTER); do echo $(<${FILE}); done | sort -n | tail -n1 | tr -d '\n'"))
				writemsg("!!! Global counter missing. Regenerated from counter files to: %s\n" % counter)
			except:
				writemsg("!!! Initializing global counter.\n")
				counter=long(0)
			changed=1

		if counter < min_counter:
			counter = min_counter+1000
			changed = 1

		if incrementing or changed:
			
			#increment counter
			counter += 1
			# update new global counter file
			newcpath=cpath+".new"
			newcfile=open(newcpath,"w")
			newcfile.write(str(counter))
			newcfile.close()
			# now move global counter file into place
			os.rename(newcpath,cpath)
		return counter

	def invalidentry(self, mypath):
		if re.search("portage_lockfile$",mypath):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				unlockfile((mypath,None,None))
			else:
				# Nothing we can do about it. We're probably sandboxed.
				pass
		elif re.search(".*/-MERGING-(.*)",mypath):
			if os.path.exists(mypath):
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n")
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath)



class fakedbapi(dbapi):
	"This is a dbapi to use for the emptytree function.  It's empty, but things can be added to it."
	def __init__(self):
		self.cpvdict={}
		self.cpdict={}

	def cpv_exists(self,mycpv):
		return self.cpvdict.has_key(mycpv)
	
	def cp_list(self,mycp,use_cache=1):
		if not self.cpdict.has_key(mycp):
			return []
		else:
			return self.cpdict[mycp]

	def cp_all(self):
		returnme=[]
		for x in self.cpdict.keys():
			returnme.extend(self.cpdict[x])
		return returnme

	def cpv_inject(self,mycpv):
		"""Adds a cpv from the list of available packages."""
		mycp=cpv_getkey(mycpv)
		self.cpvdict[mycpv]=1
		if not self.cpdict.has_key(mycp):
			self.cpdict[mycp]=[]
		if not mycpv in self.cpdict[mycp]:
			self.cpdict[mycp].append(mycpv)

	#def cpv_virtual(self,oldcpv,newcpv):
	#	"""Maps a cpv to the list of available packages."""
	#	mycp=cpv_getkey(newcpv)
	#	self.cpvdict[newcpv]=1
	#	if not self.virtdict.has_key(mycp):
	#		self.virtdict[mycp]=[]
	#	if not mycpv in self.virtdict[mycp]:
	#		self.virtdict[mycp].append(oldcpv)
	#	cpv_remove(oldcpv)

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		mycp=cpv_getkey(mycpv)
		if self.cpvdict.has_key(mycpv):
			del	self.cpvdict[mycpv]
		if not self.cpdict.has_key(mycp):
			return
		while mycpv in self.cpdict[mycp]:
			del self.cpdict[mycp][self.cpdict[mycp].index(mycpv)]
		if not len(self.cpdict[mycp]):
			del self.cpdict[mycp]

class bindbapi(fakedbapi):
	def __init__(self,mybintree=None):
		self.bintree = mybintree
		self.cpvdict={}
		self.cpdict={}

	def aux_get(self,mycpv,wants):
		mysplit = string.split(mycpv,"/")
		mylist  = []
		tbz2name = mysplit[1]+".tbz2"
		if self.bintree and self.bintree.isremote(mycpv):
			tbz2 = xpak.tbz2(self.bintree.getname(mycpv))
		for x in wants:
			if self.bintree and self.bintree.isremote(mycpv):
				# We use the cache for remote packages
				if self.bintree.remotepkgs[tbz2name].has_key(x):
					mylist.append(self.bintree.remotepkgs[tbz2name][x][:]) # [:] Copy String
				else:
					mylist.append("")
			else:
				try:
					myval = tbz2.getfile("USE")
				except:
					myval = ""
				mylist.append(myval)

		return mylist


cptot=0
class vardbapi(dbapi):
	def __init__(self,root):
		self.root=root
		#cache for category directory mtimes
		self.mtdircache={}
		#cache for dependency checks
		self.matchcache={}
		#cache for cp_list results
		self.cpcache={}	
		self.blockers=None

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.root+VDB_PATH+"/"+mykey)

	def cpv_counter(self,mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		cdir=self.root+VDB_PATH+"/"+mycpv
		cpath=self.root+VDB_PATH+"/"+mycpv+"/COUNTER"

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption on XFS (unexpected reboot.)
		corrupted=0
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except ValueError:
				print "portage: COUNTER for",mycpv,"was corrupted; resetting to value of 0"
				counter=long(0)
				corrupted=1
			cfile.close()
		elif os.path.exists(cdir):
			mys = pkgsplit(mycpv)
			myl = self.match(mys[0],use_cache=0)
			print mys,myl
			if len(myl) == 1:
				try:
					# Only one package... Counter doesn't matter.
					myf = open(cpath, "w")
					myf.write("1")
					myf.flush()
					myf.close()
					counter = 1
				except Exception, e:
					writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n")
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.pl or\n")
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n")
					writemsg("!!! unmerge this exact version.\n")
					writemsg("!!! %s\n" % e)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n")
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.pl or\n")
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n")
				writemsg("!!! remerge the package.\n")
				sys.exit(1)
		else:
			counter=long(0)
		if corrupted:
			newcpath=cpath+".new"
			# update new global counter file
			newcfile=open(newcpath,"w")
			newcfile.write(str(counter))
			newcfile.close()
			# now move global counter file into place
			os.rename(newcpath,cpath)
		return counter
	
	def cpv_inject(self,mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		os.makedirs(self.root+VDB_PATH+"/"+mycpv)	
		counter=db[self.root]["vartree"].dbapi.counter_tick(self.root,mycpv)
		# write local package counter so that emerge clean does the right thing
		lcfile=open(self.root+VDB_PATH+"/"+mycpv+"/COUNTER","w")
		lcfile.write(str(counter))
		lcfile.close()

	def isInjected(self,mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/INJECTED"):
				return True
			if not os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/CONTENTS"):
				return True
		return False

	def move_ent(self,mylist):
		origcp=mylist[1]
		newcp=mylist[2]
		origmatches=self.match(origcp,use_cache=0)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			mynewcpv=newcp+"-"+mycpsplit[2]
			mynewcat=newcp.split("/")[0]
			if mycpsplit[3]!="r0":
				mynewcpv += "-"+mycpsplit[3]
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue
			writemsg("@")
			if not os.path.exists(self.root+VDB_PATH+"/"+mynewcat):
				#create the directory
				os.makedirs(self.root+VDB_PATH+"/"+mynewcat)	
			newpath=self.root+VDB_PATH+"/"+mynewcpv
			if os.path.exists(newpath):
				#dest already exists; keep this puppy where it is.
				continue
			spawn("/bin/mv "+origpath+" "+newpath,settings, free=1)
			
			catfile=open(newpath+"/CATEGORY", "w")
			catfile.write(mynewcat+"\n")
			catfile.close()

		dbdir = self.root+VDB_PATH
		for catdir in listdir(dbdir):
			catdir = dbdir+"/"+catdir
			if os.path.isdir(catdir):
				for pkgdir in listdir(catdir):
					pkgdir = catdir+"/"+pkgdir
					if os.path.isdir(pkgdir):
						fixdbentries(origcp, newcp, pkgdir)
	
	def move_slot_ent(self,mylist):
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]

		origmatches=self.match(pkg,use_cache=0)
		if not origmatches:
			return
		for mycpv in origmatches:
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue

			slot=grabfile(origpath+"/SLOT");
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			writemsg("s")
			slotfile=open(origpath+"/SLOT", "w")
			slotfile.write(newslot+"\n")
			slotfile.close()

	def cp_list(self,mycp,use_cache=1):
		mysplit=mycp.split("/")
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat=os.stat(self.root+VDB_PATH+"/"+mysplit[0])[ST_MTIME]
		except OSError:
			mystat=0
		if use_cache and self.cpcache.has_key(mycp):
			cpc=self.cpcache[mycp]
			if cpc[0]==mystat:
				return cpc[1]
		list=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)

		if (list==None):
			return []
		returnme=[]
		for x in list:
			if x[0] == '-':
				#writemsg(red("INCOMPLETE MERGE:")+str(x[len("-MERGING-"):])+"\n")
				continue
			ps=pkgsplit(x)
			if not ps:
				self.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if len(mysplit) > 1:
				if ps[0]==mysplit[1]:
					returnme.append(mysplit[0]+"/"+x)
		if use_cache:
			self.cpcache[mycp]=[mystat,returnme]
		elif self.cpcache.has_key(mycp):
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self,use_cache=1):
		returnme=[]
		for x in settings.categories:
			for y in listdir(self.root+VDB_PATH+"/"+x,EmptyOnError=1):
				returnme += [x+"/"+y]
		return returnme

	def cp_all(self,use_cache=1):
		returnme=[]
		mylist = self.cpv_all(use_cache=use_cache)
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			mysplit=catpkgsplit(y)
			if not mysplit:
				self.invalidentry(self.root+VDB_PATH+"/"+y)
				continue
			mykey=mysplit[0]+"/"+mysplit[1]
			if not mykey in returnme:
				returnme.append(mykey)
		return returnme

	def checkblockers(self,origdep):
		pass

	def match(self,origdep,use_cache=1):
		"caching match function"
		mydep=dep_expand(origdep,self,use_cache=use_cache)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		if not use_cache:
			if self.matchcache.has_key(mycat):
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			return match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
		try:
			curmtime=os.stat(self.root+VDB_PATH+"/"+mycat)[ST_MTIME]
		except:
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat]=curmtime
			self.matchcache[mycat]={}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch=match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
			self.matchcache[mycat][mydep]=mymatch
		return self.matchcache[mycat][mydep][:]
	
	def aux_get(self, mycpv, wants):
		global auxdbkeys
		results = []
		if not self.cpv_exists(mycpv):
			return []
		for x in wants:
			myfn = self.root+VDB_PATH+"/"+str(mycpv)+"/"+str(x)
			if os.access(myfn,os.R_OK):
				myf = open(myfn, "r")
				myd = myf.read()
				myf.close()
				myd = re.sub("[\n\r\t]+"," ",myd)
				myd = re.sub(" +"," ",myd)
				myd = string.strip(myd)
			else:
				myd = ""
			results.append(myd)
		return results
		

class vartree(packagetree):
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self,root="/",virtual=None,clone=None):
		if clone:
			self.root=clone.root
			self.dbapi=clone.dbapi
			self.populated=1
		else:
			self.root=root
			self.dbapi=vardbapi(self.root)
			self.populated=1

	def zap(self,mycpv):
		return

	def inject(self,mycpv):
		return
		
	def get_provide(self,mycpv):
		myprovides=[]
		try:
			mylines = grabfile(self.root+VDB_PATH+"/"+mycpv+"/PROVIDE")
			if mylines:
				for myprovide in string.split(string.join(mylines)):
					mys = catpkgsplit(myprovide)
					if not mys:
						mys = string.split(myprovide, "/")
					myprovides += [mys[0] + "/" + mys[1]]
			return myprovides
		except Exception, e:
			print "mylines:",mylines
			print e
			return []

	def get_all_provides(self):
		myprovides = {}
		for node in self.getallcpv():
			for mykey in self.get_provide(node):
				if myprovides.has_key(mykey):
					myprovides[mykey] += [node]
				else:
					myprovides[mykey]  = [node]
		return myprovides
	
	def dep_bestmatch(self,mydep,use_cache=1):
		"compatibility method -- all matches, not just visible ones"
		#mymatch=best(match(dep_expand(mydep,self.dbapi),self.dbapi))
		mymatch=best(self.dbapi.match(dep_expand(mydep,self.dbapi),use_cache=use_cache))
		if mymatch==None:
			return ""
		else:
			return mymatch
			
	def dep_match(self,mydep,use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch=match(mydep,self.dbapi)
		mymatch=self.dbapi.match(mydep,use_cache=use_cache)
		if mymatch==None:
			return []
		else:
			return mymatch

	def exists_specific(self,cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallcpv(self):
		"""temporary function, probably to be renamed --- Gets a list of all
		category/package-versions installed on the system."""
		return self.dbapi.cpv_all()
	
	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def exists_specific_cat(self,cpv,use_cache=1):
		cpv=key_expand(cpv,self.dbapi,use_cache=use_cache)
		a=catpkgsplit(cpv)
		if not a:
			return 0
		mylist=listdir(self.root+VDB_PATH+"/"+a[0],EmptyOnError=1)
		for x in mylist:
			b=pkgsplit(x)
			if not b:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+a[0]+"/"+x)
				continue
			if a[1]==b[0]:
				return 1
		return 0
			
	def getebuildpath(self,fullpackage):
		cat,package=fullpackage.split("/")
		return self.root+VDB_PATH+"/"+fullpackage+"/"+package+".ebuild"

	def getnode(self,mykey,use_cache=1):
		mykey=key_expand(mykey,self.dbapi,use_cache=use_cache)
		if not mykey:
			return []
		mysplit=mykey.split("/")
		mydirlist=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)
		returnme=[]
		for x in mydirlist:
			mypsplit=pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if mypsplit[0]==mysplit[1]:
				appendme=[mysplit[0]+"/"+x,[mysplit[0],mypsplit[0],mypsplit[1],mypsplit[2]]]
				returnme.append(appendme)
		return returnme

	
	def getslot(self,mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			myslotfile=open(self.root+VDB_PATH+"/"+mycatpkg+"/SLOT","r")
			myslotvar=string.split(myslotfile.readline())
			myslotfile.close()
			if len(myslotvar):
				return myslotvar[0]
		except:
			pass
		return ""
	
	def hasnode(self,mykey,use_cache):
		"""Does the particular node (cat/pkg key) exist?"""
		mykey=key_expand(mykey,self.dbapi,use_cache=use_cache)
		mysplit=mykey.split("/")
		mydirlist=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)
		for x in mydirlist:
			mypsplit=pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if mypsplit[0]==mysplit[1]:
				return 1
		return 0
	
	def populate(self):
		self.populated=1

# ----------------------------------------------------------------------------
class eclass_cache:
	"""Maintains the cache information about eclasses used in ebuild."""
	def __init__(self,porttree_root,settings):
		self.porttree_root = porttree_root
		self.settings = settings
		self.cachedir = self.settings["PORTAGE_CACHEDIR"]

		self.dbmodule = self.settings.load_best_module("eclass_cache.dbmodule")

		self.packages = {} # {"PV": {"eclass1": ["location", "_mtime_"]}}
		self.eclasses = {} # {"Name": ["location","_mtime_"]}
		
		self.porttrees=self.settings["PORTDIR_OVERLAY"].split()+[self.porttree_root]
		self.update_eclasses()

	def flush_cache(self):
		self.packages = {}
		self.eclasses = {}
		self.update_eclasses()

	def update_eclasses(self):
		self.eclasses = {}
		for x in suffix_array(self.porttrees, "/eclass"):
			if x and os.path.exists(x):
				dirlist = listdir(x)
				for y in dirlist:
					if y[-len(".eclass"):]==".eclass":
						try:
							ys=y[:-len(".eclass")]
							ymtime=os.stat(x+"/"+y)[ST_MTIME]
						except:
							continue
						self.eclasses[ys] = [x, ymtime]
	
	def setup_package(self, location, cat, pkg):
		if not self.packages.has_key(location):
			self.packages[location] = {}

		if not self.packages[location].has_key(cat):
			self.packages[location][cat] = self.dbmodule(self.cachedir+"/"+location, cat+"-eclass", [], uid, portage_gid)
	
	def sync(self, location, cat, pkg):
		if self.packages[location].has_key(cat):
			self.packages[location][cat].sync()
	
	def update_package(self, location, cat, pkg, eclass_list):
		self.setup_package(location, cat, pkg)
		if not eclass_list:
			return 1

		data = {}
		for x in eclass_list:
			if x not in self.eclasses:
				writemsg("Eclass '%s' does not exist for '%s'\n" % (x, cat+"/"+pkg))
				return 0
			data[x] = [self.eclasses[x][0],self.eclasses[x][1]]
		
		self.packages[location][cat][pkg] = data
		self.sync(location,cat,pkg)
		return 1

	def is_current(self, location, cat, pkg, eclass_list):
		self.setup_package(location, cat, pkg)

		if not eclass_list:
			return 1

		if not (self.packages[location][cat].has_key(pkg) and self.packages[location][cat][pkg] and eclass_list):
			return 0

		eclass_list.sort()
		eclass_list = unique_array(eclass_list)
		
		ec_data = self.packages[location][cat][pkg].keys()
		ec_data.sort()
		if eclass_list != ec_data:
			return 0

		for x in eclass_list:
			if x not in self.eclasses:
				return 0
			data = self.packages[location][cat][pkg][x]
			if data[1] != self.eclasses[x][1]:
				return 0
			if data[0] != self.eclasses[x][0]:
				return 0

		return 1			
				
# ----------------------------------------------------------------------------

auxdbkeys=['DEPEND','RDEPEND','SLOT','SRC_URI','RESTRICT','HOMEPAGE','LICENSE','DESCRIPTION','KEYWORDS','INHERITED','IUSE','CDEPEND','PDEPEND']
auxdbkeylen=len(auxdbkeys)

class portdbapi(dbapi):
	"this tree will scan a portage directory located at root (passed to init)"
	def __init__(self,porttree_root,mysettings=None):

		if mysettings:
			self.mysettings = mysettings
		else:
			self.mysettings = config(clone=settings)

		#self.root=settings["PORTDIR"]
		self.porttree_root = porttree_root
		
		self.cachedir = self.mysettings["PORTAGE_CACHEDIR"]

		self.tmpfs = self.mysettings["PORTAGE_TMPFS"]
		if not os.path.exists(self.tmpfs):
			self.tmpfs = None
		
		self.eclassdb = eclass_cache(self.porttree_root, self.mysettings)

		self.metadb       = {}
		self.metadbmodule = self.mysettings.load_best_module("portdbapi.metadbmodule")
		
		self.auxdb        = {}
		self.auxdbmodule  = self.mysettings.load_best_module("portdbapi.auxdbmodule")

		#if the portdbapi is "frozen", then we assume that we can cache everything (that no updates to it are happening)
		self.xcache={}
		self.frozen=0

		self.porttrees=[self.porttree_root]+self.mysettings["PORTDIR_OVERLAY"].split()

	def flush_cache(self):
		self.metadb = {}
		self.auxdb  = {}
		self.eclassdb.flush_cache()
		
	def finddigest(self,mycpv):
		try:
			mydig   = self.findname2(mycpv)[0]
			mydigs  = string.split(mydig, "/")[:-1]
			mydig   = string.join(mydigs, "/")

			mysplit = mycpv.split("/")
		except:
			return ""
		return mydig+"/files/digest-"+mysplit[-1]

	def findname(self,mycpv):
		return self.findname2(mycpv)[0]

	def findname2(self,mycpv):
		"returns file location for this particular package"
		if not mycpv:
			return "",0
		mysplit=mycpv.split("/")
		if mysplit[0]=="virtual":
			print "!!! Cannot resolve a virtual package name to an ebuild."
			print "!!! This is a bug, please report it. ("+mycpv+")"
			sys.exit(1)
		
		psplit=pkgsplit(mysplit[1])
		ret=None
		if psplit:
			for x in self.porttrees:
				# XXX Why are there errors here? XXX
				try:
					file=x+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"
				except Exception, e:
					print
					print "!!! Problem with determining the name/location of an ebuild."
					print "!!! Please report this on IRC and bugs if you are not causing it."
					print "!!! mycpv:  ",mycpv
					print "!!! mysplit:",mysplit
					print "!!! psplit: ",psplit
					print "!!! error:  ",e
					print
					sys.exit(17)
					
				if os.access(file, os.R_OK):
					# when found
					ret=[file, x]
		if ret:
			return ret[0], ret[1]

		# when not found
		return None, 0

	def aux_get(self,mycpv,mylist,strict=0,metacachedir=None,debug=0):
		"stub code for returning auxilliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or raise KeyError if error'
		global auxdbkeys,auxdbkeylen
		cat,pkg = string.split(mycpv, "/", 1)
		
		if metacachedir:
			if cat not in self.metadb:
				self.metadb[cat] = self.metadbmodule(metacachedir,cat,auxdbkeys,uid,portage_gid)

		myebuild, mylocation=self.findname2(mycpv)
		if not myebuild:
			writemsg("!!! aux_get(): ebuild for '%s' does not exist at:\n" % mycpv)
			writemsg("!!!            %s\n" % myebuild)
			raise KeyError
			return None

		if mylocation not in self.auxdb:
			self.auxdb[mylocation] = {}

		if not self.auxdb[mylocation].has_key(cat):
			self.auxdb[mylocation][cat]=self.auxdbmodule(self.cachedir+"/"+mylocation,cat,auxdbkeys,uid,portage_gid)

		if os.access(myebuild, os.R_OK):
			emtime=os.stat(myebuild)[ST_MTIME]
		else:
			writemsg("!!! aux_get(): ebuild for '%s' does not exist at:\n" % mycpv)
			writemsg("!!!            %s\n" % myebuild)
			raise KeyError

		# when mylocation is not overlay directorys and metacachedir is set,
		# we use cache files, which is usually on /usr/portage/metadata/cache/.
		if mylocation==self.mysettings["PORTDIR"] and metacachedir and self.metadb[cat].has_key(pkg):
			metadata=self.metadb[cat][pkg]
			self.eclassdb.update_package(mylocation,cat,pkg,metadata["INHERITED"].split())
			self.auxdb[mylocation][cat][pkg]=metadata
		else:
			auxdb_is_valid = self.auxdb[mylocation][cat].has_key(pkg) and \
			                 self.auxdb[mylocation][cat][pkg].has_key("_mtime_") and \
			                 self.auxdb[mylocation][cat][pkg]["_mtime_"] == emtime
			writemsg("auxdb is valid: "+str(auxdb_is_valid)+" "+str(pkg)+"\n", 2)
			if auxdb_is_valid:
				doregen=0
			else:
				doregen=1

			if doregen or not self.eclassdb.is_current(mylocation,cat,pkg,self.auxdb[mylocation][cat][pkg]["INHERITED"].split()):
				writemsg("doregen: %s %s\n" % (doregen,mycpv), 2)
				writemsg("Generating cache entry(0) for: "+str(myebuild)+"\n",1)

				if self.tmpfs:
					mydbkey = self.tmpfs+"/aux_db_key_temp"
				else:
					mydbkey = self.cachedir+"/aux_db_key_temp"

				mylock = lockfile(mydbkey,unlinkfile=1)

				myret=doebuild(myebuild,"depend","/",self.mysettings,dbkey=mydbkey)
				if myret:
					unlockfile(mylock)
					#depend returned non-zero exit code...
					writemsg(str(red("\naux_get():")+" (0) Error in "+mycpv+" ebuild. ("+str(myret)+")\n"
         	   "               Check for syntax error or corruption in the ebuild. (--debug)\n\n"))
					raise KeyError

				try:
					mycent=open(mydbkey,"r")
					mylines=mycent.readlines()
					mycent.close()
				except (IOError, OSError):
					writemsg(str(red("\naux_get():")+" (1) Error in "+mycpv+" ebuild.\n"
					  "               Check for syntax error or corruption in the ebuild. (--debug)\n\n"))
					raise KeyError
				unlockfile(mylock)

				mydata = {}
				for x in range(0,len(mylines)):
					if mylines[x][-1] == '\n':
						mylines[x] = mylines[x][:-1]
					mydata[auxdbkeys[x]] = mylines[x]
				mydata["_mtime_"] = emtime

				self.auxdb[mylocation][cat][pkg] = mydata
				if not self.eclassdb.update_package(mylocation, cat, pkg, mylines[auxdbkeys.index("INHERITED")].split()):
					sys.exit(1)

		#finally, we look at our internal cache entry and return the requested data.
		returnme=[]
		for x in mylist:
			if self.auxdb[mylocation][cat][pkg].has_key(x):
				returnme.append(self.auxdb[mylocation][cat][pkg][x])
			else:
				returnme.append("")

		self.auxdb[mylocation][cat].sync()
		return returnme

	def getfetchlist(self,mypkg,useflags=None,mysettings=None,all=0):
		if mysettings == None:
			mysettings = self.mysettings
		try: myuris = self.aux_get(mypkg,["SRC_URI"])[0]
		except (IOError,KeyError):
			print red("getfetchlist():")+" aux_get() error; aborting."
			sys.exit(1)

		useflags = string.split(mysettings["USE"])
		
		myurilist = portage_dep.paren_reduce(myuris)
		myurilist = portage_dep.use_reduce(myurilist,useflags,matchall=all)
		newuris = flatten(myurilist)

		myfiles = []
		for x in newuris:
			mya = os.path.basename(x)
			if not mya in myfiles:
				myfiles.append(mya)
		return [newuris, myfiles]

	def getfetchsizes(self,mypkg,useflags=None,debug=0):
		# returns a filename:size dictionnary of remaining downloads
		mydigest=self.finddigest(mypkg)
		mymd5s=digestParseFile(mydigest)
		if not mymd5s:
			if debug: print "[empty/missing/bad digest]: "+mypkg
			return None
		filesdict={}
		if useflags == None:
			myuris, myfiles = self.getfetchlist(mypkg,all=1)
		else:
			myuris, myfiles = self.getfetchlist(mypkg,useflags=useflags)
		#XXX: maybe this should be improved: take partial downloads
		# into account? check md5sums?
		for myfile in myfiles:
			if debug and myfile not in mymd5s.keys():
				print "[bad digest]: missing",myfile,"for",mypkg
			elif myfile in mymd5s.keys():
				distfile=settings["DISTDIR"]+"/"+myfile
				if not os.access(distfile, os.R_OK):
					filesdict[myfile]=int(mymd5s[myfile][1])
		return filesdict

	def getsize(self,mypkg,useflags=None,debug=0):
		# returns the total size of remaining downloads
		#
		# we use getfetchsizes() now, so this function would be obsoleted
		#
		filesdict=self.getfetchsizes(mypkg,useflags,debug)
		if filesdict==None:
			return "[empty/missing/bad digest]"
		mysize=0
		for myfile in filesdict.keys():
			mysum+=filesdict[myfile]
		return mysum

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		cps2=mykey.split("/")
		cps=catpkgsplit(mykey,0)
		if not cps:
			#invalid cat/pkg-v
			return 0
		if self.findname2(cps[0]+"/"+cps2[1]):
			return 1
		else:
			return 0

	def cp_all(self):
		"returns a list of all keys in our tree"
		biglist=[]
		for x in self.mysettings.categories:
			for oroot in self.porttrees:
				for y in listdir(oroot+"/"+x,EmptyOnError=1,ignorecvs=1):
					mykey=x+"/"+y
					if not mykey in biglist:
						biglist.append(mykey)
		return biglist
	
	def p_list(self,mycp):
		returnme=[]
		for oroot in self.porttrees:
			for x in listdir(oroot+"/"+mycp,EmptyOnError=1,ignorecvs=1):
				if x[-7:]==".ebuild":
					mye=x[:-7]
					if not mye in returnme:
						returnme.append(mye)
		return returnme

	def cp_list(self,mycp,use_cache=1):
		mysplit=mycp.split("/")
		returnme=[]
		for oroot in self.porttrees:
			for x in listdir(oroot+"/"+mycp,EmptyOnError=1,ignorecvs=1):
				if x[-7:]==".ebuild":
					cp=mysplit[0]+"/"+x[:-7]
					if not cp in returnme:
						returnme.append(cp)
		return returnme

	def freeze(self):
		for x in ["list-visible","bestmatch-visible","match-visible","match-all"]:
			self.xcache[x]={}
		self.frozen=1

	def melt(self):
		self.xcache={}
		self.frozen=0

	def xmatch(self,level,origdep,mydep=None,mykey=None,mylist=None):
		"caching match function; very trick stuff"
		#if no updates are being made to the tree, we can consult our xcache...
		if self.frozen:
			try:
				return self.xcache[level][origdep]
			except KeyError:
				pass

		if not mydep:
			#this stuff only runs on first call of xmatch()
			#create mydep, mykey from origdep
			mydep=dep_expand(origdep,self)
			mykey=dep_getkey(mydep)
	
		if level=="list-visible":
			#a list of all visible packages, not called directly (just by xmatch())
			#myval=self.visible(self.cp_list(mykey))
			myval=self.gvisible(self.visible(self.cp_list(mykey)))
		elif level=="bestmatch-visible":
			#dep match -- best match of all visible packages
			myval=best(self.xmatch("match-visible",None,mydep,mykey))
			#get all visible matches (from xmatch()), then choose the best one
		elif level=="bestmatch-list":
			#dep match -- find best match but restrict search to sublist 
			myval=best(match_from_list(mydep,mylist))
			#no point is calling xmatch again since we're not caching list deps
		elif level=="match-list":
			#dep match -- find all matches but restrict search to sublist (used in 2nd half of visible())
			myval=match_from_list(mydep,mylist)
		elif level=="match-visible":
			#dep match -- find all visible matches
			myval=match_from_list(mydep,self.xmatch("list-visible",None,mydep,mykey))
			#get all visible packages, then get the matching ones
		elif level=="match-all":
			#match *all* visible *and* masked packages
			myval=match_from_list(mydep,self.cp_list(mykey))
		else:
			print "ERROR: xmatch doesn't handle",level,"query!"
			raise KeyError
		if self.frozen and (level not in ["match-list","bestmatch-list"]):
			self.xcache[level][mydep]=myval
		return myval

	def match(self,mydep,use_cache=1):
		return self.xmatch("match-visible",mydep)

	def visible(self,mylist):
		"""two functions in one.  Accepts a list of cpv values and uses the package.mask *and*
		packages file to remove invisible entries, returning remaining items.  This function assumes
		that all entries in mylist have the same category and package name."""
		if (mylist==None) or (len(mylist)==0):
			return []
		newlist=mylist[:]
		#first, we mask out packages in the package.mask file
		mykey=newlist[0]
		cpv=catpkgsplit(mykey)
		if not cpv:
			#invalid cat/pkg-v
			print "visible(): invalid cat/pkg-v:",mykey
			return []
		mycp=cpv[0]+"/"+cpv[1]
		maskdict=self.mysettings.pmaskdict
		unmaskdict=self.mysettings.punmaskdict
		if maskdict.has_key(mycp):
			for x in maskdict[mycp]:
				mymatches=self.xmatch("match-all",x)
				if mymatches==None:
					#error in package.mask file; print warning and continue:
					print "visible(): package.mask entry \""+x+"\" is invalid, ignoring..."
					continue
				for y in mymatches:
					unmask=0
					if unmaskdict.has_key(mycp):
						for z in unmaskdict[mycp]:
							mymatches_unmask=self.xmatch("match-all",z)
							if y in mymatches_unmask:
								unmask=1
								break
					if unmask==0:
						try:
							newlist.remove(y)
						except ValueError:
							pass

		revmaskdict=self.mysettings.prevmaskdict
		if revmaskdict.has_key(mycp):
			for x in revmaskdict[mycp]:
				#important: only match against the still-unmasked entries...
				#notice how we pass "newlist" to the xmatch() call below....
				#Without this, ~ deps in the packages files are broken.
				mymatches=self.xmatch("match-list",x,mylist=newlist)
				if mymatches==None:
					#error in packages file; print warning and continue:
					print "emerge: visible(): profile packages entry \""+x+"\" is invalid, ignoring..."
					continue
				pos=0
				while pos<len(newlist):
					if newlist[pos] not in mymatches:
						del newlist[pos]
					else:
						pos += 1
		return newlist

	def gvisible(self,mylist):
		"strip out group-masked (not in current group) entries"
		global groups
		if mylist==None:
			return []
		newlist=[]

		pkgdict = self.mysettings.pkeywordsdict
		for mycpv in mylist:
			#we need to update this next line when we have fully integrated the new db api
			auxerr=0
			try:
				myaux=db["/"]["porttree"].dbapi.aux_get(mycpv, ["KEYWORDS"])
			except (KeyError,IOError,TypeError):
				return []
			if not myaux[0]:
				# KEYWORDS=""
				#print "!!! No KEYWORDS for "+str(mycpv)+" -- Untested Status"
				continue
			mygroups=myaux[0].split()
			pgroups=groups[:]
			match=0
			for mykey in pkgdict:
				if db["/"]["porttree"].dbapi.xmatch("bestmatch-list", mykey, None, None, [mycpv]):
					pgroups.extend(pkgdict[mykey])
			for gp in mygroups:
				if gp=="*":
					writemsg("--- WARNING: Package '%s' uses '*' keyword.\n" % mycpv)
					match=1
					break
				elif "-"+gp in pgroups:
					match=0
					break
				elif gp in pgroups:
					match=1
					break
			if match:
				newlist.append(mycpv)
		return newlist
		
class binarytree(packagetree):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self,root,pkgdir,virtual=None,clone=None):
		
		if clone:
			# XXX This isn't cloning. It's an instance of the same thing.
			self.root=clone.root
			self.pkgdir=clone.pkgdir
			self.dbapi=clone.dbapi
			self.populated=clone.populated
			self.tree=clone.tree
			self.remotepkgs=clone.remotepkgs
			self.invalids=clone.invalids
		else:
			self.root=root
			#self.pkgdir=settings["PKGDIR"]
			self.pkgdir=pkgdir
			self.dbapi=bindbapi(self)
			self.populated=0
			self.tree={}
			self.remotepkgs={}
			self.invalids=[]

	def move_ent(self,mylist):
		if not self.populated:
			self.populate()
		origcp=mylist[1]
		newcp=mylist[2]
		origmatches=self.dbapi.cp_list(origcp)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			mynewcpv=newcp+"-"+mycpsplit[2]
			mynewcat=newcp.split("/")[0]
			mynewpkg=mynewcpv.split("/")[1]
			myoldpkg=mycpv.split("/")[1]
			if mycpsplit[3]!="r0":
				mynewcpv += "-"+mycpsplit[3]
			if (mynewpkg != myoldpkg) and os.path.exists(self.getname(mynewcpv)):
				writemsg("!!! Cannot update binary: Destination exists.\n")
				writemsg("!!! "+mycpv+" -> "+mynewcpv+"\n")
				continue
			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
				continue
			
			#print ">>> Updating data in:",mycpv
			sys.stdout.write("%")
			sys.stdout.flush()
			mytmpdir=settings["PORTAGE_TMPDIR"]+"/tbz2"
			mytbz2=xpak.tbz2(tbz2path)
			mytbz2.decompose(mytmpdir, cleanup=1)
			
			fixdbentries(origcp, newcp, mytmpdir)

			catfile=open(mytmpdir+"/CATEGORY", "w")
			catfile.write(mynewcat+"\n")
			catfile.close()
			try:
				os.rename(mytmpdir+"/"+string.split(mycpv,"/")[1]+".ebuild", mytmpdir+"/"+string.split(mynewcpv, "/")[1]+".ebuild")
			except Exception, e:
				pass
				
			mytbz2.recompose(mytmpdir, cleanup=1)
			
			self.dbapi.cpv_remove(mycpv)
			if (mynewpkg != myoldpkg):
				os.rename(tbz2path,self.getname(mynewcpv))
			self.dbapi.cpv_inject(mynewcpv)
		return 1

	def move_slot_ent(self,mylist,mytmpdir):
		#mytmpdir=settings["PORTAGE_TMPDIR"]+"/tbz2"
		mytmpdir=mytmpdir+"/tbz2"
		if not self.populated:
			self.populate()
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]
		origmatches=self.dbapi.match(pkg)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			myoldpkg=mycpv.split("/")[1]
			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
				continue
			
			#print ">>> Updating data in:",mycpv
			mytbz2=xpak.tbz2(tbz2path)
			mytbz2.decompose(mytmpdir, cleanup=1)

			slot=grabfile(mytmpdir+"/SLOT");
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			sys.stdout.write("S")
			sys.stdout.flush()

			slotfile=open(mytmpdir+"/SLOT", "w")
			slotfile.write(newslot+"\n")
			slotfile.close()
			mytbz2.recompose(mytmpdir, cleanup=1)
		return 1

	def update_ents(self,mybiglist,mytmpdir):
		#XXX mytmpdir=settings["PORTAGE_TMPDIR"]+"/tbz2"
		if not self.populated:
			self.populate()
		for mycpv in self.dbapi.cp_all():
			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
				continue
			#print ">>> Updating binary data:",mycpv
			writemsg("*")
			mytbz2=xpak.tbz2(tbz2path)
			mytbz2.decompose(mytmpdir,cleanup=1)
			for mylist in mybiglist:
				mylist=string.split(mylist)
				if mylist[0] != "move":
					continue
				fixdbentries(mylist[1], mylist[2], mytmpdir)
			mytbz2.recompose(mytmpdir,cleanup=1)
		return 1

	def populate(self, getbinpkgs=0,getbinpkgsonly=0):
		"populates the binarytree"
		if (not os.path.isdir(self.pkgdir) and not getbinpkgs):
			return 0
		if (not os.path.isdir(self.pkgdir+"/All") and not getbinpkgs):
			return 0

		if (not getbinpkgsonly) and os.path.exists(self.pkgdir+"/All"):
			for mypkg in listdir(self.pkgdir+"/All"):
				if mypkg[-5:]!=".tbz2":
					continue
				mytbz2=xpak.tbz2(self.pkgdir+"/All/"+mypkg)
				mycat=mytbz2.getfile("CATEGORY")
				if not mycat:
					#old-style or corrupt package
					writemsg("!!! Invalid binary package: "+mypkg+"\n")
					self.invalids.append(mypkg)
					continue
				mycat=string.strip(mycat)
				fullpkg=mycat+"/"+mypkg[:-5]
				mykey=dep_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					self.dbapi.cpv_inject(fullpkg)
				except:
					continue

		if getbinpkgs and not settings["PORTAGE_BINHOST"]:
			writemsg(red("!!! PORTAGE_BINHOST unset, but use is requested.\n"))

		if getbinpkgs and settings["PORTAGE_BINHOST"] and not self.remotepkgs:
			try:
				chunk_size = long(settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except:
				chunk_size = 3000

			writemsg(green("Fetching binary packages info...\n"))
			self.remotepkgs = getbinpkg.dir_get_metadata(settings["PORTAGE_BINHOST"], chunk_size=chunk_size)
			writemsg(green("  -- DONE!\n\n"))

			for mypkg in self.remotepkgs.keys():
				if not self.remotepkgs[mypkg].has_key("CATEGORY"):
					#old-style or corrupt package
					writemsg("!!! Invalid remote binary package: "+mypkg+"\n")
					del self.remotepkgs[mypkg]
					continue
				mycat=string.strip(self.remotepkgs[mypkg]["CATEGORY"])
				fullpkg=mycat+"/"+mypkg[:-5]
				mykey=dep_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					#print "cpv_inject("+str(fullpkg)+")"
					self.dbapi.cpv_inject(fullpkg)
					#print "  -- Injected"
				except:
					writemsg("!!! Failed to inject remote binary package:"+str(fullpkg)+"\n")
					del self.remotepkgs[mypkg]
					continue
		self.populated=1

	def inject(self,cpv):
		return self.dbapi.cpv_inject(cpv)
	
	def exists_specific(self,cpv):
		if not self.populated:
			self.populate()
		return self.dbapi.match(dep_expand("="+cpv,self.dbapi))

	def dep_bestmatch(self,mydep):
		"compatibility method -- all matches, not just visible ones"
		if not self.populated:
			self.populate()
		writemsg("\n\n", 1)
		writemsg("mydep: %s\n" % mydep, 1)
		mydep=dep_expand(mydep,self.dbapi)
		writemsg("mydep: %s\n" % mydep, 1)
		mykey=dep_getkey(mydep)
		writemsg("mykey: %s\n" % mykey, 1)
		mymatch=best(match_from_list(mydep,self.dbapi.cp_list(mykey)))
		writemsg("mymatch: %s\n" % mymatch, 1)
		if mymatch==None:
			return ""
		return mymatch

	def getname(self,pkgname):
		"returns file location for this particular package"
		mysplit=string.split(pkgname,"/")
		if len(mysplit)==1:
			return self.pkgdir+"/All/"+self.resolve_specific(pkgname)+".tbz2"
		else:
			return self.pkgdir+"/All/"+mysplit[1]+".tbz2"

	def isremote(self,pkgname):
		"Returns true if the package is kept remotely."
		mysplit=string.split(pkgname,"/")
		remote = (not os.path.exists(self.getname(pkgname))) and self.remotepkgs.has_key(mysplit[1]+".tbz2")
		return remote
	
	def get_use(self,pkgname):
		mysplit=string.split(pkgname,"/")
		if self.isremote(pkgname):
			return string.split(self.remotepkgs[mysplit[1]+".tbz2"]["USE"][:])
		tbz2=xpak.tbz2(self.getname(pkgname))
		return string.split(tbz2.getfile("USE"))
	
	def gettbz2(self,pkgname):
		"fetches the package from a remote site, if necessary."
		print "Fetching '"+str(pkgname)+"'"
		mysplit  = string.split(pkgname,"/")
		tbz2name = mysplit[1]+".tbz2"
		if not self.isremote(pkgname):
			if (tbz2name not in self.invalids):
				return
			else:
				writemsg("Resuming download of this tbz2, but it is possible that it is corrupt.\n")
		mydest = self.pkgdir+"/All/"
		try:
			os.makedirs(mydest, 0775)
		except:
			pass
		getbinpkg.file_get(settings["PORTAGE_BINHOST"]+"/"+tbz2name, mydest, fcmd=settings["RESUMECOMMAND"])
		return

class dblink:
	"this class provides an interface to the standard text package database"
	# XXX SETTINGS
	def __init__(self,cat,pkg,myroot,mysettings):
		"create a dblink object for cat/pkg.  This dblink entry may or may not exist"
		self.cat     = cat
		self.pkg     = pkg
		self.mycpv   = self.cat+"/"+self.pkg
		self.mysplit = pkgsplit(self.mycpv)
	
		self.dbroot   = os.path.normpath(myroot+VDB_PATH)
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir    = self.dbpkgdir
		
		self.lock_pkg = None
		self.lock_tmp = None
		self.lock_num = 0    # Count of the held locks on the db.
	
		self.settings = mysettings
		if self.settings==1:
			raise ValueError
	
		self.myroot=myroot
		self.updateprotect()

	def lockdb(self):
		if self.lock_num == 0:
			self.lock_pkg = lockdir(self.dbpkgdir)
			self.lock_tmp = lockdir(self.dbtmpdir)
		self.lock_num += 1
		
	def unlockdb(self):
		self.lock_num -= 1
		if self.lock_num == 0:
			unlockdir(self.lock_tmp)
			unlockdir(self.lock_pkg)

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir
	
	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)
	
	def create(self):
		"create the skeleton db directory structure.  No contents, virtuals, provides or anything.  Also will create /var/db/pkg if necessary."
		# XXXXX Delete this eventually
		raise Exception, "This is bad. Don't use it."
		if not os.path.exists(self.dbdir):
			os.makedirs(self.dbdir)
	
	def delete(self):
		"erase this db entry completely"
		if not os.path.exists(self.dbdir):
			return
		try:
			for x in listdir(self.dbdir):
				os.unlink(self.dbdir+"/"+x)
			os.rmdir(self.dbdir)
		except OSError, e:
			print "!!! Unable to remove db entry for this package."
			print "!!! It is possible that a directory is in this one. Portage will still"
			print "!!! register this package as installed as long as this directory exists."
			print "!!! You may delete this directory with 'rm -Rf "+self.dbdir+"'"
			print "!!! "+str(e)
			print
			sys.exit(1)
	
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
		pos=1
		for line in mylines:
			mydat = string.split(line)
			# we do this so we can remove from non-root filesystems
			# (use the ROOT var to allow maintenance on other partitions)
			try:
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
					if (x >= 13) and (mydat[-1][-1]==')'): # Old/Broken symlink entry
						mydat = mydat[:-10]+[mydat[-10:][ST_MTIME][:-1]]
						writemsg("FIXED SYMLINK LINE: %s\n" % mydat, 1)
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
			except (KeyError,IndexError):
				print "portage: CONTENTS line",pos,"corrupt!"
			pos += 1
		return pkgfiles

	def updateprotect(self):
		#do some config file management prep
		self.protect=[]
		for x in string.split(self.settings["CONFIG_PROTECT"]):
			ppath=os.path.normpath(self.myroot+"///"+x)+"/"
			if os.path.isdir(ppath):
				self.protect.append(ppath)
			
		self.protectmask=[]
		for x in string.split(self.settings["CONFIG_PROTECT_MASK"]):
			ppath=os.path.normpath(self.myroot+"///"+x)+"/"
			if os.path.isdir(ppath):
				self.protectmask.append(ppath)
			#if it doesn't exist, silently skip it

	def isprotected(self,obj):
		"""Checks if obj is in the current protect/mask directories. Returns
		0 on unprotected/masked, and 1 on protected."""
		masked=0
		protected=0
		for ppath in self.protect:
			if (len(ppath) > masked) and (obj[0:len(ppath)]==ppath):
				protected=len(ppath)
				#config file management
				for pmpath in self.protectmask:
					if (len(pmpath) >= protected) and (obj[0:len(pmpath)]==pmpath):
						#skip, it's in the mask
						masked=len(pmpath)
		return (protected > masked)

	def unmerge(self,pkgfiles=None,trimworld=1,cleanup=0):
		global dircache
		dircache={}
		
		self.lockdb()
		
		self.settings.load_infodir(self.dbdir)

		if not pkgfiles:
			print "No package files given... Grabbing a set."
			pkgfiles=self.getcontents()

		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath=None
		
		# We should use the environement file if possible,
		# as it has all sourced files already included.
		# XXX: Need to ensure it doesn't overwrite any important vars though.
		if os.access(self.dbdir+"/environment.bz2", os.R_OK):
			spawn("bzip2 -d "+self.dbdir+"/environment.bz2",self.settings,free=1)
		
		if not myebuildpath:
			mystuff=listdir(self.dbdir,EmptyOnError=1)
			for x in mystuff:
				if x[-7:]==".ebuild":
					myebuildpath=self.dbdir+"/"+x
					break

		#do prerm script
		if myebuildpath and os.path.exists(myebuildpath):
			a=doebuild(myebuildpath,"prerm",self.myroot,self.settings,cleanup=cleanup,use_cache=0)
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED prerm: "+str(a)+"\n")
				sys.exit(123)

		if pkgfiles:
			mykeys=pkgfiles.keys()
			mykeys.sort()
			mykeys.reverse()

			self.updateprotect()

			#process symlinks second-to-last, directories last.
			mydirs=[]
			mysyms=[]
			modprotect="/lib/modules/"
			for obj in mykeys:
				obj=os.path.normpath(obj)
				if obj[:2]=="//":
					obj=obj[1:]
				if not os.path.exists(obj):
					if not os.path.islink(obj):
						#we skip this if we're dealing with a symlink
						#because os.path.exists() will operate on the
						#link target rather than the link itself.
						print "--- !found "+str(pkgfiles[obj][0]), obj
						continue
				# next line includes a tweak to protect modules from being unmerged,
				# but we don't protect modules from being overwritten if they are
				# upgraded. We effectively only want one half of the config protection
				# functionality for /lib/modules. For portage-ng both capabilities
				# should be able to be independently specified.
				if self.isprotected(obj) or ((len(obj) > len(modprotect)) and (obj[0:len(modprotect)]==modprotect)):
					print "--- cfgpro "+str(pkgfiles[obj][0]), obj
					continue

				lstatobj=os.lstat(obj)
				lmtime=str(lstatobj[ST_MTIME])
				if (pkgfiles[obj][0] not in ("dir","fif","dev","sym")) and (lmtime != pkgfiles[obj][1]):
					print "--- !mtime", pkgfiles[obj][0], obj
					continue

				if pkgfiles[obj][0]=="dir":
					if not os.path.isdir(obj):
						print "--- !dir  ","dir", obj
						continue
					mydirs.append(obj)
				elif pkgfiles[obj][0]=="sym":
					if not os.path.islink(obj):
						print "--- !sym  ","sym", obj
						continue
					mysyms.append(obj)
				elif pkgfiles[obj][0]=="obj":
					if not os.path.isfile(obj):
						print "--- !obj  ","obj", obj
						continue
					mymd5=perform_md5(obj, calc_prelink=1)

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != string.lower(pkgfiles[obj][2]):
						print "--- !md5  ","obj", obj
						continue
					try:
						os.unlink(obj)
					except (OSError,IOError),e:
						pass		
					print "<<<       ","obj",obj
				elif pkgfiles[obj][0]=="fif":
					if not S_ISFIFO(lstatobj[ST_MODE]):
						print "--- !fif  ","fif", obj
						continue
					try:
						os.unlink(obj)
					except (OSError,IOError),e:
						pass
					print "<<<       ","fif",obj
				elif pkgfiles[obj][0]=="dev":
					print "---       ","dev",obj

			#Now, we need to remove symlinks and directories.  We'll repeatedly
			#remove dead symlinks, then directories until we stop making progress.
			#This is how we'll clean up directories containing symlinks pointing to
			#directories that are now empty.  These cases will require several
			#iterations through our two-stage symlink/directory cleaning loop.
	
			#main symlink and directory removal loop:
	
			#progress -- are we making progress?  Initialized to 1 so loop will start
			progress=1
			while progress:
				#let's see if we're able to make progress this iteration...
				progress=0
	
				#step 1: remove all the dead symlinks we can...
	
				pos = 0
				while pos<len(mysyms):
					obj=mysyms[pos]
					if os.path.exists(obj):
						pos += 1
					else:
						#we have a dead symlink; remove it from our list, then from existence
						del mysyms[pos]
						#we've made progress!	
						progress = 1
						try:
							os.unlink(obj)
							print "<<<       ","sym",obj
						except (OSError,IOError),e:
							print "!!!       ","sym",obj
							#immutable?
							pass
		
				#step 2: remove all the empty directories we can...
		
				pos = 0
				while pos<len(mydirs):
					obj=mydirs[pos]
					objld=listdir(obj)
					if objld == None:
						print "mydirs["+str(pos)+"]",mydirs[pos]
						print "obj",obj
						print "objld",objld
						# the directory doesn't exist yet, continue
						pos += 1
						continue
					if len(objld)>0:
						#we won't remove this directory (yet), continue
						pos += 1
						continue
					elif (objld != None):
						#zappo time
						del mydirs[pos]
						#we've made progress!
						progress = 1
						try:
							os.rmdir(obj)
							print "<<<       ","dir",obj
						except (OSError,IOError),e:
							#immutable?
							pass
					#else:
					#	print "--- !empty","dir", obj
					#	continue
			
				#step 3: if we've made progress, we'll give this another go...
	
			#step 4: otherwise, we'll print out the remaining stuff that we didn't unmerge (and rightly so!)
	
			#directories that aren't empty:
			for x in mydirs:
				print "--- !empty dir", x
				
			#symlinks whose target still exists:
			for x in mysyms:
				print "--- !targe sym", x

		#step 5: well, removal of package objects is complete, now for package *meta*-objects....

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		db[self.myroot]["vartree"].zap(self.mycpv)

		# New code to remove stuff from the world and virtuals files when unmerged.
		if trimworld:
			worldlist=grabfile(self.myroot+"var/cache/edb/world")
			mykey=cpv_getkey(self.mycpv)
			newworldlist=[]
			for x in worldlist:
				if dep_getkey(x)==mykey:
					matches=db[self.myroot]["vartree"].dbapi.match(x,use_cache=0)
					if not matches:
						#zap our world entry
						pass
					elif (len(matches)==1) and (matches[0]==self.mycpv):
						#zap our world entry
						pass
					else:
						#others are around; keep it.
						newworldlist.append(x)
				else:
					#this doesn't match the package we're unmerging; keep it.
					newworldlist.append(x)
			myworld=open(self.myroot+"var/cache/edb/world","w")
			for x in newworldlist:
				myworld.write(x+"\n")
			myworld.close()

			#remove stale virtual entries (mappings for packages that no longer exist)
			newvirts={}
			myvirts=grabdict(self.myroot+"var/cache/edb/virtuals")
			myprovides=db[self.myroot]["vartree"].get_all_provides()
			for myvirt in myvirts.keys():
				newvirts[myvirt]=[]
				for mykey in myvirts[myvirt]:
					if mykey == self.cat+"/"+pkgsplit(self.pkg)[0] and myprovides.has_key(myvirt) and myprovides[myvirt].count(self.mycpv)>0:
						# remove myself first
						myprovides[myvirt].remove(self.mycpv)
						for x in myprovides[myvirt]:
							if pkgsplit(x)[0]==mykey:
								if mykey not in newvirts[myvirt]:
									newvirts[myvirt].append(mykey)
								writemsg("--- Leaving virtual '"+mykey+"' from '"+myvirt+"'\n")
								break
						else:
							writemsg("<<< Removing virtual '"+mykey+"' from '"+myvirt+"'\n")
					else:
						if mykey not in newvirts[myvirt]:
							newvirts[myvirt].append(mykey)
				if newvirts[myvirt]==[]:
					del newvirts[myvirt]
					writemsg("<<< Removing virtual '"+myvirt+"'\n")

			writedict(newvirts,self.myroot+"var/cache/edb/virtuals")
	
		#do original postrm
		if myebuildpath and os.path.exists(myebuildpath):
			# XXX: This should be the old config, not the current one.
			# XXX: Use vardbapi to load up env vars.
			a=doebuild(myebuildpath,"postrm",self.myroot,self.settings,use_cache=0)
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED postrm: "+str(a)+"\n")
				sys.exit(123)

		self.unlockdb()

	def treewalk(self,srcroot,destroot,inforoot,myebuild,cleanup=0):
		global db
		# srcroot  = ${D};
		# destroot = where to merge, ie. ${ROOT},
		# inforoot = root of db entry,
		# secondhand = list of symlinks that have been skipped due to
		#              their target not existing (will merge later),

		if not os.path.exists(self.dbcatdir):
			os.makedirs(self.dbcatdir)

		# This blocks until we can get the dirs to ourselves.
		self.lockdb()

		# get old contents info for later unmerging
		oldcontents = self.getcontents()

		self.dbdir = self.dbtmpdir
		self.delete()
		if not os.path.exists(self.dbtmpdir):
			os.makedirs(self.dbtmpdir)
		
		print ">>> Merging",self.mycpv,"to",destroot

		# run preinst script
		if myebuild:
			# if we are merging a new ebuild, use *its* pre/postinst rather than using the one in /var/db/pkg 
			# (if any).
			a=doebuild(myebuild,"preinst",root,self.settings,cleanup=cleanup,use_cache=0)
		else:
			a=doebuild(inforoot+"/"+self.pkg+".ebuild","preinst",root,self.settings,cleanup=cleanup,use_cache=0)

		# XXX: Decide how to handle failures here.
		if a != 0:
			writemsg("!!! FAILED preinst: "+str(a)+"\n")
			sys.exit(123)

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# get current counter value (counter_tick also takes care of incrementing it)
		# XXX Need to make this destroot, but it needs to be initialized first. XXX
		# XXX bis: leads to some invalidentry() call through cp_all().
		counter = db["/"]["vartree"].dbapi.counter_tick(self.myroot,self.mycpv)
		# write local package counter for recording
		lcfile = open(self.dbtmpdir+"/COUNTER","w")
		lcfile.write(str(counter))
		lcfile.close()

		# open CONTENTS file (possibly overwriting old one) for recording
		outfile=open(self.dbtmpdir+"/CONTENTS","w")

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		if os.path.exists(destroot+"/var/cache/edb/config"):
			cfgfiledict=grabdict(destroot+"/var/cache/edb/config")
		else:
			cfgfiledict={}
		if self.settings.has_key("NOCONFMEM"):
			cfgfiledict["IGNORE"]=1
		else:
			cfgfiledict["IGNORE"]=0

		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		mymtime    = long(time.time())
		prevmask   = os.umask(0)
		secondhand = []

		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		if self.mergeme(srcroot,destroot,outfile,secondhand,"",cfgfiledict,mymtime):
			return 1

		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen=0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that
			# couldn't get merged will be added to thirdhand.

			thirdhand=[]
			self.mergeme(srcroot,destroot,outfile,thirdhand,secondhand,cfgfiledict,mymtime)

			#swap hands
			lastlen=len(secondhand)
			
			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			self.mergeme(srcroot,destroot,outfile,None,secondhand,cfgfiledict,mymtime)
		
		#restore umask
		os.umask(prevmask)

		#if we opened it, close it
		outfile.flush()
		outfile.close()

		if (oldcontents):
			print ">>> Safely unmerging already-installed instance..."
			self.dbdir = self.dbpkgdir
			self.unmerge(oldcontents,trimworld=0)
			self.dbdir = self.dbtmpdir
			print ">>> original instance of package unmerged safely."	

		# We hold both directory locks.
		self.dbdir = self.dbpkgdir
		self.delete()
		movefile(self.dbtmpdir, self.dbpkgdir, mysettings=self.settings)

		self.unlockdb()

		#write out our collection of md5sums
		if cfgfiledict.has_key("IGNORE"):
			del cfgfiledict["IGNORE"]

		mylock = lockfile(destroot+"/var/cache/edb/config")
		writedict(cfgfiledict,destroot+"/var/cache/edb/config")
		unlockfile(mylock)
		
		#create virtual links
		mylock = lockfile(destroot+"var/cache/edb/virtuals")
		myprovides=self.getelements("PROVIDE")
		if myprovides:
			myvkey=self.cat+"/"+pkgsplit(self.pkg)[0]
			myvirts=grabdict(destroot+"var/cache/edb/virtuals")
			for mycatpkg in self.getelements("PROVIDE"):
				if isspecific(mycatpkg):
					#convert a specific virtual like dev-lang/python-2.2 to dev-lang/python
					mysplit=catpkgsplit(mycatpkg)
					if not mysplit:
						print "treewalk(): skipping invalid PROVIDE entry:",mycatpkg
						continue
					mycatpkg=mysplit[0]+"/"+mysplit[1]
				if myvirts.has_key(mycatpkg):
					if myvkey not in myvirts[mycatpkg]:
						myvirts[mycatpkg][0:0]=[myvkey]
				else:
					myvirts[mycatpkg]=[myvkey]
			writedict(myvirts,destroot+"var/cache/edb/virtuals")
		unlockfile(mylock)
		
		#do postinst script
		if myebuild:
			# if we are merging a new ebuild, use *its* pre/postinst rather than using the one in /var/db/pkg 
			# (if any).
			a=doebuild(myebuild,"postinst",root,self.settings,use_cache=0)
		else:
			a=doebuild(inforoot+"/"+self.pkg+".ebuild","postinst",root,self.settings,use_cache=0)

		# XXX: Decide how to handle failures here.
		if a != 0:
			writemsg("!!! FAILED postinst: "+str(a)+"\n")
			sys.exit(123)
	
		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=0)
		#dircache may break autoclean because it remembers the -MERGING-pkg file
		global dircache
		if dircache.has_key(self.dbcatdir):
			del dircache[self.dbcatdir]
		print ">>>",self.mycpv,"merged."


	def new_protect_filename(self, mydest, newmd5=None):
		"""Resolves a config-protect filename for merging, optionally
		using the last filename if the md5 matches.
		(dest,md5) ==> 'string'            --- path_to_target_filename
		(dest)     ==> ('next', 'highest') --- next_target and most-recent_target
		"""

		# config protection filename format:
		# ._cfg0000_foo
		# 0123456789012
		prot_num=-1
		last_pfile=""
		
		if (len(mydest) == 0):
			raise ValueError, "Empty path provided where a filename is required"
		if (mydest[-1]=="/"): # XXX add better directory checking
			raise ValueError, "Directory provided but this function requires a filename"
		if not os.path.exists(mydest):
			return mydest
		
		real_filename = os.path.basename(mydest)
		real_dirname  = os.path.dirname(mydest)
		for pfile in listdir(real_dirname):
			if pfile[0:5] != "._cfg":
				continue
			if pfile[10:] != real_filename:
				continue
			try:
				new_prot_num = string.atoi(pfile[5:9])
				if new_prot_num > prot_num:
					prot_num = new_prot_num
					last_pfile = pfile
			except:
				continue
		prot_num = prot_num + 1

		new_pfile = os.path.normpath(real_dirname+"/._cfg"+string.zfill(prot_num,4)+"_"+real_filename)
		old_pfile = os.path.normpath(real_dirname+"/"+last_pfile)
		if last_pfile and newmd5:
			if perform_md5(real_dirname+"/"+last_pfile) == newmd5:
				return old_pfile
			else:
				return new_pfile
		elif newmd5:
			return new_pfile
		else:
			return (new_pfile, old_pfile)
		
	def mergeme(self,srcroot,destroot,outfile,secondhand,stufftomerge,cfgfiledict,thismtime):
		srcroot=os.path.normpath("///"+srcroot)+"/"
		destroot=os.path.normpath("///"+destroot)+"/"
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if type(stufftomerge)==types.StringType:
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist=listdir(srcroot+stufftomerge)
			offset=stufftomerge
			# We need mydest defined up here to calc. protection paths.  This is now done once per
			# directory rather than once per file merge.  This should really help merge performance.
			# Trailing / ensures that protects/masks with trailing /'s match.
			mytruncpath="/"+offset+"/"
			myppath=self.isprotected(mytruncpath)
		else:
			mergelist=stufftomerge
			offset=""
		for x in mergelist:
			mysrc=os.path.normpath("///"+srcroot+offset+x)
			mydest=os.path.normpath("///"+destroot+offset+x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest="/"+offset+x
			# stat file once, test using S_* macros many times (faster that way)
			try:
				mystat=os.lstat(mysrc)
			except OSError, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: There appears to be ")+bold("FILE SYSTEM CORRUPTION.")+red(" A file that is listed\n"))
				writemsg(red("!!!        as existing is not capable of being stat'd. If you are using an\n"))
				writemsg(red("!!!        experimental kernel, please boot into a stable one, force an fsck,\n"))
				writemsg(red("!!!        and ensure your filesystem is in a sane state. ")+bold("'shutdown -Fr now'\n"))
				writemsg(red("!!!        File:  ")+str(mysrc)+"\n")
				writemsg(red("!!!        Error: ")+str(e)+"\n")
				sys.exit(1)
			except Exception, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: An unknown error has occurred during the merge process.\n"))
				writemsg(red("!!!        A stat call returned the following error for the following file:"))
				writemsg(    "!!!        Please ensure that your filesystem is intact, otherwise report\n")
				writemsg(    "!!!        this as a portage bug at bugs.gentoo.org. Append 'emerge info'.\n")
				writemsg(    "!!!        File:  "+str(mysrc)+"\n")
				writemsg(    "!!!        Error: "+str(e)+"\n")
				sys.exit(1)
				
				
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
				myabsto=abssymlink(mysrc)
				if myabsto[0:len(srcroot)]==srcroot:
					myabsto=myabsto[len(srcroot):]
					if myabsto[0]!="/":
						myabsto="/"+myabsto
				myto=os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.find(self.settings["D"])==0:
						myto=myto[len(self.settings["D"]):]
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto=os.path.normpath(os.path.join(destroot,myabsto))
				if mydmode!=None:
					#destination exists
					if not S_ISLNK(mydmode):
						if S_ISDIR(mydmode):
							# directory in the way: we can't merge a symlink over a directory
							# we won't merge this, continue with next file...
							continue
						if self.isprotected(mydest):
							# Use md5 of the target in ${D} if it exists...
							if os.path.exists(os.path.normpath(srcroot+myabsto)):
								mydest = self.new_protect_filename(myrealdest, perform_md5(srcroot+myabsto))
							else:
								mydest = self.new_protect_filename(myrealdest, perform_md5(myabsto))
								
				# if secondhand==None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand!=None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				mymtime=movefile(mysrc,mydest,thismtime,mystat, mysettings=self.settings)
				if mymtime!=None:
					print ">>>",mydest,"->",myto
					outfile.write("sym "+myrealdest+" -> "+myto+" "+str(mymtime)+"\n")
				else:
					print "!!! Failed to move file."
					print "!!!",mydest,"->",myto
					sys.exit(1)
			elif S_ISDIR(mymode):
				# we are merging a directory
				if mydmode!=None:
					# destination exists
					if not os.access(mydest, os.W_OK):
						pkgstuff = pkgsplit(self.pkg)
						writemsg("\n!!! Cannot write to '"+mydest+"'.\n")
						writemsg("!!! Please check permissions and directories for broken symlinks.\n")
						writemsg("!!! You may start the merge process again by using ebuild:\n")
						writemsg("!!! ebuild "+self.settings["PORTDIR"]+"/"+self.cat+"/"+pkgstuff[0]+"/"+self.pkg+".ebuild merge\n")
						writemsg("!!! And finish by running this: env-update\n\n")
						return 1

					if S_ISLNK(mydmode) or S_ISDIR(mydmode):
						# a symlink to an existing directory will work for us; keep it:
						print "---",mydest+"/"
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						if movefile(mydest,mydest+".backup", mysettings=self.settings) == None:
							sys.exit(1)
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
				if self.mergeme(srcroot,destroot,outfile,secondhand,offset+x+"/",cfgfiledict,thismtime):
					return 1
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
						cfgprot=0
						# install of destination is blocked by an existing regular file;
						# now, config file management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if myppath:
							# we have a protection path; enable config file management.
							destmd5=perform_md5(mydest)
							cycled=0
							if cfgfiledict.has_key(myrealdest):
								if destmd5 in cfgfiledict[myrealdest]:
									#cycle
									print "cycle"
									del cfgfiledict[myrealdest]
									cycled=1
							if mymd5==destmd5:
								#file already in place; simply update mtimes of destination
								os.utime(mydest,(thismtime,thismtime))
								zing="---"
								moveme=0
							elif cycled:
								#mymd5!=destmd5 and we've cycled; move mysrc into place as a ._cfg file
								moveme=1
								cfgfiledict[myrealdest]=[mymd5]
								cfgprot=1
							elif cfgfiledict.has_key(myrealdest) and (mymd5 in cfgfiledict[myrealdest]):
								#myd5!=destmd5, we haven't cycled, and the file we're merging has been already merged previously 
								zing="-o-"
								moveme=cfgfiledict["IGNORE"]
								cfgprot=cfgfiledict["IGNORE"]
							else:	
								#mymd5!=destmd5, we haven't cycled, and the file we're merging hasn't been merged before
								moveme=1
								cfgprot=1
								if not cfgfiledict.has_key(myrealdest):
									cfgfiledict[myrealdest]=[]
								if mymd5 not in cfgfiledict[myrealdest]:
									cfgfiledict[myrealdest].append(mymd5)
								#don't record more than 16 md5sums
								if len(cfgfiledict[myrealdest])>16:
									del cfgfiledict[myrealdest][0]
	
						if cfgprot:
							mydest = self.new_protect_filename(myrealdest, mymd5)

				# whether config protection or not, we merge the new file the
				# same way.  Unless moveme=0 (blocking directory)
				if moveme:
					mymtime=movefile(mysrc,mydest,thismtime,mystat, mysettings=self.settings)
					if mymtime == None:
						sys.exit(1)
					zing=">>>"
				else:
					mymtime=thismtime
					# We need to touch the destination so that on --update the
					# old package won't yank the file with it. (non-cfgprot related)
					os.utime(myrealdest,(thismtime,thismtime))
					zing="---"
				if mymtime!=None:
					zing=">>>"
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				print zing,mydest
			else:
				# we are merging a fifo or device node
				zing="!!!"
				if mydmode==None:
					# destination doesn't exist
					if movefile(mysrc,mydest,thismtime,mystat, mysettings=self.settings)!=None:
						zing=">>>"
						if S_ISFIFO(mymode):
							# we don't record device nodes in CONTENTS,
							# although we do merge them.
							outfile.write("fif "+myrealdest+"\n")
					else:
						sys.exit(1)
				print zing+" "+mydest
	
	def merge(self,mergeroot,inforoot,myroot,myebuild=None,cleanup=0):
		return self.treewalk(mergeroot,myroot,inforoot,myebuild,cleanup=cleanup)

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		myfile=open(self.dbdir+"/"+name,"r")
		mydata=string.split(myfile.read())
		myfile.close()
		return string.join(mydata," ")
	
	def copyfile(self,fname):
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))
	
	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		myfile=open(self.dbdir+"/"+fname,"r")
		mydata=myfile.read()
		myfile.close()
		return mydata

	def setfile(self,fname,data):
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
		myelement=open(self.dbdir+"/"+ename,"w")
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()
	
	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(self.dbdir+"/CATEGORY")

def cleanup_pkgmerge(mypkg,origdir):
	shutil.rmtree(settings["PORTAGE_TMPDIR"]+"/portage-pkg/"+mypkg)
	if os.path.exists(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment"):
		os.unlink(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment")
	os.chdir(origdir)

def pkgmerge(mytbz2,myroot,mysettings):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""
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
	tmploc=mysettings["PORTAGE_TMPDIR"]+"/portage-pkg/"
	pkgloc=tmploc+"/"+mypkg+"/bin/"
	infloc=tmploc+"/"+mypkg+"/inf/"
	myebuild=tmploc+"/"+mypkg+"/inf/"+os.path.basename(mytbz2)[:-4]+"ebuild"
	if os.path.exists(tmploc+"/"+mypkg):
		shutil.rmtree(tmploc+"/"+mypkg,1)
	os.makedirs(pkgloc)
	os.makedirs(infloc)
	print ">>> extracting info"
	xptbz2.unpackinfo(infloc)
	# run pkg_setup early, so we can bail out early
	# (before extracting binaries) if there's a problem
	origdir=getcwd()
	os.chdir(pkgloc)
	print ">>> extracting",mypkg
	notok=spawn("bzip2 -dqc -- '"+mytbz2+"' | tar xpf -",mysettings,free=1)
	if notok:
		print "!!! Error extracting",mytbz2
		cleanup_pkgmerge(mypkg,origdir)
		return None

	# the merge takes care of pre/postinst and old instance
	# auto-unmerge, virtual/provides updates, etc.
	mysettings.load_infodir(infloc)
	mylink=dblink(mycat,mypkg,myroot,mysettings)
	mylink.merge(pkgloc,infloc,myroot,myebuild,cleanup=1)

	if not os.path.exists(infloc+"/RDEPEND"):
		returnme=""
	else:
		#get runtime dependencies
		a=open(infloc+"/RDEPEND","r")
		returnme=string.join(string.split(a.read())," ")
		a.close()
	cleanup_pkgmerge(mypkg,origdir)
	return returnme


if os.environ.has_key("ROOT"):
	root=os.environ["ROOT"]
	if not len(root):
		root="/"
	elif root[-1]!="/":
		root=root+"/"
else:
	root="/"
if root != "/":
	if not os.path.exists(root[:-1]):
		writemsg("!!! Error: ROOT "+root+" does not exist.  Please correct this.\n")
		writemsg("!!! Exiting.\n\n")
		sys.exit(1)
	elif not os.path.isdir(root[:-1]):
		writemsg("!!! Error: ROOT "+root[:-1]+" is not a directory. Please correct this.\n")
		writemsg("!!! Exiting.\n\n")
		sys.exit(1)

#create tmp and var/tmp if they don't exist; read config
os.umask(0)
if not os.path.exists(root+"tmp"):
	writemsg(">>> "+root+"tmp doesn't exist, creating it...\n")
	os.mkdir(root+"tmp",01777)
if not os.path.exists(root+"var/tmp"):
	writemsg(">>> "+root+"var/tmp doesn't exist, creating it...\n")
	try:
		os.mkdir(root+"var",0755)
	except (OSError,IOError):
		pass
	try:
		os.mkdir(root+"var/tmp",01777)
	except:
		writemsg("portage: couldn't create /var/tmp; exiting.\n")
		sys.exit(1)

os.umask(022)
profiledir=None
if os.path.exists("/etc/make.profile/make.defaults"):
	profiledir = "/etc/make.profile"
	if os.access("/etc/make.profile/deprecated", os.R_OK):
		deprecatedfile = open("/etc/make.profile/deprecated", "r")
		dcontent = deprecatedfile.readlines()
		deprecatedfile.close()
		newprofile = dcontent[0]
		writemsg(red("\n!!! Your current profile is deprecated and not supported anymore.\n"))
		writemsg(red("!!! Please upgrade to the following profile if possible:\n"))
		writemsg(8*" "+green(newprofile)+"\n")
		if len(dcontent) > 1:
			writemsg("To upgrade do the following steps:\n")
			for myline in dcontent[1:]:
				writemsg(myline)
			writemsg("\n\n")

db={}

# =============================================================================
# =============================================================================
# -----------------------------------------------------------------------------
# We're going to lock the global config to prevent changes, but we need
# to ensure the global settings are right.
settings=config(config_profile_path="/etc/make.profile",config_incrementals=incrementals)

# useful info
settings["PORTAGE_MASTER_PID"]=str(os.getpid())
settings.backup_changes("PORTAGE_MASTER_PID")
settings["BASH_ENV"]="/etc/portage/bashrc"
settings.backup_changes("BASH_ENV")

# gets virtual package settings
def getvirtuals(myroot):
	global settings
	writemsg("--- DEPRECATED call to getvirtual\n")
	return settings.getvirtuals(myroot)

def do_vartree(mysettings):
	global virts,virts_p
	virts=mysettings.getvirtuals("/")
	virts_p={}

	if virts:
		myvkeys=virts.keys()
		for x in myvkeys:
			vkeysplit=x.split("/")
			if not virts_p.has_key(vkeysplit[1]):
				virts_p[vkeysplit[1]]=virts[x]
	try:
		del x
	except:
		pass
	db["/"]={"virtuals":virts,"vartree":vartree("/",virts)}
	if root!="/":
		virts=mysettings.getvirtuals(root)
		db[root]={"virtuals":virts,"vartree":vartree(root,virts)}
	#We need to create the vartree first, then load our settings, and then set up our other trees

usedefaults=settings.use_defs
do_vartree(settings)
settings.reset() # XXX: Regenerate use after we get a vartree -- GLOBAL


# XXX: Might cause problems with root="/" assumptions
portdb=portdbapi(settings["PORTDIR"])

settings.lock()
# -----------------------------------------------------------------------------
# =============================================================================
# =============================================================================


if 'selinux' in settings["USE"].split(" "):
	try:
		import selinux
		selinux_enabled=1
	except OSError, e:
		writemsg(red("!!! SELinux not loaded: ")+str(e)+"\n")
		selinux_enabled=0
	except ImportError:
		writemsg(red("!!! SELinux module not found.")+" Please verify that it was installed.\n")
		selinux_enabled=0
else:
	selinux_enabled=0

cachedirs=["/var/cache/edb"]
if root!="/":
	cachedirs.append(root+"var/cache/edb")
if not os.environ.has_key("SANDBOX_ACTIVE"):
	for cachedir in cachedirs:
		if not os.path.exists(cachedir):
			os.makedirs(cachedir,0755)
			writemsg(">>> "+cachedir+" doesn't exist, creating it...\n")
		if not os.path.exists(cachedir+"/dep"):
			os.makedirs(cachedir+"/dep",2755)
			writemsg(">>> "+cachedir+"/dep doesn't exist, creating it...\n")
		try:
			os.chown(cachedir,uid,portage_gid)
			os.chmod(cachedir,0775)
		except OSError:
			pass
		try:
			mystat=os.lstat(cachedir+"/dep")
			os.chown(cachedir+"/dep",uid,portage_gid)
			os.chmod(cachedir+"/dep",02775)
			if mystat[ST_GID]!=portage_gid:
				spawn("chown -R "+str(uid)+":"+str(portage_gid)+" "+cachedir+"/dep",settings,free=1)
				spawn("chmod -R u+rw,g+rw "+cachedir+"/dep",settings,free=1)
		except OSError:
			pass
	
def flushmtimedb(record):
	if mtimedb:
		if record in mtimedb.keys():
			del mtimedb[record]
			#print "mtimedb["+record+"] is cleared."
		else:
			writemsg("Invalid or unset record '"+record+"' in mtimedb.\n")

#grab mtimes for eclasses and upgrades
mtimedb={}
mtimedbkeys=[
"updates", "info",
"version", "starttime",
"resume", "ldpath"
]
mtimedbfile=root+"var/cache/edb/mtimedb"
try:
	mypickle=cPickle.Unpickler(open(mtimedbfile))
	mypickle.find_global=None
	mtimedb=mypickle.load()
	if mtimedb.has_key("old"):
		mtimedb["updates"]=mtimedb["old"]
		del mtimedb["old"]
	if mtimedb.has_key("cur"):
		del mtimedb["cur"]
except:
	#print "!!!",e
	mtimedb={"updates":{},"version":"","starttime":0}

for x in mtimedb.keys():
	if x not in mtimedbkeys:
		writemsg("Deleting invalid mtimedb key: "+str(x)+"\n")
		del mtimedb[x]

#,"porttree":portagetree(root,virts),"bintree":binarytree(root,virts)}
features=settings["FEATURES"].split()

do_upgrade_packagesmessage=0
def do_upgrade(mykey):
	global do_upgrade_packagesmessage
	writemsg("\n\n")
	writemsg(green("Performing Global Updates: ")+bold(mykey)+"\n")
	writemsg("(Could take a couple minutes if you have a lot of binary packages.)\n")
	writemsg("  "+bold(".")+"='update pass'  "+bold("*")+"='binary update'  "+bold("@")+"='/var/db move'\n"+"  "+bold("s")+"='/var/db SLOT move' "+bold("S")+"='binary SLOT move'\n")
	processed=1
	#remove stale virtual entries (mappings for packages that no longer exist)
	myvirts=grabdict("/var/cache/edb/virtuals")
	
	worldlist=grabfile("/var/cache/edb/world")
	myupd=grabfile(mykey)
	db["/"]["bintree"]=binarytree("/",settings["PKGDIR"],virts)
	for myline in myupd:
		mysplit=myline.split()
		if not len(mysplit):
			continue
		if mysplit[0]!="move" and mysplit[0]!="slotmove":
			writemsg("portage: Update type \""+mysplit[0]+"\" not recognized.\n")
			processed=0
			continue
		if mysplit[0]=="move" and len(mysplit)!=3:
			writemsg("portage: Update command \""+myline+"\" invalid; skipping.\n")
			processed=0
			continue
		if mysplit[0]=="slotmove" and len(mysplit)!=4:
			writemsg("portage: Update command \""+myline+"\" invalid; skipping.\n")
			processed=0
			continue
		sys.stdout.write(".")
		sys.stdout.flush()

		if mysplit[0]=="move":
			db["/"]["vartree"].dbapi.move_ent(mysplit)
			db["/"]["bintree"].move_ent(mysplit)
			#update world entries:
			for x in range(0,len(worldlist)):
				#update world entries, if any.
				worldlist[x]=dep_transform(worldlist[x],mysplit[1],mysplit[2])
		
			#update virtuals:
			for myvirt in myvirts.keys():
				for mypos in range(0,len(myvirts[myvirt])):
					if myvirts[myvirt][mypos]==mysplit[1]:
						#update virtual to new name
						myvirts[myvirt][mypos]=mysplit[2]

		elif mysplit[0]=="slotmove":
			db["/"]["vartree"].dbapi.move_slot_ent(mysplit)
			db["/"]["bintree"].move_slot_ent(mysplit,settings["PORTAGE_TMPDIR"]+"/tbz2")

	# We gotta do the brute force updates for these now.
	if (settings["PORTAGE_CALLER"] in ["fixpackages"]) or \
	   ("fixpackages" in features):
		db["/"]["bintree"].update_ents(myupd,settings["PORTAGE_TMPDIR"]+"/tbz2")
	else:
		do_upgrade_packagesmessage = 1
	
	if processed:
		#update our internal mtime since we processed all our directives.
		mtimedb["updates"][mykey]=os.stat(mykey)[ST_MTIME]
	myworld=open("/var/cache/edb/world","w")
	for x in worldlist:
		myworld.write(x+"\n")
	myworld.close()
	writedict(myvirts,"/var/cache/edb/virtuals")
	print ""

def portageexit():
	global uid,portage_gid,portdb
	if secpass and not os.environ.has_key("SANDBOX_ACTIVE"):
		# wait child process death
		try:
			while True:
				os.wait()
		except OSError:
			#writemsg(">>> All child process are now dead.")
			pass
		if mtimedb:
		# Store mtimedb
			mymfn=mtimedbfile
			try:
				mtimedb["version"]=VERSION
				cPickle.dump(mtimedb,open(mymfn,"w"))
				#print "*** Wrote out mtimedb data successfully."
				os.chown(mymfn,uid,portage_gid)
				os.chmod(mymfn,0664)
			except Exception, e:
				pass

atexit.register(portageexit)

if (secpass==2) and (not os.environ.has_key("SANDBOX_ACTIVE")):
	if settings["PORTAGE_CALLER"] in ["emerge","fixpackages"]:
		#only do this if we're root and not running repoman/ebuild digest
		updpath=os.path.normpath(settings["PORTDIR"]+"///profiles/updates")
		didupdate=0
		if not mtimedb.has_key("updates"):
			mtimedb["updates"]={}
		try:
			mylist=listdir(updpath,EmptyOnError=1)
			# resort the list
			mylist=[myfile[3:]+"-"+myfile[:2] for myfile in mylist]
			mylist.sort()
			mylist=[myfile[5:]+"-"+myfile[:4] for myfile in mylist]
			for myfile in mylist:
				mykey=updpath+"/"+myfile
				if not os.path.isfile(mykey):
					continue
				if (not mtimedb["updates"].has_key(mykey)) or \
					 (mtimedb["updates"][mykey] != os.stat(mykey)[ST_MTIME]) or \
					 (settings["PORTAGE_CALLER"] == "fixpackages"):
					didupdate=1
					do_upgrade(mykey)
					portageexit() # This lets us save state for C-c.
		except OSError:
			#directory doesn't exist
			pass
		if didupdate:
			#make sure our internal databases are consistent; recreate our virts and vartree
			do_vartree(settings)
			if do_upgrade_packagesmessage and \
				 listdir(settings["PKGDIR"]+"/All/",EmptyOnError=1):
				writemsg("\n\n\n ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the")
				writemsg("\n    tbz2's in the packages directory. "+bold("Note: This can take a very long time."))
				writemsg("\n")
		




#continue setting up other trees
db["/"]["porttree"]=portagetree("/",virts)
db["/"]["bintree"]=binarytree("/",settings["PKGDIR"],virts)
if root!="/":
	db[root]["porttree"]=portagetree(root,virts)
	db[root]["bintree"]=binarytree(root,settings["PKGDIR"],virts)
thirdpartymirrors=grabdict(settings["PORTDIR"]+"/profiles/thirdpartymirrors")

if not os.path.exists(settings["PORTAGE_TMPDIR"]):
	writemsg("portage: the directory specified in your PORTAGE_TMPDIR variable, \""+settings["PORTAGE_TMPDIR"]+",\"\n")
	writemsg("does not exist.  Please create this directory or correct your PORTAGE_TMPDIR setting.\n")
	sys.exit(1)
if not os.path.isdir(settings["PORTAGE_TMPDIR"]):
	writemsg("portage: the directory specified in your PORTAGE_TMPDIR variable, \""+settings["PORTAGE_TMPDIR"]+",\"\n")
	writemsg("is not a directory.  Please correct your PORTAGE_TMPDIR setting.\n")
	sys.exit(1)

# COMPATABILITY -- This shouldn't be used.
pkglines = settings.packages

groups=settings["ACCEPT_KEYWORDS"].split()
archlist=[]
for myarch in grabfile(settings["PORTDIR"]+"/profiles/arch.list"):
	archlist += [myarch,"~"+myarch]
for group in groups:
	if not archlist:
		writemsg("--- 'profiles/arch.list' is empty or not available. Empty portage tree?\n")
		break
	elif (group not in archlist) and group[0]!='-':
		writemsg("\n"+red("!!! INVALID ACCEPT_KEYWORDS: ")+str(group)+"\n")

# Clear the cache
dircache={}

if not os.path.islink("/etc/make.profile") and os.path.exists(settings["PORTDIR"]+"/profiles"):
	writemsg(red("\a\n\n!!! /etc/make.profile is not a symlink and will probably prevent most merges.\n"))
	writemsg(red("!!! It should point into a profile within %s/profiles/\n" % settings["PORTDIR"]))
	writemsg(red("!!! (You can safely ignore this message when syncing. It's harmless.)\n\n\n"))
	time.sleep(3)

# Defaults set at the top of perform_checksum.
if spawn("/usr/sbin/prelink --version > /dev/null 2>&1",settings,free=1) == 0:
	prelink_capable=1

# ============================================================================
# ============================================================================

def pickle_write(data,filename,debug=0):
	import cPickle
	try:
		myf=open(filename,"w")
		cPickle.dump(data,myf)
		myf.flush()
		myf.close()
		writemsg("Wrote pickle: "+str(filename)+"\n",1)
		os.chown(myefn,uid,portage_gid)
		os.chmod(myefn,0664)
	except Exception, e:
		return 0
	return 1

def pickle_read(filename,default=None,debug=0):
	import cPickle,os
	if not os.access(filename, os.R_OK):
		writemsg("pickle_read(): File not readable. '"+filename+"'\n",1)
		return default
	data = None
	try:
		myf = open(filename)
		mypickle = cPickle.Unpickler(myf)
		mypickle.find_global = None
		data = mypickle.load()
		myf.close()
		del mypickle,myf
		writemsg("pickle_read(): Loaded pickle. '"+filename+"'\n",1)
	except Exception, e:
		writemsg("!!! Failed to load pickle: "+str(e)+"\n",1)
		data = default
	return data

