# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

import sys,string,shlex,os.path,stat,types
import shutil

noiselimit = 0
def writemsg(mystr,noiselevel=0):
	"""Prints out warning and debug messages based on the noiselimit setting"""
	global noiselimit
	if noiselevel <= noiselimit:
		sys.stderr.write(mystr)
		sys.stderr.flush()

def normalize_path(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			newpath = newpath[1:]
	return newpath


def grabfile(myfilename, compat_level=0):
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
			# Check if we have a compat-level string. BC-integration data.
			# '##COMPAT==>N<==' 'some string attached to it'
			mylinetest = string.split(myline, "<==", 1)
			if len(mylinetest) == 2:
				myline_potential = mylinetest[1]
				mylinetest = string.split(mylinetest[0],"##COMPAT==>")
				if len(mylinetest) == 2:
					if compat_level >= int(mylinetest[1]):
						# It's a compat line, and the key matches.
						newlines.append(myline_potential)
				continue
			else:
				continue
		newlines.append(myline)
	return newlines

def map_dictlist_vals(func,myDict):
	"""Performs a function on each value of each key in a dictlist.
	Returns a new dictlist."""
	new_dl = {}
	for key in myDict.keys():
		new_dl[key] = []
		new_dl[key] = map(func,myDict[key])
	return new_dl

def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced."""
	final_dict = None
	kill_list = {}
	for mydict in original_dicts:
		if mydict == None:
			continue
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if not final_dict.has_key(y):
				final_dict[y] = []
			if not kill_list.has_key(y):
				kill_list[y] = []
			
			for thing in mydict[y]:
				if thing and (thing not in kill_list[y]):
					if (incremental or (y in incrementals)) and thing[0] == '-':
						if thing[1:] not in kill_list[y]:
							kill_list[y] += [thing[1:]]
#						while(thing[1:] in final_dict[y]):
#							del final_dict[y][final_dict[y].index(thing[1:])]
					else:
						if thing not in final_dict[y]:
							final_dict[y].insert(0,thing[:])
			if final_dict.has_key(y) and not final_dict[y]:
				del final_dict[y]
	return final_dict

def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = None
	for mydict in dicts:
		if mydict == None:
			if ignore_none:
				continue
			else:
				return None
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if mydict[y]:
				if final_dict.has_key(y) and (incremental or (y in incrementals)):
					final_dict[y] += " "+mydict[y][:]
				else:
					final_dict[y]  = mydict[y][:]
			mydict[y] = string.join(mydict[y].split()) # Remove extra spaces.
	return final_dict

def stack_lists(lists, incremental=1):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced."""
	new_list = []
	for x in lists:
		for y in x:
			if y:
				if incremental and y[0]=='-':
					while y[1:] in new_list:
						del new_list[new_list.index(y[1:])]
				else:
					if y not in new_list:
						new_list.append(y[:])
	return new_list

def grab_multiple(basename, locations, handler, all_must_exist=0):
	mylist = []
	for x in locations:
		mylist.append(handler(x+"/"+basename))
	return mylist

def grabdict(myfilename,juststrings=0,empty=0):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a dictionary"""
	newdict={}
	try:
		myfile=open(myfilename,"r")
	except IOError,e:
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

def grabfile_package(myfilename,compatlevel=0):
	pkgs=grabfile(myfilename,compatlevel)
	for x in range(len(pkgs)-1,-1,-1):
		pkg = pkgs[x]
		if pkg[0] == "*": # Kill this so we can deal the "packages" file too
			pkg = pkg[1:]
		if not isvalidatom(pkg):
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, pkgs[x]))
			del(pkgs[x])
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
	try:
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
					raise portage_exception.CorruptionError("ParseError: Unexpected EOF: "+str(mycfg)+": line "+str(lex.lineno))
				else:
					return mykeys
			mykeys[key]=varexpand(val,mykeys)
	except SystemExit, e:
		raise
	except Exception, e:
		raise e.__class__, str(e)+" in "+mycfg
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
					elif a!='\n':
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

def pickle_write(data,filename,debug=0):
	import cPickle,os
	try:
		myf=open(filename,"w")
		cPickle.dump(data,myf,cPickle.HIGHEST_PROTOCOL)
		myf.flush()
		myf.close()
		writemsg("Wrote pickle: "+str(filename)+"\n",1)
		os.chown(myefn,uid,portage_gid)
		os.chmod(myefn,0664)
	except SystemExit, e:
		raise
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
	except SystemExit, e:
		raise
	except Exception, e:
		writemsg("!!! Failed to load pickle: "+str(e)+"\n",1)
		data = default
	return data

class ReadOnlyConfig:
	def __init__(self,filename,strict_keys=0):
		self.__filename = filename[:]
		self.__strict_keys = strict_keys
		self.__mydict = {}
		self.__dict_was_loaded = False
		if os.path.isfile(self.__filename):
			self.__mydict = getconfig(self.__filename)
			self.__dict_was_loaded = True

	def isLoaded():
		return self.__dict_was_loaded

	def __getitem__(self,key):
		if self.__mydict.has_key(key):
			return self.__mydict[key][:]
		if self.__strict_keys:
			raise KeyError("%s not found in config: '%s'" % (key,self.__filename))
		return ""

	def __setitem__(self,key,value):
		raise KeyError("This class is not modifiable.")

	def keys(self):
		return self.__mydict.keys()

	def has_key(self,key):
		return self.__mydict.has_key(key)

def unique_array(array):
	"""Takes an array and makes sure each element is unique."""
	mya = []
	for x in array:
		if x not in mya:
			mya.append(x)
	return mya

def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	global lchown
	from portage_exec import selinux_enabled
	if selinux_enabled:
		import selinux
	from portage_data import lchown
	try:
		if not sstat:
			sstat=os.lstat(src)
	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except SystemExit, e:
		raise
	except:
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if destexists:
		if stat.S_ISLNK(dstat[stat.ST_MODE]):
			try:
				os.unlink(dest)
				destexists=0
			except SystemExit, e:
				raise
			except Exception, e:
				pass

	if stat.S_ISLNK(sstat[stat.ST_MODE]):
		try:
			target=os.readlink(src)
			if mysettings and mysettings["D"]:
				if target.find(mysettings["D"])==0:
					target=target[len(mysettings["D"]):]
			if destexists and not stat.S_ISDIR(dstat[stat.ST_MODE]):
				os.unlink(dest)
			if selinux_enabled:
				sid = selinux.get_lsid(src)
				selinux.secure_symlink(target,dest,sid)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			return os.lstat(dest)[stat.ST_MTIME]
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			return os.lstat(dest)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! failed to properly create symlink:"
			print "!!!",dest,"->",target
			print "!!!",e
			return None

	renamefailed=1
	if sstat[stat.ST_DEV]==dstat[stat.ST_DEV] or selinux_enabled:
		try:
			if selinux_enabled:
				ret=selinux.secure_rename(src,dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except SystemExit, e:
			raise
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
		if stat.S_ISREG(sstat[stat.ST_MODE]):
			try: # For safety copy then move it over.
				if selinux_enabled:
					selinux.secure_copy(src,dest+"#new")
					selinux.secure_rename(dest+"#new",dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except SystemExit, e:
				raise
			except Exception, e:
				print '!!! copy',src,'->',dest,'failed.'
				print "!!!",e
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			if selinux_enabled:
				a=portage_exec.spawn_get_output(MOVE_BINARY+" -c -f '%s' '%s'" % (src,dest))
			else:
				a=portage_exec.spawn_get_output(MOVE_BINARY+" -f '%s' '%s'" % (src,dest))
				if a[0]!=0:
					print "!!! Failed to move special file:"
					print "!!! '"+src+"' to '"+dest+"'"
					print "!!!",a
					return None # failure
		try:
			if didcopy:
				lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				os.chmod(dest, stat.S_IMODE(sstat[stat.ST_MODE])) # Sticky is reset on chown
				os.unlink(src)
		except SystemExit, e:
				os.unlink(src)
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! Failed to chown/chmod/unlink in movefile()"
			print "!!!",dest
			print "!!!",e
			return None

	if newmtime:
		os.utime(dest,(newmtime,newmtime))
	else:
		os.utime(dest, (sstat[stat.ST_ATIME], sstat[stat.ST_MTIME]))
		newmtime=sstat[stat.ST_MTIME]
	return newmtime

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


