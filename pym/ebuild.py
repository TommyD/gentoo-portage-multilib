# these classes kind of suck, but work.
# a lot of the ebuild process management crap (spawning a new one when all available are locked)
# should be moved here. for now, it's used as a layer to prevent starting a ebuild-daemon.sh unless needed.
# the reason for this classes existance, is that if the locks are changed to be thread aware, it would be the basis 
# for allowing a regen to take advantage of smp systems (currently limited to single proc)
# also, the portageq hijack allows for a processor to be locked, and have to get the keys from another ebuild.
# until a bash hack is created to allow the daemon to dynamically store/reload envs (*quickly*), it's quicker to 
# startup another daemon.

#!/usr/bin/python
import os,sys,traceback
import portage_const,types
#still needed?
from portage_const import *
import portage_locks, portage_util
import portage_exec
import shutil, anydbm
import stat
import string

def shutdown_all_processors():
	"""kill off all known processors"""
	global active_ebp_list, inactive_ebp_list
	if type(active_ebp_list) != types.ListType:
		print "warning, ebuild.active_ebp_list wasn't a list."
		active_ebp_list = []
	if type(inactive_ebp_list) != types.ListType:
		print "warning, ebuild.inactive_ebp_list wasn't a list."
		inactive_ebp_list = []
	while len(active_ebp_list) > 0:
		try:	active_ebp_list[0].shutdown_processor()
		except (IOError,OSError):
			active_ebp_list.pop(0)
			continue
		try:			active_ebp_list.pop(0)
		except IndexError:	pass
	while len(inactive_ebp_list) > 0:
		try:
			inactive_ebp_list[0].shutdown_processor()
		except (IOError,OSError):
			inactive_ebp_list.pop(0)
			continue
		try:			inactive_ebp_list.pop(0)
		except IndexError:	pass


inactive_ebp_list = []
active_ebp_list = []

def request_ebuild_processor(ebuild_daemon_path=portage_const.EBUILD_DAEMON_PATH,userpriv=False, \
	sandbox=portage_exec.sandbox_capable,fakeroot=False,save_file=None):
	"""request an ebuild_processor instance from the pool, or create a new one
	  this walks through the requirements, matching a inactive processor if one exists
	  note fakerooted processors are never reused, do to the nature of fakeroot"""

	global inactive_ebp_list, active_ebp_list
	if not fakeroot:
		for x in inactive_ebp_list:
			if not x.locked() and x.ebd == ebuild_daemon_path and \
				x.userprived() == userpriv and (x.sandboxed() or not sandbox):
				inactive_ebp_list.remove(x)
				active_ebp_list.append(x)
				return x
	active_ebp_list.append(ebuild_processor(userpriv=userpriv,sandbox=sandbox,fakeroot=fakeroot,save_file=save_file))
	return active_ebp_list[-1]

def release_ebuild_processor(ebp):
	"""the inverse of request_ebuild_processor.  Any processor requested via request_ebuild_processor
	_must_ be released via this function once it's no longer in use.
	this includes fakerooted processors.
	Returns True exempting when the processor requested to be released isn't marked as active"""

	global inactive_ebp_list, active_ebp_list
	try:	active_ebp_list.remove(ebp)
	except ValueError:	return False

	try:	inactive_ebp_list.index(ebp)
	except ValueError:	
		# if it's a fakeroot'd process, we throw it away.  it's not useful outside of a chain of calls
		if not ebp.onetime():
			inactive_ebp_list.append(ebp)
		else:
			del ebp
		return True

	# if it makes it this far, that means ebp was already in the inactive list.
	# which is indicative of an internal fsck up.
	import traceback
	print "ebp was requested to be free'd, yet it already is claimed inactive _and_ was in the active list"
	print "this means somethings horked, badly"
	traceback.print_stack()
	return False
		


class ebuild_processor:
	"""abstraction of a running ebuild.sh instance- the env, functions, etc that ebuilds expect."""
	def __init__(self, ebuild_daemon_path=portage_const.EBUILD_DAEMON_PATH,userpriv=False, sandbox=True, \
		fakeroot=False,save_file=None):
		"""ebuild_daemon_path shouldn't be fooled with unless the caller knows what they're doing.
		sandbox enables a sandboxed processor
		userpriv enables a userpriv'd processor
		fakeroot enables a fakeroot'd processor- this is a mutually exclusive option to sandbox, and 
		requires userpriv to be enabled.  Violating this will result in nastyness"""

		self.ebd = ebuild_daemon_path
		from portage_data import portage_uid, portage_gid
		spawn_opts = {}

		if fakeroot and (sandbox or not userpriv):
			import traceback
			traceback.print_stack()
			print "warning, was asking to enable fakeroot but-"
			print "sandbox",sandbox,"userpriv",userpriv
			print "this isn't valid.  bailing"
			raise Exception,"cannot initialize with sandbox and fakeroot"

		if userpriv:
			self.__userpriv = True
			spawn_opts.update({"uid":portage_uid,"gid":portage_gid,"groups":[portage_gid],"umask":002})
		else:
			if portage_exec.userpriv_capable:
				spawn_opts.update({"gid":portage_gid,"groups":[0,portage_gid]})
			self.__userpriv = False

		# open the pipes to be used for chatting with the new daemon
		cread, cwrite = os.pipe()
		dread, dwrite = os.pipe()
		self.__sandbox = False
		self.__fakeroot = False
		
		# since it's questionable which spawn method we'll use (if sandbox or fakeroot fex), 
		# we ensure the bashrc is invalid.
		env={"BASHRC":"/etc/portage/spork/not/valid/ha/ha"}
		args = []
		if sandbox:
			if fakeroot:
				print "!!! ERROR: fakeroot was on, but sandbox was also on"
				sys.exit(1)
			self.__sandbox = True
			spawn_func = portage_exec.spawn_sandbox
			env.update({"SANDBOX_DEBUG":"1","SANDBOX_DEBUG_LOG":"/var/tmp/test"})

		elif fakeroot:
			self.__fakeroot = True
			spawn_func = portage_exec.spawn_fakeroot
			args.append(save_file)
		else:
			spawn_func = portage_exec.spawn_exec

		self.pid = spawn_func(self.ebd+" daemonize", fd_pipes={0:0, 1:1, 2:2, 3:cread, 4:dwrite},
			returnpid=True,env=env, *args, **spawn_opts)[0]

		os.close(cread)
		os.close(dwrite)
		self.ebd_write = os.fdopen(cwrite,"w")
		self.ebd_read  = os.fdopen(dread,"r")

		# basically a quick "yo" to the daemon
		self.write("dude?")
		if not self.expect("dude!"):
			print "error in server coms, bailing."
			raise Exception("expected 'dude!' response from ebd, which wasn't received. likely a bug")
		if self.__sandbox:
			self.write("sandbox_log?")
			self.__sandbox_log = self.read().split()[0]
		self.dont_export_vars=self.read().split()
		# locking isn't used much, but w/ threading this will matter
		self.unlock()

	def sandboxed(self):
		"""is this instance sandboxed?"""
		return self.__sandbox

	def userprived(self):
		"""is this instance userprived?"""
		return self.__userpriv

	def fakerooted(self):
		"""is this instance fakerooted?"""
		return self.__fakeroot

	def onetime(self):
		"""is this instance going to be discarded after usage; eg is it fakerooted?"""
		return self.__fakeroot

	def write(self, string,flush=True):
		"""talk to running daemon.  Disabling flush is useful when dumping large amounts of data
		all strings written are automatically \\n terminated"""
		if string[-1] == "\n":
			self.ebd_write.write(string)
		else:
			self.ebd_write.write(string +"\n")
		if flush:
			self.ebd_write.flush()
		
	def expect(self, want):
		"""read from the daemon, and return true or false if the returned string is what is expected"""
		got=self.ebd_read.readline()
		return want==got[:-1]

	def read(self,lines=1):
		"""read data from the daemon.  Shouldn't be called except internally"""
		mydata=''
		while lines > 0:
			mydata += self.ebd_read.readline()
			lines -= 1
		return mydata

	def sandbox_summary(self, move_log=False):
		"""if the instance is sandboxed, print the sandbox access summary"""
		if not os.path.exists(self.__sandbox_log):
			self.write("end_sandbox_summary")
			return 0
		violations=portage_util.grabfile(self.__sandbox_log)
		if len(violations)==0:
			self.write("end_sandbox_summary")
			return 0
		if not move_log:
			move_log=self.__sandbox_log
		elif move_log != self.__sandbox_log:
			myf=open(move_log)
			for x in violations:
				myf.write(x+"\n")
			myf.close()
		from output import red
		self.ebd_write.write(red("--------------------------- ACCESS VIOLATION SUMMARY ---------------------------")+"\n")
		self.ebd_write.write(red("LOG FILE = \"%s\"" % move_log)+"\n\n")
		for x in violations:
			self.ebd_write.write(x+"\n")
		self.write(red("--------------------------------------------------------------------------------")+"\n")
		self.write("end_sandbox_summary")
		try:
			os.remove(self.__sandbox_log)
		except (IOError, OSError), e:
			print "exception caught when cleansing sandbox_log=%s" % str(e)
		return 1
		
	def preload_eclasses(self, ec_file):
		"""this preloades eclasses into a function, thus avoiding the cost of going to disk.
		preloading eutils (which is heaviliy inherited) speeds up regen times fex"""
		if not os.path.exists(ec_file):
			return 1
		self.write("preload_eclass %s" % ec_file)
		if self.expect("preload_eclass succeeded"):
			self.preloaded_eclasses=True
			return True
		return False

	def lock(self):
		"""lock the processor.  Currently doesn't block any access, but will"""
		self.processing_lock = True

	def unlock(self):
		"""unlock the processor"""
		self.processing_lock = False

	def locked(self):
		"""is the processor locked?"""
		return self.processing_lock

	def is_alive(self):
		"""returns if it's known if the processor has been shutdown.
		Currently doesn't check to ensure the pid is still running, yet it should"""
		return self.pid != None

	def shutdown_processor(self):
		"""tell the daemon to shut itself down, and mark this instance as dead"""
		try:
			if self.is_alive():
				self.write("shutdown_daemon")
				self.ebd_write.close()
				self.ebd_read.close()

				# now we wait.
				os.waitpid(self.pid,0)
		except (IOError,OSError,ValueError):
			pass

		# we *really* ought to modify portageatexit so that we can set limits for waitpid.
		# currently, this assumes all went well.
		# which isn't always true.
		self.pid = None

	def set_sandbox_state(self,state):
		"""tell the daemon whether to enable the sandbox, or disable it"""
		if state:
			self.write("set_sandbox_state 1")
		else:
			self.write("set_sandbox_state 0")

	def send_env(self, mysettings):
		"""essentially transfer the ebuild's desired env to the running daemon
		accepts a portage.config instance, although it will accept dicts at some point"""
		be=mysettings.bash_environ()
		self.write("start_receiving_env\n")
		exported_keys = ''
		for x in be.keys():
			if x not in self.dont_export_vars:
				self.write("%s=%s\n" % (x,be[x]), flush=False)
				exported_keys += x+' '
		self.write("export "+exported_keys,flush=False)
		self.write("end_receiving_env")
		return self.expect("env_received")
	
	def set_logfile(self,logfile=''):
		"""relevant only when the daemon is sandbox'd, set the logfile"""
		self.write("logging %s" % logfile)
		return self.expect("logging_ack")
	
	
	def __del__(self):
		"""simply attempts to notify the daemon to die"""
		# for this to be reached means we ain't in a list no more.
		if self.pid:
			self.shutdown_processor()


class ebuild_handler:
	"""abstraction of ebuild phases, fetching exported keys, fetching srcs, etc"""
	import portageq
	def __init__(self, process_limit=5):
		"""process_limit is currently ignored"""
		self.processed = 0
		self.__process_limit = process_limit
		self.preloaded_eclasses = False
		self.__ebp = None

	def __del__(self):
		"""only ensures any processors this handler has claimed are released"""
		if self.__ebp:
			release_ebuild_processor(self.__ebp)

	# this is an implementation of stuart's confcache/sandbox trickery, basically the file/md5 stuff implemented in 
	# python with a basic bash wrapper that calls back to this.
	# all credit for the approach goes to him, as stated, this is just an implementation of it.
	# bugs should be thrown at ferringb.
	def load_confcache(self,transfer_to,confcache=portage_const.CONFCACHE_FILE,confcache_list=portage_const.CONFCACHE_LIST):
		"""verifys a requested conf cache, removing the global cache if it's stale.
		The handler should be the only one to call this"""
		from portage_checksum import perform_md5
		from output import red
		if not self.__ebp:
			import traceback
			traceback.print_stack()
			print "err... no ebp, yet load_confcache called. invalid"
			raise Exception,"load_confcache called yet no running processor.  bug?"

		valid=True
		lock=None
		if not os.path.exists(confcache_list):
			print "confcache file listing doesn't exist"
			valid=False
		elif not os.path.exists(confcache):
			print "confcache doesn't exist"
			valid=False
		else:
			lock=portage_locks.lockfile(confcache_list,wantnewlockfile=1)
			try:
				myf=anydbm.open(confcache_list, "r", 0664)
				for l in myf.keys():
					# file, md5
					if perform_md5(l) != myf[l]:
						print red("***")+" confcache is stale: %s: recorded md5: %s: actual: %s:" % (l,myf[l],perform_md5(l))
						raise Exception
				myf.close()
				# verify env now.
				new_cache=[]
				env_vars=[]
				
				# guessing on THOST.  I'm sure it's wrong...

				env_translate={"build_alias":"CBUILD","host_alias":"CHOST","target_alias":"THOST"}
				cache=portage_util.grabfile(confcache)

				x=0
				while x < len(cache):
					#ac_cv_env
					if cache[x][0:10] == "ac_cv_env_":
						f=cache[x][10:].find("_set")
						if f == -1 or f==11:
							cache.pop(x)
							continue
						env_vars.append(cache[x][10:10 + cache[x][10:].find("_set")])
						x += 1
					else:
						new_cache.append(cache[x])
					x += 1

				for x in env_vars:
					self.__ebp.write("request %s" % env_translate.get(x,x))
					line=self.__ebp.read()
					if line[-1] == "\n":
						line=line[:-1]
					new_cache.append("ac_cv_env_%s_set=%s" % (x, line))
					if line == "unset":
						new_cache.append("ac_cv_env_%s_value=" % x)
					else:
						line=self.__ebp.read()
						if line[-1] == "\n":
							line=line[:-1]
						if line.split()[0] != line:
							#quoting... XXX
							new_cache.append("ac_cv_env_%s_value='%s'" % (x,line))
						else:
							new_cache.append("ac_cv_env_%s_value=%s" % (x,line))

				myf=open(confcache,"w")
				for x in new_cache:
					myf.write(x+"\n")
				myf.close()
						
			except SystemExit, e:
				raise
			except Exception,e:
				print "caught exception %s" % str(e)
				try:	myf.close()
				except (IOError, OSError):	pass
				valid=False

		if not valid:
			print "\nconfcache is invalid\n"
			try:	os.remove(confcache_list)
			except: pass
			try:	os.remove(confcache)
			except: pass
			self.__ebp.write("empty")
			valid=0
		else:
			self.__ebp.write("location: %s" % confcache)
			valid=1
		if lock:
			portage_locks.unlockfile(lock)
		return valid

	def update_confcache(self,settings,logfile,new_confcache, confcache=portage_const.CONFCACHE_FILE, \
		confcache_list=portage_const.CONFCACHE_LIST):
		"""internal function called when a processor has finished a configure, and wishes its cache
		be transferred to the global cache
		This runs through the sandbox log, storing the md5 of files along with the list of files to check.
		Finally, it transfers the cache to the global location."""

		if not self.__ebp:
			import traceback
			traceback.print_stack()
			print "err... no ebp, yet load_confcache called. invalid"
			sys.exit(1)

		import re
		from portage_checksum import perform_md5
		if not (os.path.exists(logfile) and os.path.exists(new_confcache)) :
			# eh?  wth?
			self.__ebp.write("failed")
			return 0
		myfiles=portage_util.grabfile(logfile)
		filter=re.compile('^(%s|/tmp|/dev|.*/\.ccache)/' % os.path.normpath(settings["PORTAGE_TMPDIR"]))
		l=[]
		for x in myfiles:
			# get only read syscalls...
			if x[0:8] == "open_rd:":
				l.append(x.split()[1])

		myfiles = portage_util.unique_array(l)
		l=[]
		for x in myfiles:
			if not os.path.exists(x):
				continue
			if not filter.match(x):
				l.append(x)
		del myfiles

		if not len(l):
			self.__ebp.write("updated")
			return 0

		lock=portage_locks.lockfile(confcache_list,wantnewlockfile=1)
		# update phase.
		if not os.path.exists(confcache_list):
			prevmask=os.umask(0)
			myf=anydbm.open(confcache_list,"n",0664)
			os.umask(prevmask)
		else:
			myf=anydbm.open(confcache_list,"w",0664)

		for x in l:
			try:
				if not stat.S_ISDIR(os.stat(x).st_mode) and not myf.has_key(x):
					myf[x]=str(perform_md5(x))
			except (IOError, OSError):
				# exceptions are only possibly (ignoring anydbm horkage) from os.stat
				pass
		myf.close()
		from portage_data import portage_gid
		os.chown(confcache_list, -1, portage_gid)
		shutil.move(new_confcache, confcache)
		os.chown(confcache, -1, portage_gid)
		m=os.umask(0)
		os.chmod(confcache, 0664)
		os.chmod(confcache_list, 0664)
		os.umask(m)
		portage_locks.unlockfile(lock)
		self.__ebp.write("updated")
		return 0

	def get_keys(self,myebuild,mysettings,myroot="/"):
		"""request the auxdbkeys from an ebuild
		returns a dict"""
#		print "getting keys for %s" % myebuild
		# normally,
		# userpriv'd, minus sandbox.  which is odd.
		# I say both, personally (and I'm writing it, so live with it)
		if self.__ebp:
			import traceback
			traceback.print_stack()
			print "self.__ebp exists. it shouldn't.  this indicates a handler w/ an active ebp never"
			print "released it, or a bug in the calls"
			sys.exit(1)


		self.__ebp = request_ebuild_processor(userpriv=portage_exec.userpriv_capable)

		if self.__adjust_env("depend",mysettings,myebuild,myroot):
			return {}

		self.__ebp.write("process_ebuild depend")
		self.__ebp.send_env(mysettings)
		self.__ebp.set_sandbox_state(True)
		self.__ebp.write("start_processing")
		line=self.__generic_phase(["sending_keys"],mysettings,interpret_results=False)
		if line != "sending_keys":
			return {}
		mykeys={}
		while line != "end_keys":
			line=self.__ebp.read()
			line=line[:-1]
			if line == "failed":
				self.__ebp.unlock()
				return {}
			if line == "end_keys" or not len(line):
				continue
			pair = line.split('=',1)
			mykeys[pair[0]]=pair[1]
		self.__ebp.expect("phases succeeded")
		if not release_ebuild_processor(self.__ebp):
			self.__ebp = None
			raise Exception,"crud"
		self.__ebp = None
		return mykeys

	def __adjust_env(self,mydo,mysettings,myebuild,myroot,debug=0,listonly=0,fetchonly=0,cleanup=0,dbkey=None,\
			use_cache=1,fetchall=0,tree="porttree",use_info_env=True,verbosity=0):
		"""formerly portage.doebuild, since it's specific to ebuilds, it's now a method of ebuild handling.
		severely gutted, and in need of cleansing/exorcism"""
		from portage import db,ExtractKernelVersion,fetch,features, \
			digestgen,digestcheck,root,flatten
		from portage_data import portage_uid,portage_gid,secpass
		import portage_dep
		from portage_util import writemsg

		ebuild_path = os.path.abspath(myebuild)
		pkg_dir     = os.path.dirname(ebuild_path)
	
		if mysettings.configdict["pkg"].has_key("CATEGORY"):
			cat = mysettings.configdict["pkg"]["CATEGORY"]
		else:
			cat         = os.path.basename(os.path.normpath(pkg_dir+"/.."))
		mypv        = os.path.basename(ebuild_path)[:-7]
		mycpv       = cat+"/"+mypv
	
		mysplit=portage_dep.pkgsplit(mypv,silent=0)
		if mysplit==None:
			writemsg("!!! Error: PF is null '%s'; exiting.\n" % mypv)
			return 1

		if mydo == "clean":
			cleanup=True
	
		if mydo != "depend":
			# XXX: We're doing a little hack here to curtain the gvisible locking
			# XXX: that creates a deadlock... Really need to isolate that.
			mysettings.reset(use_cache=use_cache)
			
		mysettings.setcpv(mycpv,use_cache=use_cache)
	
		if not os.path.exists(myebuild):
			writemsg("!!! doebuild: "+str(myebuild)+" not found for "+str(mydo)+"\n")
			return 1

		if debug: # Otherwise it overrides emerge's settings.
			# We have no other way to set debug... debug can't be passed in
			# due to how it's coded... Don't overwrite this so we can use it.
			mysettings["PORTAGE_DEBUG"]=str(debug)
	
		mysettings["ROOT"]     = myroot
	
		mysettings["EBUILD"]   = ebuild_path
		mysettings["O"]        = pkg_dir
		mysettings["CATEGORY"] = cat
		mysettings["FILESDIR"] = pkg_dir+"/files"
		mysettings["PF"]       = mypv
		
		mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"

		mysettings["PROFILE_PATHS"] = PROFILE_PATH+"\n"+CUSTOM_PROFILE_PATH
		mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
		mysettings["PN"] = mysplit[0]
		mysettings["PV"] = mysplit[1]
		mysettings["PR"] = mysplit[2]
	

		# bailing now, probably horks a few things up, but neh.
		# got to break a few eggs to make an omelot after all (spelling is wrong, too) :)
		if mydo=="unmerge":
			return 0

		if mydo!="depend":
			try:
				mysettings["INHERITED"],mysettings["PORTAGE_RESTRICT"] = db[root][tree].dbapi.aux_get(
					mycpv,["INHERITED","RESTRICT"])

				mysettings["PORTAGE_RESTRICT"]=string.join(flatten(portage_dep.use_reduce(
					portage_dep.paren_reduce(mysettings["PORTAGE_RESTRICT"]), 
					uselist=mysettings["USE"].split() )),' ')

			except SystemExit, e:
				raise
			except Exception, e:
				print "caught exception %s in ebd_proc:doebuild" % str(e)
				pass
	

		if mysplit[2] == "r0":
			mysettings["PVR"]=mysplit[1]
		else:
			mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]
	
		mysettings["SLOT"]=""
	
		if mysettings.has_key("PATH"):
			mysplit=string.split(mysettings["PATH"],":")
		else:
			mysplit=[]

		if PORTAGE_BIN_PATH not in mysplit:
			mysettings["PATH"]=PORTAGE_BIN_PATH+":"+mysettings["PATH"]
	
		mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
		if tree=="bintree":
			mysettings["BUILD_PREFIX"] += "-pkg"

		mysettings["HOME"]         = mysettings["BUILD_PREFIX"]+"/homedir"
		mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/portage-pkg"
		mysettings["BUILDDIR"]     = mysettings["BUILD_PREFIX"]+"/"+mysettings["PF"]

		if cleanup and os.path.exists(mysettings["BUILDDIR"]):
			print "cleansing builddir"+mysettings["BUILDDIR"]
			shutil.rmtree(mysettings["BUILDDIR"])

		if mydo=="clean":
			# if clean, just flat out skip the rest of this crap.
			return 0			
	
		mysettings["PORTAGE_BASHRC"] = EBUILD_SH_ENV_FILE
	
		#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.

		if mydo not in ["depend","fetch","digest","manifest"]:
			if not mysettings.has_key("KV"):
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
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey),2)
			if dbkey:
				mysettings["dbkey"] = dbkey
			else:
				mysettings["dbkey"] = mysettings.depcachedir+"/aux_db_key_temp"
	
			return 0
			
		mysettings["PORTAGE_LOGFILE"]=''
		logfile=None


		#fetch/digest crap
		if mydo not in ["prerm","postrm","preinst","postinst","config","help","setup","unmerge"]:

			newuris, alist = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings)
			alluris, aalist = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings,all=1)
			mysettings["A"]=string.join(alist," ")
			mysettings["AA"]=string.join(aalist," ")
			if ("mirror" in features) or fetchall:
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
				if ((mystat[stat.ST_GID]!=portage_gid) or ((mystat[stat.ST_MODE]&00775)!=00775)) and not listonly:
					print "*** Adjusting cvs-src permissions for portage user..."
					os.chown(mysettings["DISTDIR"]+"/cvs-src",0,portage_gid)
					os.chmod(mysettings["DISTDIR"]+"/cvs-src",00775)
					portage_exec.spawn("chgrp -R "+str(portage_gid)+" "+mysettings["DISTDIR"]+"/cvs-src")
					portage_exec.spawn("chmod -R g+rw "+mysettings["DISTDIR"]+"/cvs-src")
			except (IOError, OSError):
				pass

			if not fetch(fetchme, mysettings, listonly=listonly, fetchonly=fetchonly,verbosity=verbosity):
				return 1

			if mydo=="fetch" and listonly:
				return 0

			if "digest" in features:
				#generate digest if it doesn't exist.
				if mydo=="digest":
					# exemption to the return rule
					return (not digestgen(aalist,mysettings,overwrite=1,verbosity=verbosity))
				else:
					digestgen(aalist,mysettings,overwrite=0,verbosity=verbosity)

			elif mydo=="digest":
				#since we are calling "digest" directly, recreate the digest even if it already exists
				return (not digestgen(checkme,mysettings,overwrite=1,verbosity=verbosity))
			if mydo=="manifest":
				return (not digestgen(checkme,mysettings,overwrite=1,manifestonly=1,verbosity=verbosity))
	
			if not digestcheck(checkme, mysettings, ("strict" in features),verbosity=verbosity):
				return 1
		
			if mydo=="fetch":
				return 0

		if not os.path.exists(mysettings["BUILD_PREFIX"]):
			os.makedirs(mysettings["BUILD_PREFIX"])
		os.chown(mysettings["BUILD_PREFIX"],portage_uid,portage_gid)
		os.chmod(mysettings["BUILD_PREFIX"],00775)

		# Should be ok again to set $T, as sandbox does not depend on it
		mysettings["T"]=mysettings["BUILDDIR"]+"/temp"

		if not os.path.exists(mysettings["T"]):
			print "creating temp dir"
			os.makedirs(mysettings["T"])
		os.chown(mysettings["T"],portage_uid,portage_gid)
		os.chmod(mysettings["T"],0770)
	
		try:
			if ("nouserpriv" not in string.split(mysettings["RESTRICT"])):
				if ("userpriv" in features) and (portage_uid and portage_gid):
					if (secpass==2):
						if os.path.exists(mysettings["HOME"]):
							portage_exec.spawn("rm -Rf "+mysettings["HOME"])
						if not os.path.exists(mysettings["HOME"]):
							os.makedirs(mysettings["HOME"])
				elif ("userpriv" in features):
					print "!!! Disabling userpriv from features... Portage UID/GID not valid."
					del features[features.index("userpriv")]
		except (IOError, OSError), e:
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
			if not os.path.exists(mysettings["HOME"]):
				os.makedirs(mysettings["HOME"])
			os.chown(mysettings["HOME"],portage_uid,portage_gid)
			os.chmod(mysettings["HOME"],02770)

		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Failed to create fake home directory in BUILDDIR"
			print "!!!",str(e)
			return 1

		try:
			if ("userpriv" in features) and ("ccache" in features):
				if (not mysettings.has_key("CCACHE_DIR")) or (mysettings["CCACHE_DIR"]==""):
					mysettings["CCACHE_DIR"]=mysettings["PORTAGE_TMPDIR"]+"/ccache"
				if not os.path.exists(mysettings["CCACHE_DIR"]):
					os.makedirs(mysettings["CCACHE_DIR"])
				os.chown(mysettings["CCACHE_DIR"],portage_uid,portage_gid)
				os.chmod(mysettings["CCACHE_DIR"],02775)
		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Perhaps: rm -Rf",mysettings["BUILD_PREFIX"]
			print "!!!",str(e)
			return 1

		try:
			mystat=os.stat(mysettings["CCACHE_DIR"])
			if (mystat[stat.ST_GID]!=portage_gid) or ((mystat[stat.ST_MODE]&02070)!=02070):
				print "*** Adjusting ccache permissions for portage user..."
				os.chown(mysettings["CCACHE_DIR"],portage_uid,portage_gid)
				os.chmod(mysettings["CCACHE_DIR"],02770)
				portage_exec.spawn("chown -R "+str(portage_uid)+":"+str(portage_gid)+" "+mysettings["CCACHE_DIR"])
				portage_exec.spawn("chmod -R g+rw "+mysettings["CCACHE_DIR"])
		except (OSError, IOError):
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

		# break off into process_phase
		if mysettings.has_key("PORT_LOGDIR"):
			if os.access(mysettings["PORT_LOGDIR"]+"/",os.W_OK):
				try:
					os.chown(mysettings["BUILD_PREFIX"],portage_uid,portage_gid)
					os.chmod(mysettings["PORT_LOGDIR"],00770)
					if not mysettings.has_key("LOG_PF") or (mysettings["LOG_PF"] != mysettings["PF"]):
						mysettings["LOG_PF"]=mysettings["PF"]
						mysettings["LOG_COUNTER"]=str(db[myroot]["vartree"].dbapi.get_counter_tick_core("/"))
					mysettings["PORTAGE_LOGFILE"]="%s/%s-%s.log" % (mysettings["PORT_LOGDIR"],mysettings["LOG_COUNTER"],mysettings["LOG_PF"])
				except ValueError, e:
					mysettings["PORT_LOGDIR"]=""
					print "!!! Unable to chown/chmod PORT_LOGDIR. Disabling logging."
					print "!!!",e
			else:
				print "!!! Cannot create log... No write access / Does not exist"
				print "!!! PORT_LOGDIR:",mysettings["PORT_LOGDIR"]
				mysettings["PORT_LOGDIR"]=""

		# if any of these are being called, handle them -- running them out of the sandbox -- and stop now.
		if mydo in ["help","setup"]:
			return 0
#			return spawn(EBUILD_SH_BINARY+" "+mydo,mysettings,debug=debug,free=1,logfile=logfile)
		elif mydo in ["prerm","postrm","preinst","postinst","config"]:
			mysettings.load_infodir(pkg_dir)
			if not use_info_env:
				print "overloading port_env_file setting to %s" % mysettings["T"]+"/environment"
				mysettings["PORT_ENV_FILE"] = mysettings["T"] + "/environment"
				if not os.path.exists(mysettings["PORT_ENV_FILE"]):
					from output import red
					print red("!!!")+" err.. it doesn't exist.  that's bad."
					sys.exit(1)
			return 0
#			return spawn(EBUILD_SH_BINARY+" "+mydo,mysettings,debug=debug,free=1,logfile=logfile)
	
		try: 
			mysettings["SLOT"], mysettings["RESTRICT"] = db["/"]["porttree"].dbapi.aux_get(mycpv,["SLOT","RESTRICT"])
		except (IOError,KeyError):
			print red("doebuild():")+" aux_get() error; aborting."
			sys.exit(1)

		#initial dep checks complete; time to process main commands
	
		nosandbox=(("userpriv" in features) and ("usersandbox" not in features))
		actionmap={
				  "depend": {                 "args":(0,1)},         # sandbox  / portage
				  "setup":  {                 "args":(1,0)},         # without  / root
				 "unpack":  {"dep":"setup",   "args":(0,1)},         # sandbox  / portage
				"compile":  {"dep":"unpack",  "args":(nosandbox,1)}, # optional / portage
				   "test":  {"dep":"compile", "args":(nosandbox,1)}, # optional / portage
				"install":  {"dep":"test",    "args":(0,0)},         # sandbox  / root
				    "rpm":  {"dep":"install", "args":(0,0)},         # sandbox  / root
    				"package":  {"dep":"install", "args":(0,0)},         # sandbox  / root
		}
	
		if mydo in actionmap.keys():	
			if mydo=="package":
				for x in ["","/"+mysettings["CATEGORY"],"/All"]:
					if not os.path.exists(mysettings["PKGDIR"]+x):
						os.makedirs(mysettings["PKGDIR"]+x)
			# REBUILD CODE FOR TBZ2 --- XXXX
			return 0
#			return spawnebuild(mydo,actionmap,mysettings,debug,logfile=logfile)
		elif mydo=="qmerge": 
			#check to ensure install was run.  this *only* pops up when users forget it and are using ebuild
			bail=False
			if not os.path.exists(mysettings["BUILDDIR"]+"/.completed_stages"):
				bail=True
			else:
				myf=open(mysettings["BUILDDIR"]+"/.completed_stages")
				myd=myf.readlines()
				myf.close()
				if len(myd) == 0:
					bail = True
				else:
					bail = ("install" not in myd[0].split())
			if bail:
				print "!!! mydo=qmerge, but install phase hasn't been ran"
				sys.exit(1)

			#qmerge is specifically not supposed to do a runtime dep check
			return 0
#			return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,mysettings)
		elif mydo=="merge":
			return 0
#			retval=spawnebuild("install",actionmap,mysettings,debug,alwaysdep=1,logfile=logfile)
			if retval:
				return retval

#			return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,mysettings,myebuild=mysettings["EBUILD"])
		else:
			print "!!! Unknown mydo:",mydo
			sys.exit(1)

	# phases
	# my... god... this... is... ugly.
	# we're talking red headed step child of medusa ugly here.

	def process_phase(self,phase,mysettings,myebuild,myroot,allstages=False,**keywords):
		"""the public 'doebuild' interface- all phases are called here, along w/ a valid config
		allstages is the equivalent of 'do merge, and all needed phases to get to it'
		**keywords is options passed on to __adjust_env.  It will be removed as __adjust_env is digested"""
		from portage import merge,unmerge,features

		validcommands = ["help","clean","prerm","postrm","preinst","postinst",
		                "config","setup","depend","fetch","digest",
		                "unpack","compile","test","install","rpm","qmerge","merge",
		                "package","unmerge", "manifest"]
	
		if phase not in validcommands:
			validcommands.sort()
			writemsg("!!! doebuild: '%s' is not one of the following valid commands:" % phase)
			for vcount in range(len(validcommands)):
				if vcount%6 == 0:
					writemsg("\n!!! ")
				writemsg(string.ljust(validcommands[vcount], 11))
			writemsg("\n")
			return 1

		retval=self.__adjust_env(phase,mysettings,myebuild,myroot,**keywords)
		if retval:
			return retval

		if "userpriv" in features:
			sandbox = ("usersandbox" in features)
		else:
			sandbox = ("sandbox" in features)

	        droppriv=(("userpriv" in features) and \
	                ("nouserpriv" not in string.split(mysettings["RESTRICT"])) and portage_exec.userpriv_capable)
		use_fakeroot=(("userpriv_fakeroot" in features) and droppriv and portage_exec.fakeroot_capable)

		# basically a nasty graph of 'w/ this phase, have it userprived/sandboxed/fakeroot', and run
		# these phases prior
		actionmap={
			  "depend": {                "sandbox":False,	"userpriv":True, "fakeroot":False},
			  "setup":  {                "sandbox":True,	"userpriv":False, "fakeroot":False},
			 "unpack":  {"dep":"setup",  "sandbox":sandbox,	"userpriv":True, "fakeroot":False},
			"compile":  {"dep":"unpack", "sandbox":sandbox,"userpriv":True, "fakeroot":False},
			   "test":  {"dep":"compile","sandbox":sandbox,"userpriv":True, "fakeroot":False},
			"install":  {"dep":"test",   "sandbox":(not use_fakeroot or (not use_fakeroot and sandbox)),
									"userpriv":use_fakeroot,"fakeroot":use_fakeroot},
			    "rpm":  {"dep":"install","sandbox":False,	"userpriv":use_fakeroot, "fakeroot":use_fakeroot},
	    		"package":  {"dep":"install", "sandbox":False,	"userpriv":use_fakeroot, "fakeroot":use_fakeroot},
			"merge"	 :  {"dep":"install", "sandbox":True,	"userpriv":False, "fakeroot":False}
		}

		# this shouldn't technically ever be called, get_keys exists for this.
		# left in for compatability while portage.doebuild still exists
		if phase=="depend":
			return retval
		elif phase=="unmerge":
			return unmerge(mysettings["CATEGORY"],mysettings["PF"],myroot,mysettings)
		elif phase in ["fetch","digest","manifest","clean"]:
			return retval
		elif phase=="qmerge":
			#no phases ran.
			return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,\
				mysettings)

		elif phase in ["help","clean","prerm","postrm","preinst","postinst","config"]:
			self.__ebp = request_ebuild_processor(userpriv=False)
			self.__ebp.write("process_ebuild %s" % phase)
			self.__ebp.send_env(mysettings)
			self.__ebp.set_sandbox_state(phase in ["help","clean"])
			self.__ebp.write("start_processing")
			retval = self.__generic_phase([],mysettings)
			release_ebuild_processor(self.__ebp)
			self.__ebp = None
			return not retval

		k=phase
		merging=False
		# represent the phases to run, grouping each phase based upon if it's sandboxed, fakerooted, and userpriv'd
		# ugly at a glance, but remember a processor can run multiple phases now.
		# best to not be wasteful in terms of env saving/restoring, and just run all applicable phases in one shot
		phases=[[[phase]]]
		sandboxed=[[actionmap[phase]["sandbox"]]]
		privs=[(actionmap[phase]["userpriv"],actionmap[phase]["fakeroot"])]

		if allstages:
			while actionmap[k].has_key("dep"):
				k=actionmap[k]["dep"]
				if actionmap[k]["userpriv"] != privs[-1][0] or actionmap[k]["fakeroot"] != privs[-1][1]:
					phases.append([[k]])
					sandboxed.append([actionmap[k]["sandbox"]])
					privs.append((actionmap[k]["userpriv"],actionmap[k]["fakeroot"]))
				elif actionmap[k]["sandbox"] != sandboxed[-1][-1]:
					phases[-1].append([k])
					sandboxed[-1].extend([actionmap[k]["sandbox"]])
				else:
					phases[-1][-1].append(k)
			privs.reverse()
			phases.reverse()
			sandboxed.reverse()
			for x in phases:
				for y in x:
					y.reverse()
				x.reverse()
		# and now we have our phases grouped in parallel to the sandbox/userpriv/fakeroot state.

		all_phases = portage_util.flatten(phases)

#		print "all_phases=",all_phases
#		print "phases=",phases
#		print "sandbox=",sandboxed
#		print "privs=",privs
#		sys.exit(1)
#		print "\n\ndroppriv=",droppriv,"use_fakeroot=",use_fakeroot,"\n\n"

		#temporary hack until sandbox + fakeroot (if ever) play nice.
		while privs:
			if self.__ebp == None or (droppriv and self.__ebp.userprived() != privs[0][0]) or \
				(use_fakeroot and self.__ebp.fakerooted() != privs[0][1]):
				if self.__ebp != None:
					print "swapping processors for",phases[0][0]
					release_ebuild_processor(self.__ebp)
					self.__ebp = None
				opts={}

				#only engage fakeroot when userpriv'd
				if use_fakeroot and privs[0][1]:
					opts["save_file"] = mysettings["T"]+"/fakeroot_db"

				self.__ebp = request_ebuild_processor(userpriv=(privs[0][0] and droppriv), \
					fakeroot=(privs[0][1] and use_fakeroot), \

				sandbox=(not (privs[0][1] and use_fakeroot) and portage_exec.sandbox_capable),**opts)

			#loop through the instances where the processor must have the same sandboxed state-
			#note a sandbox'd process can have it's sandbox disabled.
			#this seperation is needed since you can't mix sandbox and fakeroot atm.
			for sandbox in sandboxed[0]:
				if "merge" in phases[0][0]:
					if len(phases[0][0]) == 1:
						print "skipping this phase, it's just merge"
						continue
					phases[0][0].remove("merge")

				self.__ebp.write("process_ebuild %s" % string.join(phases[0][0]," "))
				self.__ebp.send_env(mysettings)
				self.__ebp.set_sandbox_state(sandbox)
				self.__ebp.write("start_processing")
				phases[0].pop(0)
				retval = not self.__generic_phase([],mysettings)
				if retval:
					release_ebuild_processor(self.__ebp)
					self.__ebp = None
					return retval
			sandboxed.pop(0)
			privs.pop(0)
			phases.pop(0)
		# hey hey. we're done.  Now give it back.
		release_ebuild_processor(self.__ebp)
		self.__ebp = None

		# packaging moved out of ebuild.sh, and into this code.
		# makes it so ebuild.sh no longer must run as root for the package phase.
		if "package" in all_phases:
			print "processing package"
			#mv "${PF}.tbz2" "${PKGDIR}/All" 
			if not os.path.exists(mysettings["PKGDIR"]+"/All"):
				os.makedirs(mysettings["PKGDIR"]+"/All")
			if not os.path.exists(mysettings["PKGDIR"]+"/"+mysettings["CATEGORY"]):
				os.makedirs(mysettings["PKGDIR"]+"/"+mysettings["CATEGORY"])
			if os.path.exists("%s/All/%s.tbz2" % (mysettings["PKGDIR"],mysettings["PF"])):
				os.remove("%s/All/%s.tbz2" % (mysettings["PKGDIR"],mysettings["PF"]))
			retval = not portage_util.movefile("%s/%s.tbz2" % (mysettings["BUILDDIR"],mysettings["PF"]),
				mysettings["PKGDIR"]+"/All/"+mysettings["PF"]+".tbz2") > 0
			if retval:	return False
			if os.path.exists("%s/%s/%s.tbz2" % (mysettings["PKGDIR"],mysettings["CATEGORY"],mysettings["PF"])):
				os.remove("%s/%s/%s.tbz2" % (mysettings["PKGDIR"],mysettings["CATEGORY"],mysettings["PF"]))
			os.symlink("%s/All/%s.tbz2" % (mysettings["PKGDIR"],mysettings["PF"]),
				"%s/%s/%s.tbz2" % (mysettings["PKGDIR"],mysettings["CATEGORY"],mysettings["PF"]))

		#same as the package phase above, removes the root requirement for the rpm phase.
		if "rpm" in all_phases:
			rpm_name="%s-%s-%s" % (mysettings["PN"],mysettings["PV"],mysettings["PR"])

			retval = not portage_util.movefile("%s/%s.tar.gz" % (mysettings["T"],mysettings["PF"]),
				"/usr/src/redhat/SOURCES/%s.tar.gz" % mysettings["PF"]) > 0
			if retval:
				print "moving src for rpm failed, retval=",retval
				return False

			retval=portage_exec.spawn(("rpmbuild","-bb","%s/%s.spec" % \
				(mysettings["BUILDDIR"],mysettings["PF"])))
			if retval:
				print "Failed to integrate rpm spec file"
				return retval

			if not os.path.exists(mysettings["RPMDIR"]+"/"+mysettings["CATEGORY"]):
				os.makedirs(mysettings["RPMDIR"]+"/"+mysettings["CATEGORY"])

			retval = not portage_util.movefile("/usr/src/redhat/RPMS/i386/%s.i386.rpm" % rpm_name,
				"%s/%s/%s.rpm" % (mysettings["RPMDIR"],mysettings["CATEGORY"],rpm_name)) > 0
			if retval:
				print "rpm failed"
				return retval


		# not great check, but it works.
		# basically, if FEATURES="-buildpkg" emerge package was called, the files in the current 
		# image directory don't have their actual perms.  so we use an ugly bit of bash
		# to make the fakeroot (claimed) permissions/owners a reality.
		if use_fakeroot and os.path.exists(mysettings["T"]+"/fakeroot_db") and all_phases[-1] == "merge":
			print "correcting fakeroot privs"
			retval=portage_exec.spawn(("/usr/lib/portage/bin/affect-fakeroot-perms.sh", \
				mysettings["T"]+"/fakeroot_db", \
				mysettings["D"]),env={"BASHRC":portage_const.INVALID_ENV_FILE})
			if retval or retval == None:
				print red("!!!")+"affecting fakeroot perms after the fact failed"
				return retval

		if "merge" in all_phases:
			print "processing merge"
			retval = merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["BUILDDIR"]+"/build-info",myroot,\
				mysettings,myebuild=mysettings["EBUILD"])
		return retval

	# this basically handles all hijacks from the daemon, whether confcache or portageq.
	def __generic_phase(self,breakers,mysettings,interpret_results=True):
		"""internal function that responds to the running ebuild processor's requests
		this enables portageq hijack, sandbox summaries, confcache among other things
		interpret_results controls whether this returns true/false, or the string the 
		processor spoke that caused this to release control
		breaks is list of strings that cause this loop/interpretter to relinquish control"""
		b = breakers[:]
		b.extend(["prob","phases failed","phases succeeded","env_receiving_failed"])
		line=''
		while line not in b:
			line=self.__ebp.read()
			line=line[:-1]
			if line[0:23] == "request_sandbox_summary":
				self.__ebp.sandbox_summary(line[24:])
			elif line[0:17] == "request_confcache":
				self.load_confcache(line[18:])
			elif line[0:16] == "update_confcache":
				k=line[17:].split()
				# sandbox_debug_log, local_cache
				self.update_confcache(mysettings,k[0],k[1])
			elif line[0:8] == "portageq":
				keys=line[8:].split()
				try:
					e,s=getattr(self.portageq,keys[0])(keys[1:])
				except SystemExit, e:
					raise
				except Exception, ex:
					sys.stderr.write("caught exception %s\n" % str(ex))
					e=2
					s="ERROR: insufficient paramters!"
				self.__ebp.write("return_code="+str(e))
				if len(s):
					self.__ebp.write(s)
				self.__ebp.write("stop_text")
		self.processed += 1
		if interpret_results:
			return (line=="phases succeeded")
		return line

