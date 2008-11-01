# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


import os
import errno
import logging
import shlex
import stat
import string
import sys

from portage.exception import PortageException, FileNotFound, \
       OperationNotPermitted, PermissionDenied, ReadOnlyFileSystem
import portage.exception
from portage.dep import isvalidatom

try:
	import cPickle as pickle
except ImportError:
	import pickle

try:
	import cStringIO as StringIO
except ImportError:
	import StringIO

noiselimit = 0

def initialize_logger(level=logging.WARN):
	"""Sets up basic logging of portage activities
	Args:
		level: the level to emit messages at ('info', 'debug', 'warning' ...)
	Returns:
		None
	"""
	logging.basicConfig(level=logging.WARN, format='[%(levelname)-4s] %(message)s')

def writemsg(mystr,noiselevel=0,fd=None):
	"""Prints out warning and debug messages based on the noiselimit setting"""
	global noiselimit
	if fd is None:
		fd = sys.stderr
	if noiselevel <= noiselimit:
		fd.write(mystr)
		fd.flush()

def writemsg_stdout(mystr,noiselevel=0):
	"""Prints messages stdout based on the noiselimit setting"""
	writemsg(mystr, noiselevel=noiselevel, fd=sys.stdout)

def writemsg_level(msg, level=0, noiselevel=0):
	"""
	Show a message for the given level as defined by the logging module
	(default is 0). When level >= logging.WARNING then the message is
	sent to stderr, otherwise it is sent to stdout. The noiselevel is
	passed directly to writemsg().

	@type msg: str
	@param msg: a message string, including newline if appropriate
	@type level: int
	@param level: a numeric logging level (see the logging module)
	@type noiselevel: int
	@param noiselevel: passed directly to writemsg
	"""
	if level >= logging.WARNING:
		fd = sys.stderr
	else:
		fd = sys.stdout
	writemsg(msg, noiselevel=noiselevel, fd=fd)

def normalize_path(mypath):
	""" 
	os.path.normpath("//foo") returns "//foo" instead of "/foo"
	We dislike this behavior so we create our own normpath func
	to fix it.
	"""
	if mypath.startswith(os.path.sep):
		# posixpath.normpath collapses 3 or more leading slashes to just 1.
		return os.path.normpath(2*os.path.sep + mypath)
	else:
		return os.path.normpath(mypath)

def grabfile(myfilename, compat_level=0, recursive=0):
	"""This function grabs the lines in a file, normalizes whitespace and returns lines in a list; if a line
	begins with a #, it is ignored, as are empty lines"""

	mylines=grablines(myfilename, recursive)
	newlines=[]
	for x in mylines:
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		myline=" ".join(x.split())
		if not len(myline):
			continue
		if myline[0]=="#":
			# Check if we have a compat-level string. BC-integration data.
			# '##COMPAT==>N<==' 'some string attached to it'
			mylinetest = myline.split("<==",1)
			if len(mylinetest) == 2:
				myline_potential = mylinetest[1]
				mylinetest = mylinetest[0].split("##COMPAT==>")
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
	for key in myDict:
		new_dl[key] = []
		new_dl[key] = map(func,myDict[key])
	return new_dl

def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""
	Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced.
	
	Example usage:
	   >>> from portage.util import stack_dictlist
		>>> print stack_dictlist( [{'a':'b'},{'x':'y'}])
		>>> {'a':'b','x':'y'}
		>>> print stack_dictlist( [{'a':'b'},{'a':'c'}], incremental = True )
		>>> {'a':['b','c'] }
		>>> a = {'KEYWORDS':['x86','alpha']}
		>>> b = {'KEYWORDS':['-x86']}
		>>> print stack_dictlist( [a,b] )
		>>> { 'KEYWORDS':['x86','alpha','-x86']}
		>>> print stack_dictlist( [a,b], incremental=True)
		>>> { 'KEYWORDS':['alpha'] }
		>>> print stack_dictlist( [a,b], incrementals=['KEYWORDS'])
		>>> { 'KEYWORDS':['alpha'] }
	
	@param original_dicts a list of (dictionary objects or None)
	@type list
	@param incremental True or false depending on whether new keys should overwrite
	   keys which already exist.
	@type boolean
	@param incrementals A list of items that should be incremental (-foo removes foo from
	   the returned dict).
	@type list
	@param ignore_none Appears to be ignored, but probably was used long long ago.
	@type boolean
	
	"""
	final_dict = {}
	for mydict in original_dicts:
		if mydict is None:
			continue
		for y in mydict:
			if not y in final_dict:
				final_dict[y] = []
			
			for thing in mydict[y]:
				if thing:
					if incremental or y in incrementals:
						if thing == "-*":
							final_dict[y] = []
							continue
						elif thing.startswith("-"):
							try:
								final_dict[y].remove(thing[1:])
							except ValueError:
								pass
							continue
					if thing not in final_dict[y]:
						final_dict[y].append(thing)
			if y in final_dict and not final_dict[y]:
				del final_dict[y]
	return final_dict

def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = None
	for mydict in dicts:
		if mydict is None:
			if ignore_none:
				continue
			else:
				return None
		if final_dict is None:
			final_dict = {}
		for y in mydict.keys():
			if True:
				if y in final_dict and (incremental or (y in incrementals)):
					final_dict[y] += " "+mydict[y][:]
				else:
					final_dict[y]  = mydict[y][:]
			mydict[y] = " ".join(mydict[y].split()) # Remove extra spaces.
	return final_dict

def stack_lists(lists, incremental=1):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced.

	all elements must be hashable."""

	new_list = {}
	for x in lists:
		for y in filter(None, x):
			if incremental:
				if y == "-*":
					new_list.clear()
				elif y.startswith("-"):
					new_list.pop(y[1:], None)
				else:
					new_list[y] = True
			else:
				new_list[y] = True
	return new_list.keys()

def grabdict(myfilename, juststrings=0, empty=0, recursive=0, incremental=1):
	"""
	This function grabs the lines in a file, normalizes whitespace and returns lines in a dictionary
	
	@param myfilename: file to process
	@type myfilename: string (path)
	@param juststrings: only return strings
	@type juststrings: Boolean (integer)
	@param empty: Ignore certain lines
	@type empty: Boolean (integer)
	@param recursive: Recursively grab ( support for /etc/portage/package.keywords/* and friends )
	@type recursive: Boolean (integer)
	@param incremental: Append to the return list, don't overwrite
	@type incremental: Boolean (integer)
	@rtype: Dictionary
	@returns:
	1.  Returns the lines in a file in a dictionary, for example:
		'sys-apps/portage x86 amd64 ppc'
		would return
		{ "sys-apps/portage" : [ 'x86', 'amd64', 'ppc' ]
		the line syntax is key : [list of values]
	"""
	newdict={}
	for x in grablines(myfilename, recursive):
		#the split/join thing removes leading and trailing whitespace, and converts any whitespace in the line
		#into single spaces.
		if x[0] == "#":
			continue
		myline=x.split()
		if len(myline) < 2 and empty == 0:
			continue
		if len(myline) < 1 and empty == 1:
			continue
		if incremental:
			newdict.setdefault(myline[0], []).extend(myline[1:])
		else:
			newdict[myline[0]] = myline[1:]
	if juststrings:
		for k, v in newdict.iteritems():
			newdict[k] = " ".join(v)
	return newdict

def grabdict_package(myfilename, juststrings=0, recursive=0):
	""" Does the same thing as grabdict except it validates keys
	    with isvalidatom()"""
	pkgs=grabdict(myfilename, juststrings, empty=1, recursive=recursive)
	# We need to call keys() here in order to avoid the possibility of
	# "RuntimeError: dictionary changed size during iteration"
	# when an invalid atom is deleted.
	for x in pkgs.keys():
		if not isvalidatom(x):
			del(pkgs[x])
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, x),
				noiselevel=-1)
	return pkgs

def grabfile_package(myfilename, compatlevel=0, recursive=0):
	pkgs=grabfile(myfilename, compatlevel, recursive=recursive)
	for x in range(len(pkgs)-1, -1, -1):
		pkg = pkgs[x]
		if pkg[0] in '-*': # -atom *pkg for packages file
			pkg = pkg[1:]
		if not isvalidatom(pkg):
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, pkgs[x]),
				noiselevel=-1)
			del(pkgs[x])
	return pkgs

def grablines(myfilename,recursive=0):
	mylines=[]
	if recursive and os.path.isdir(myfilename):
		if myfilename in ["RCS", "CVS", "SCCS"]:
			return mylines
		dirlist = os.listdir(myfilename)
		dirlist.sort()
		for f in dirlist:
			if not f.startswith(".") and not f.endswith("~"):
				mylines.extend(grablines(
					os.path.join(myfilename, f), recursive))
	else:
		try:
			myfile = open(myfilename, "r")
			mylines = myfile.readlines()
			myfile.close()
		except IOError, e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(myfilename)
			pass
	return mylines

def writedict(mydict,myfilename,writekey=True):
	"""Writes out a dict to a file; writekey=0 mode doesn't write out
	the key and assumes all values are strings, not lists."""
	myfile = None
	try:
		myfile = atomic_ofstream(myfilename)
		if not writekey:
			for x in mydict.values():
				myfile.write(x+"\n")
		else:
			for x in mydict:
				myfile.write("%s %s\n" % (x, " ".join(mydict[x])))
		myfile.close()
	except IOError:
		if myfile is not None:
			myfile.abort()
		return 0
	return 1

class _tolerant_shlex(shlex.shlex):
	def sourcehook(self, newfile):
		try:
			return shlex.shlex.sourcehook(self, newfile)
		except EnvironmentError, e:
			writemsg("!!! Parse error in '%s': source command failed: %s\n" % \
				(self.infile, str(e)), noiselevel=-1)
			return (newfile, StringIO.StringIO())

class _insert_newline_eof(file):
	"""
	Read functions insert anywhere from 0 and 2 newlines just before eof.
	This is useful as a workaround for avoiding a silent error in shlex that
	is triggered by a source statement at the end of the file without a
	trailing newline after the source statement.
	"""

	def read(self, *args):
		if hasattr(self, "_got_eof"):
			return ""
		rval = file.read(self, *args)
		if rval and not args and rval[-1:] != "\n":
			rval += "\n"
		if not rval:
			self._got_eof = True
			return "\n"
		return rval

	def readline(self, *args):
		if hasattr(self, "_got_eof"):
			return ""
		rval = file.readline(self, *args)
		if rval and rval[-1:] != "\n":
			rval += "\n"
		if not rval:
			self._got_eof = True
			rval = "\n"
		return rval

	def readlines(self, *args):
		if hasattr(self, "_got_eof"):
			return []
		lines = file.readlines(self, *args)
		if lines and lines[-1][-1:] != "\n":
			lines[-1] += "\n"
		return lines

def getconfig(mycfg, tolerant=0, allow_sourcing=False, expand=True):
	if isinstance(expand, dict):
		# Some existing variable definitions have been
		# passed in, for use in substitutions.
		expand_map = expand
		expand = True
	else:
		expand_map = {}
	mykeys = {}
	try:
		f = _insert_newline_eof(mycfg, 'rb')
	except IOError, e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied(mycfg)
		if e.errno != errno.ENOENT:
			writemsg("open('%s', 'r'): %s\n" % (mycfg, e), noiselevel=-1)
			raise
		return None
	try:
		if tolerant:
			shlex_class = _tolerant_shlex
		else:
			shlex_class = shlex.shlex
		# The default shlex.sourcehook() implementation
		# only joins relative paths when the infile
		# attribute is properly set.
		lex = shlex_class(f, infile=mycfg, posix=True)
		lex.wordchars=string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"     
		lex.quotes="\"'"
		if allow_sourcing:
			lex.source="source"
		while 1:
			key=lex.get_token()
			if key == "export":
				key = lex.get_token()
			if key is None:
				#normal end of file
				break;
			equ=lex.get_token()
			if (equ==''):
				#unexpected end of file
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n",
						noiselevel=-1)
					raise Exception("ParseError: Unexpected EOF: "+str(mycfg)+": on/before line "+str(lex.lineno))
				else:
					return mykeys
			elif (equ!='='):
				#invalid token
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					raise Exception("ParseError: Invalid token " + \
						"'%s' (not '='): %s: line %s" % \
						(equ, mycfg, lex.lineno))
				else:
					return mykeys
			val=lex.get_token()
			if val is None:
				#unexpected end of file
				#lex.error_leader(self.filename,lex.lineno)
				if not tolerant:
					writemsg("!!! Unexpected end of config file: variable "+str(key)+"\n",
						noiselevel=-1)
					raise portage.exception.CorruptionError("ParseError: Unexpected EOF: "+str(mycfg)+": line "+str(lex.lineno))
				else:
					return mykeys
			if expand:
				mykeys[key] = varexpand(val, expand_map)
				expand_map[key] = mykeys[key]
			else:
				mykeys[key] = val
	except SystemExit, e:
		raise
	except Exception, e:
		raise portage.exception.ParseError(str(e)+" in "+mycfg)
	return mykeys
	
#cache expansions of constant strings
cexpand={}
def varexpand(mystring, mydict={}):
	newstring = cexpand.get(" "+mystring, None)
	if newstring is not None:
		return newstring

	"""
	new variable expansion code.  Preserves quotes, handles \n, etc.
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
				newstring += "'" # Quote removal is handled by shlex.
				insing=not insing
			pos=pos+1
			continue
		elif (mystring[pos]=='"') and (mystring[pos-1]!="\\"):
			if (insing):
				newstring=newstring+'"'
			else:
				newstring += '"' # Quote removal is handled by shlex.
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
				if myvarname in mydict:
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

# broken and removed, but can still be imported
pickle_write = None

def pickle_read(filename,default=None,debug=0):
	import os
	if not os.access(filename, os.R_OK):
		writemsg("pickle_read(): File not readable. '"+filename+"'\n",1)
		return default
	data = None
	try:
		myf = open(filename)
		mypickle = pickle.Unpickler(myf)
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

def dump_traceback(msg, noiselevel=1):
	import sys, traceback
	info = sys.exc_info()
	if not info[2]:
		stack = traceback.extract_stack()[:-1]
		error = None
	else:
		stack = traceback.extract_tb(info[2])
		error = str(info[1])
	writemsg("\n====================================\n", noiselevel=noiselevel)
	writemsg("%s\n\n" % msg, noiselevel=noiselevel)
	for line in traceback.format_list(stack):
		writemsg(line, noiselevel=noiselevel)
	if error:
		writemsg(error+"\n", noiselevel=noiselevel)
	writemsg("====================================\n\n", noiselevel=noiselevel)

def unique_array(s):
	"""lifted from python cookbook, credit: Tim Peters
	Return a list of the elements in s in arbitrary order, sans duplicates"""
	n = len(s)
	# assume all elements are hashable, if so, it's linear
	try:
		return list(set(s))
	except TypeError:
		pass

	# so much for linear.  abuse sort.
	try:
		t = list(s)
		t.sort()
	except TypeError:
		pass
	else:
		assert n > 0
		last = t[0]
		lasti = i = 1
		while i < n:
			if t[i] != last:
				t[lasti] = last = t[i]
				lasti += 1
			i += 1
		return t[:lasti]

	# blah.	 back to original portage.unique_array
	u = []
	for x in s:
		if x not in u:
			u.append(x)
	return u

def apply_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None, follow_links=True):
	"""Apply user, group, and mode bits to a file if the existing bits do not
	already match.  The default behavior is to force an exact match of mode
	bits.  When mask=0 is specified, mode bits on the target file are allowed
	to be a superset of the mode argument (via logical OR).  When mask>0, the
	mode bits that the target file is allowed to have are restricted via
	logical XOR.
	Returns True if the permissions were modified and False otherwise."""

	modified = False

	if stat_cached is None:
		try:
			if follow_links:
				stat_cached = os.stat(filename)
			else:
				stat_cached = os.lstat(filename)
		except OSError, oe:
			func_call = "stat('%s')" % filename
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	if	(uid != -1 and uid != stat_cached.st_uid) or \
		(gid != -1 and gid != stat_cached.st_gid):
		try:
			if follow_links:
				os.chown(filename, uid, gid)
			else:
				import portage.data
				portage.data.lchown(filename, uid, gid)
			modified = True
		except OSError, oe:
			func_call = "chown('%s', %i, %i)" % (filename, uid, gid)
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.EROFS:
				raise ReadOnlyFileSystem(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	new_mode = -1
	st_mode = stat_cached.st_mode & 07777 # protect from unwanted bits
	if mask >= 0:
		if mode == -1:
			mode = 0 # Don't add any mode bits when mode is unspecified.
		else:
			mode = mode & 07777
		if	(mode & st_mode != mode) or \
			((mask ^ st_mode) & st_mode != st_mode):
			new_mode = mode | st_mode
			new_mode = (mask ^ new_mode) & new_mode
	elif mode != -1:
		mode = mode & 07777 # protect from unwanted bits
		if mode != st_mode:
			new_mode = mode

	# The chown system call may clear S_ISUID and S_ISGID
	# bits, so those bits are restored if necessary.
	if modified and new_mode == -1 and \
		(st_mode & stat.S_ISUID or st_mode & stat.S_ISGID):
		if mode == -1:
			new_mode = st_mode
		else:
			mode = mode & 07777
			if mask >= 0:
				new_mode = mode | st_mode
				new_mode = (mask ^ new_mode) & new_mode
			else:
				new_mode = mode
			if not (new_mode & stat.S_ISUID or new_mode & stat.S_ISGID):
				new_mode = -1

	if not follow_links and stat.S_ISLNK(stat_cached.st_mode):
		# Mode doesn't matter for symlinks.
		new_mode = -1

	if new_mode != -1:
		try:
			os.chmod(filename, new_mode)
			modified = True
		except OSError, oe:
			func_call = "chmod('%s', %s)" % (filename, oct(new_mode))
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.EROFS:
				raise ReadOnlyFileSystem(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			raise
	return modified

def apply_stat_permissions(filename, newstat, **kwargs):
	"""A wrapper around apply_secpass_permissions that gets
	uid, gid, and mode from a stat object"""
	return apply_secpass_permissions(filename, uid=newstat.st_uid, gid=newstat.st_gid,
	mode=newstat.st_mode, **kwargs)

def apply_recursive_permissions(top, uid=-1, gid=-1,
	dirmode=-1, dirmask=-1, filemode=-1, filemask=-1, onerror=None):
	"""A wrapper around apply_secpass_permissions that applies permissions
	recursively.  If optional argument onerror is specified, it should be a
	function; it will be called with one argument, a PortageException instance.
	Returns True if all permissions are applied and False if some are left
	unapplied."""

	if onerror is None:
		# Default behavior is to dump errors to stderr so they won't
		# go unnoticed.  Callers can pass in a quiet instance.
		def onerror(e):
			if isinstance(e, OperationNotPermitted):
				writemsg("Operation Not Permitted: %s\n" % str(e),
					noiselevel=-1)
			elif isinstance(e, FileNotFound):
				writemsg("File Not Found: '%s'\n" % str(e), noiselevel=-1)
			else:
				raise

	all_applied = True
	for dirpath, dirnames, filenames in os.walk(top):
		try:
			applied = apply_secpass_permissions(dirpath,
				uid=uid, gid=gid, mode=dirmode, mask=dirmask)
			if not applied:
				all_applied = False
		except PortageException, e:
			all_applied = False
			onerror(e)

		for name in filenames:
			try:
				applied = apply_secpass_permissions(os.path.join(dirpath, name),
					uid=uid, gid=gid, mode=filemode, mask=filemask)
				if not applied:
					all_applied = False
			except PortageException, e:
				# Ignore InvalidLocation exceptions such as FileNotFound
				# and DirectoryNotFound since sometimes things disappear,
				# like when adjusting permissions on DISTCC_DIR.
				if not isinstance(e, portage.exception.InvalidLocation):
					all_applied = False
					onerror(e)
	return all_applied

def apply_secpass_permissions(filename, uid=-1, gid=-1, mode=-1, mask=-1,
	stat_cached=None, follow_links=True):
	"""A wrapper around apply_permissions that uses secpass and simple
	logic to apply as much of the permissions as possible without
	generating an obviously avoidable permission exception. Despite
	attempts to avoid an exception, it's possible that one will be raised
	anyway, so be prepared.
	Returns True if all permissions are applied and False if some are left
	unapplied."""

	if stat_cached is None:
		try:
			if follow_links:
				stat_cached = os.stat(filename)
			else:
				stat_cached = os.lstat(filename)
		except OSError, oe:
			func_call = "stat('%s')" % filename
			if oe.errno == errno.EPERM:
				raise OperationNotPermitted(func_call)
			elif oe.errno == errno.EACCES:
				raise PermissionDenied(func_call)
			elif oe.errno == errno.ENOENT:
				raise FileNotFound(filename)
			else:
				raise

	all_applied = True

	import portage.data # not imported globally because of circular dep
	if portage.data.secpass < 2:

		if uid != -1 and \
		uid != stat_cached.st_uid:
			all_applied = False
			uid = -1

		if gid != -1 and \
		gid != stat_cached.st_gid and \
		gid not in os.getgroups():
			all_applied = False
			gid = -1

	apply_permissions(filename, uid=uid, gid=gid, mode=mode, mask=mask,
		stat_cached=stat_cached, follow_links=follow_links)
	return all_applied

class atomic_ofstream(file):
	"""Write a file atomically via os.rename().  Atomic replacement prevents
	interprocess interference and prevents corruption of the target
	file when the write is interrupted (for example, when an 'out of space'
	error occurs)."""

	def __init__(self, filename, mode='w', follow_links=True, **kargs):
		"""Opens a temporary filename.pid in the same directory as filename."""
		self._aborted = False

		if follow_links:
			canonical_path = os.path.realpath(filename)
			self._real_name = canonical_path
			tmp_name = "%s.%i" % (canonical_path, os.getpid())
			try:
				super(atomic_ofstream, self).__init__(tmp_name, mode=mode, **kargs)
				return
			except (OSError, IOError), e:
				if canonical_path == filename:
					raise
				writemsg("!!! Failed to open file: '%s'\n" % tmp_name,
					noiselevel=-1)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)

		self._real_name = filename
		tmp_name = "%s.%i" % (filename, os.getpid())
		super(atomic_ofstream, self).__init__(tmp_name, mode=mode, **kargs)

	def close(self):
		"""Closes the temporary file, copies permissions (if possible),
		and performs the atomic replacement via os.rename().  If the abort()
		method has been called, then the temp file is closed and removed."""
		if not self.closed:
			try:
				super(atomic_ofstream, self).close()
				if not self._aborted:
					try:
						apply_stat_permissions(self.name, os.stat(self._real_name))
					except OperationNotPermitted:
						pass
					except FileNotFound:
						pass
					except OSError, oe: # from the above os.stat call
						if oe.errno in (errno.ENOENT, errno.EPERM):
							pass
						else:
							raise
					os.rename(self.name, self._real_name)
			finally:
				# Make sure we cleanup the temp file
				# even if an exception is raised.
				try:
					os.unlink(self.name)
				except OSError, oe:
					pass

	def abort(self):
		"""If an error occurs while writing the file, the user should
		call this method in order to leave the target file unchanged.
		This will call close() automatically."""
		if not self._aborted:
			self._aborted = True
			self.close()

	def __del__(self):
		"""If the user does not explicitely call close(), it is
		assumed that an error has occurred, so we abort()."""
		if not self.closed:
			self.abort()
		# ensure destructor from the base class is called
		base_destructor = getattr(super(atomic_ofstream, self), '__del__', None)
		if base_destructor is not None:
			base_destructor()

def write_atomic(file_path, content):
	f = None
	try:
		f = atomic_ofstream(file_path)
		f.write(content)
		f.close()
	except (IOError, OSError), e:
		if f:
			f.abort()
		func_call = "write_atomic('%s')" % file_path
		if e.errno == errno.EPERM:
			raise OperationNotPermitted(func_call)
		elif e.errno == errno.EACCES:
			raise PermissionDenied(func_call)
		elif e.errno == errno.EROFS:
			raise ReadOnlyFileSystem(func_call)
		elif e.errno == errno.ENOENT:
			raise FileNotFound(file_path)
		else:
			raise

def ensure_dirs(dir_path, *args, **kwargs):
	"""Create a directory and call apply_permissions.
	Returns True if a directory is created or the permissions needed to be
	modified, and False otherwise."""

	created_dir = False

	try:
		os.makedirs(dir_path)
		created_dir = True
	except OSError, oe:
		func_call = "makedirs('%s')" % dir_path
		if oe.errno in (errno.EEXIST, errno.EISDIR):
			pass
		elif oe.errno == errno.EPERM:
			raise OperationNotPermitted(func_call)
		elif oe.errno == errno.EACCES:
			raise PermissionDenied(func_call)
		elif oe.errno == errno.EROFS:
			raise ReadOnlyFileSystem(func_call)
		else:
			raise
	perms_modified = apply_permissions(dir_path, *args, **kwargs)
	return created_dir or perms_modified

class ObjectProxy(object):

	"""
	Object that acts as a proxy to another object, forwarding
	attribute accesses and method calls. This can be useful
	for implementing lazy initialization.
	"""

	def _get_target(self):
		raise NotImplementedError(self)

	def __getattribute__(self, attr):
		result = object.__getattribute__(self, '_get_target')()
		return getattr(result, attr)

	def __setattr__(self, attr, value):
		result = object.__getattribute__(self, '_get_target')()
		setattr(result, attr, value)

	def __call__(self, *args, **kwargs):
		result = object.__getattribute__(self, '_get_target')()
		return result(*args, **kwargs)

	def __setitem__(self, key, value):
		object.__getattribute__(self, '_get_target')()[key] = value

	def __getitem__(self, key):
		return object.__getattribute__(self, '_get_target')()[key]

	def __delitem__(self, key):
		del object.__getattribute__(self, '_get_target')()[key]

	def __contains__(self, key):
		return key in object.__getattribute__(self, '_get_target')()

	def __iter__(self):
		return iter(object.__getattribute__(self, '_get_target')())

	def __len__(self):
		return len(object.__getattribute__(self, '_get_target')())

	def __repr__(self):
		return repr(object.__getattribute__(self, '_get_target')())

	def __str__(self):
		return str(object.__getattribute__(self, '_get_target')())

	def __hash__(self):
		return hash(object.__getattribute__(self, '_get_target')())

	def __eq__(self, other):
		return object.__getattribute__(self, '_get_target')() == other

	def __ne__(self, other):
		return object.__getattribute__(self, '_get_target')() != other

	def __nonzero__(self):
		return bool(object.__getattribute__(self, '_get_target')())

class LazyItemsDict(dict):
	"""A mapping object that behaves like a standard dict except that it allows
	for lazy initialization of values via callable objects.  Lazy items can be
	overwritten and deleted just as normal items."""
	def __init__(self, initial_items=None):
		dict.__init__(self)
		self.lazy_items = {}
		if initial_items is not None:
			self.update(initial_items)
	def addLazyItem(self, item_key, value_callable, *pargs, **kwargs):
		"""Add a lazy item for the given key.  When the item is requested,
		value_callable will be called with *pargs and **kwargs arguments."""
		self.lazy_items[item_key] = (value_callable, pargs, kwargs)
		# make it show up in self.keys(), etc...
		dict.__setitem__(self, item_key, None)
	def addLazySingleton(self, item_key, value_callable, *pargs, **kwargs):
		"""This is like addLazyItem except value_callable will only be called
		a maximum of 1 time and the result will be cached for future requests."""
		class SingletonItem(object):
			def __init__(self, value_callable, *pargs, **kwargs):
				self._callable = value_callable
				self._pargs = pargs
				self._kwargs = kwargs
				self._called = False
			def __call__(self):
				if not self._called:
					self._called = True
					self._value = self._callable(*self._pargs, **self._kwargs)
				return self._value
		self.addLazyItem(item_key, SingletonItem(value_callable, *pargs, **kwargs))
	def update(self, map_obj):
		if isinstance(map_obj, LazyItemsDict):
			for k in map_obj:
				if k in map_obj.lazy_items:
					dict.__setitem__(self, k, None)
				else:
					dict.__setitem__(self, k, map_obj[k])
			self.lazy_items.update(map_obj.lazy_items)
		else:
			dict.update(self, map_obj)
	def __getitem__(self, item_key):
		if item_key in self.lazy_items:
			value_callable, pargs, kwargs = self.lazy_items[item_key]
			return value_callable(*pargs, **kwargs)
		else:
			return dict.__getitem__(self, item_key)
	def __setitem__(self, item_key, value):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		dict.__setitem__(self, item_key, value)
	def __delitem__(self, item_key):
		if item_key in self.lazy_items:
			del self.lazy_items[item_key]
		dict.__delitem__(self, item_key)

class ConfigProtect(object):
	def __init__(self, myroot, protect_list, mask_list):
		self.myroot = myroot
		self.protect_list = protect_list
		self.mask_list = mask_list
		self.updateprotect()

	def updateprotect(self):
		"""Update internal state for isprotected() calls.  Nonexistent paths
		are ignored."""
		self.protect = []
		self._dirs = set()
		for x in self.protect_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep)))
			mystat = None
			try:
				if stat.S_ISDIR(os.stat(ppath).st_mode):
					self._dirs.add(ppath)
				self.protect.append(ppath)
			except OSError:
				# If it doesn't exist, there's no need to protect it.
				pass

		self.protectmask = []
		for x in self.mask_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep)))
			mystat = None
			try:
				"""Use lstat so that anything, even a broken symlink can be
				protected."""
				if stat.S_ISDIR(os.lstat(ppath).st_mode):
					self._dirs.add(ppath)
				self.protectmask.append(ppath)
				"""Now use stat in case this is a symlink to a directory."""
				if stat.S_ISDIR(os.stat(ppath).st_mode):
					self._dirs.add(ppath)
			except OSError:
				# If it doesn't exist, there's no need to mask it.
				pass

	def isprotected(self, obj):
		"""Returns True if obj is protected, False otherwise.  The caller must
		ensure that obj is normalized with a single leading slash.  A trailing
		slash is optional for directories."""
		masked = 0
		protected = 0
		sep = os.path.sep
		for ppath in self.protect:
			if len(ppath) > masked and obj.startswith(ppath):
				if ppath in self._dirs:
					if obj != ppath and not obj.startswith(ppath + sep):
						# /etc/foo does not match /etc/foobaz
						continue
				elif obj != ppath:
					# force exact match when CONFIG_PROTECT lists a
					# non-directory
					continue
				protected = len(ppath)
				#config file management
				for pmpath in self.protectmask:
					if len(pmpath) >= protected and obj.startswith(pmpath):
						if pmpath in self._dirs:
							if obj != pmpath and \
								not obj.startswith(pmpath + sep):
								# /etc/foo does not match /etc/foobaz
								continue
						elif obj != pmpath:
							# force exact match when CONFIG_PROTECT_MASK lists
							# a non-directory
							continue
						#skip, it's in the mask
						masked = len(pmpath)
		return protected > masked

def new_protect_filename(mydest, newmd5=None):
	"""Resolves a config-protect filename for merging, optionally
	using the last filename if the md5 matches.
	(dest,md5) ==> 'string'            --- path_to_target_filename
	(dest)     ==> ('next', 'highest') --- next_target and most-recent_target
	"""

	# config protection filename format:
	# ._cfg0000_foo
	# 0123456789012
	prot_num = -1
	last_pfile = ""

	if not os.path.exists(mydest):
		return mydest

	real_filename = os.path.basename(mydest)
	real_dirname  = os.path.dirname(mydest)
	for pfile in os.listdir(real_dirname):
		if pfile[0:5] != "._cfg":
			continue
		if pfile[10:] != real_filename:
			continue
		try:
			new_prot_num = int(pfile[5:9])
			if new_prot_num > prot_num:
				prot_num = new_prot_num
				last_pfile = pfile
		except ValueError:
			continue
	prot_num = prot_num + 1

	new_pfile = normalize_path(os.path.join(real_dirname,
		"._cfg" + str(prot_num).zfill(4) + "_" + real_filename))
	old_pfile = normalize_path(os.path.join(real_dirname, last_pfile))
	if last_pfile and newmd5:
		import portage.checksum
		try:
			last_pfile_md5 = portage.checksum.perform_md5(old_pfile)
		except FileNotFound:
			# The file suddenly disappeared or it's a broken symlink.
			pass
		else:
			if last_pfile_md5 == newmd5:
				return old_pfile
	return new_pfile

def getlibpaths(root):
	""" Return a list of paths that are used for library lookups """

	# the following is based on the information from ld.so(8)
	rval = os.environ.get("LD_LIBRARY_PATH", "").split(":")
	rval.extend(grabfile(os.path.join(root, "etc", "ld.so.conf")))
	rval.append("/usr/lib")
	rval.append("/lib")

	rval = [normalize_path(os.path.join(root, x.lstrip(os.path.sep))) \
		for x in rval if x]

	return rval
	
