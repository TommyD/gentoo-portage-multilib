# portage: Lock management code
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

import atexit
import errno
import os
import stat
import string
import time
import types
import portage_exception
import portage_file
import portage_util
import portage_data
from portage_localization import _

HARDLINK_FD = -2

hardlock_path_list = []
def clean_my_hardlocks():
	for x in hardlock_path_list:
		hardlock_cleanup(x)
def add_hardlock_file_to_cleanup(path):
	mypath = portage_file.normpath(path)
	if os.path.isfile(mypath):
		mypath = os.path.dirname(mypath)
	if os.path.isdir(mypath):
		hardlock_path_list = mypath[:]

atexit.register(clean_my_hardlocks)

def lockdir(mydir):
	return lockfile(mydir,wantnewlockfile=1)
def unlockdir(mylock):
	return unlockfile(mylock)

def lockfile(mypath,wantnewlockfile=0,unlinkfile=0,verbosity=0):
	"""Creates all dirs upto, the given dir. Creates a lockfile
	for the given directory as the file: directoryname+'.portage_lockfile'."""
	import fcntl

	if not mypath:
		raise portage_exception.InvalidData, "Empty path given"

	if type(mypath) == types.StringType and mypath[-1] == '/':
		mypath = mypath[:-1]

	if type(mypath) == types.FileType:
		mypath = mypath.fileno()
	if type(mypath) == types.IntType:
		lockfilename    = mypath
		wantnewlockfile = 0
		unlinkfile      = 0
	elif wantnewlockfile:
		lockfilename = mypath+".portage_lockfile"
		unlinkfile   = 1
	else:
		lockfilename = mypath
	
	if type(mypath) == types.StringType:
		if not os.path.exists(os.path.dirname(mypath)):
			raise portage_exception.DirectoryNotFound, os.path.dirname(mypath)
		if not os.path.exists(lockfilename):
			old_mask=os.umask(000)
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR,0660)
			try:
				if os.stat(lockfilename).st_gid != portage_data.portage_gid:
					os.chown(lockfilename,os.getuid(),portage_data.portage_gid)
			except SystemExit, e:
				raise
			except OSError, e:
				if e[0] == 2: # No such file or directory
					return lockfile(mypath,wantnewlockfile,unlinkfile)
				else:
					portage_util.writemsg("Cannot chown a lockfile. This could cause inconvenience later.\n",verbosity)
			os.umask(old_mask)
		else:
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR,0660)

	elif type(mypath) == types.IntType:
		myfd = mypath

	else:
		raise ValueError, "Unknown type passed in '%s': '%s'" % (type(mypath),mypath)

	# try for a non-blocking lock, if it's held, throw a message
	# we're waiting on lockfile and use a blocking attempt.
	locking_method = None
	link_success=False
	for locking_method in (fcntl.flock, fcntl.lockf):
		try:
			locking_method(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
			link_success=True
			break
		except IOError, e:
			if "errno" not in dir(e):
				raise
			if e.errno == errno.EAGAIN:
				# resource temp unavailable; eg, someone beat us to the lock.
				if type(mypath) == types.IntType:
					portage_util.writemsg("waiting for lock on fd %i\n" % myfd,verbosity)
				else:
					portage_util.writemsg("waiting for lock on %s\n" % lockfilename,verbosity)
				# try for the exclusive lock now.
				locking_method(myfd,fcntl.LOCK_EX)
			elif e.errno == errno.ENOLCK:
				pass
			else:
				raise


	if not link_success:
		# We're not allowed to lock on this FS.
		os.close(myfd)
		link_success = False
		if lockfilename == str(lockfilename):
			if wantnewlockfile:
				try:
					if os.stat(lockfilename)[stat.ST_NLINK] == 1:
						os.unlink(lockfilename)
				except Exception, e:
					pass
				link_success = hardlink_lockfile(lockfilename)
		if not link_success:
			raise
		locking_method = None
		myfd = HARDLINK_FD


		
	if type(lockfilename) == types.StringType and not os.path.exists(lockfilename):
		# The file was deleted on us... Keep trying to make one...
		os.close(myfd)
		portage_util.writemsg("lockfile recurse\n",verbosity+1)
		lockfilename,myfd,unlinkfile,locking_method,verbosity = lockfile(mypath,wantnewlockfile,unlinkfile,verbosity)

	portage_util.writemsg(str((lockfilename,myfd,unlinkfile))+"\n",verbosity+1)
	return (lockfilename,myfd,unlinkfile,locking_method,verbosity)

def unlockfile(mytuple):
	import fcntl

	#XXX: Compatability hack.
	if len(mytuple) == 3:
		lockfilename,myfd,unlinkfile = mytuple
		locking_method = fcntl.flock
		verbosity=0
	elif len(mytuple) == 4:
		lockfilename,myfd,unlinkfile,locking_method = mytuple
		verbosity=0
	elif len(mytuple) == 5:
		lockfilename,myfd,unlinkfile,locking_method,verbosity = mytuple
	else:
		raise

	if(myfd == HARDLINK_FD):
		unhardlink_lockfile(lockfilename)
		return True
	
	if type(lockfilename) == types.StringType and not os.path.exists(lockfilename):
		portage_util.writemsg("lockfile does not exist '%s'\n" % lockfilename,1)
		if (myfd != None) and type(lockfilename) == types.StringType:
			os.close(myfd)
		return False

	try:
		if myfd == None:
			myfd = os.open(lockfilename, os.O_WRONLY,0660)
			unlinkfile = 1
		locking_method(myfd,fcntl.LOCK_UN)
	except SystemExit, e:
		raise
	except Exception, e:
		if type(lockfilename) == types.StringType:
			os.close(myfd)
		raise IOError, "Failed to unlock file '%s'\n" % lockfilename

	try:
		# This sleep call was added to allow other processes that are
		# waiting for a lock to be able to grab it before it is deleted.
		# lockfile() already accounts for this situation, however, and
		# the sleep here adds more time than is saved overall, so am
		# commenting until it is proved necessary.
		#time.sleep(0.0001)
		if unlinkfile:
			locking_method(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
			# We won the lock, so there isn't competition for it.
			# We can safely delete the file.
			portage_util.writemsg("Got the lockfile...\n",1)
			#portage_util.writemsg("Unlinking...\n")
			os.unlink(lockfilename)
			portage_util.writemsg("Unlinked lockfile...\n",1)
			locking_method(myfd,fcntl.LOCK_UN)
	except SystemExit, e:
		raise
	except Exception, e:
		# We really don't care... Someone else has the lock.
		# So it is their problem now.
		portage_util.writemsg("Failed to get lock... someone took it.\n",1)
		portage_util.writemsg(str(e)+"\n",1)

	# why test lockfilename?  because we may have been handed an
	# fd originally, and the caller might not like having their
	# open fd closed automatically on them.
	if type(lockfilename) == types.StringType:
		os.close(myfd)

	return True




def hardlock_name(path):
	return path+".hardlock-"+os.uname()[1]+"-"+str(os.getpid())

def hardlink_active(lock):
	if not os.path.exists(lock):
		return False
 	# XXXXXXXXXXXXXXXXXXXXXXXXXX

def hardlink_is_mine(link,lock):
	try:
		myhls = os.stat(link)
		mylfs = os.stat(lock)
	except SystemExit, e:
		raise
	except:
		myhls = None
		mylfs = None

	if myhls:
		if myhls[stat.ST_NLINK] == 2:
			return True
		if mylfs:
			if mylfs[stat.ST_INO] == myhls[stat.ST_INO]:
				return True
	return False

def hardlink_lockfile(lockfilename, max_wait=14400):
	"""Does the NFS, hardlink shuffle to ensure locking on the disk.
	We create a PRIVATE lockfile, that is just a placeholder on the disk.
	Then we HARDLINK the real lockfile to that private file.
	If our file can 2 references, then we have the lock. :)
	Otherwise we lather, rise, and repeat.
	We default to a 4 hour timeout.
	"""
	
	add_hardlock_file_to_cleanup(lockfilename)
	
	start_time = time.time()
	myhardlock = hardlock_name(lockfilename)
	reported_waiting = False
	
	while(time.time() < (start_time + max_wait)):
		# We only need it to exist.
		myfd = os.open(myhardlock, os.O_CREAT|os.O_RDWR,0660)
		os.close(myfd)
	
		if not os.path.exists(myhardlock):
			raise portage_exception.FileNotFound, _("Created lockfile is missing: %(filename)s") % {"filename":myhardlock}

		try:
			res = os.link(myhardlock, lockfilename)
		except SystemExit, e:
			raise
		except Exception, e:
			#print "lockfile(): Hardlink: Link failed."
			#print "Exception: ",e
			pass

		if hardlink_is_mine(myhardlock, lockfilename):
			# We have the lock.
			if reported_waiting:
				print
			return True

		if reported_waiting:
			portage_util.writemsg(".")
		else:
			reported_waiting = True
			print
			print "Waiting on (hardlink) lockfile: (one '.' per 3 seconds)"
			print "This is a feature to prevent distfiles corruption."
			print "/usr/lib/portage/bin/clean_locks can fix stuck locks."
			print "Lockfile: " + lockfilename
		time.sleep(0.1)
	
	os.unlink(myhardlock)
	return False

def unhardlink_lockfile(lockfilename):
	myhardlock = hardlock_name(lockfilename)
	try:
		if os.path.exists(myhardlock):
			os.unlink(myhardlock)
		if os.path.exists(lockfilename):
			os.unlink(lockfilename)
	except SystemExit, e:
		raise
	except:
		portage_util.writemsg("Something strange happened to our hardlink locks.\n")

def hardlock_cleanup(path, remove_all_locks=False):
	mypid  = str(os.getpid())
	myhost = os.uname()[1]
	mydl = os.listdir(path)

	results = []
	mycount = 0

	mylist = {}
	for x in mydl:
		if os.path.isfile(path+"/"+x):
			parts = string.split(x, ".hardlock-")
			if len(parts) == 2:
				filename = parts[0]
				hostpid  = string.split(parts[1],"-")
				host  = string.join(hostpid[:-1], "-")
				pid   = hostpid[-1]
				
				if not mylist.has_key(filename):
					mylist[filename] = {}
				if not mylist[filename].has_key(host):
					mylist[filename][host] = []
				mylist[filename][host].append(pid)

				mycount += 1


	results.append("Found %(count)s locks" % {"count":mycount})
	
	for x in mylist.keys():
		if mylist[x].has_key(myhost) or remove_all_locks:
			mylockname = hardlock_name(path+"/"+x)
			if hardlink_is_mine(mylockname, path+"/"+x) or \
			   not os.path.exists(path+"/"+x) or \
				 remove_all_locks:
				for y in mylist[x].keys():
					for z in mylist[x][y]:
						filename = path+"/"+x+".hardlock-"+y+"-"+z
						if filename == mylockname:
							continue
						try:
							# We're sweeping through, unlinking everyone's locks.
							os.unlink(filename)
							results.append(_("Unlinked: ") + filename)
						except SystemExit, e:
							raise
						except Exception,e:
							pass
				try:
					os.unlink(path+"/"+x)
					results.append(_("Unlinked: ") + path+"/"+x)
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except SystemExit, e:
					raise
				except Exception,e:
					pass
			else:
				try:
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except SystemExit, e:
					raise
				except Exception,e:
					pass

	return results

