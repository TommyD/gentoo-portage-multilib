# portage: Lock management code
# Copyright 2004-2004 Gentoo Foundation
# Distributed under the GNU Public License v2
# $Header$

import errno
import os
import stat
import time
import types
import portage_exception
import portage_util
import portage_data

HARDLINK_FD = -2

def lockdir(mydir):
	return lockfile(mydir,wantnewlockfile=1)
def unlockdir(mylock):
	return unlockfile(mylock)

def lockfile(mypath,wantnewlockfile=0,unlinkfile=0):
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
			if os.stat(lockfilename).st_gid != portage_data.portage_gid:
				try:
					os.chown(lockfilename,os.getuid(),portage_data.portage_gid)
				except:
					portage.writemsg("Cannot chown a lockfile. This could cause inconvenience later.\n");
			os.umask(old_mask)
		else:
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR,0660)

	elif type(mypath) == types.IntType:
		myfd = mypath

	else:
		raise ValueError, "Unknown type passed in '%s': '%s'" % (type(mypath),mypath)

	# try for a non-blocking lock, if it's held, throw a message
	# we're waiting on lockfile and use a blocking attempt.
	try:
		fcntl.lockf(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
	except IOError, ie:
		# resource temp unavailable; eg, someone beat us to the lock.
		if ie.errno == errno.EAGAIN:
			if type(mypath) == types.IntType:
				print "waiting for lock on fd %i" % myfd
			else:
				print "waiting for lock on %s" % lockfilename
			# try for the exclusive lock now.
			fcntl.lockf(myfd,fcntl.LOCK_EX)
		else:
			raise ie

	except OSError, oe:
		# We're not allowed to lock on this FS.
		close(myfd)
		link_success = False
		if os.errno == errno.EPERM:
			if lockfilename == str(lockfilename):
				if wantnewlockfile:
					link_success = hardlink_lockfile(lockfilename)
		if not link_success:
			raise
		myfd = HARDLINK_FD

	if type(lockfilename) == types.StringType and not os.path.exists(lockfilename):
		# The file was deleted on us... Keep trying to make one...
		os.close(myfd)
		portage_util.writemsg("lockfile recurse\n",1)
		lockfilename,myfd,unlinkfile = lockfile(mypath,wantnewlockfile,unlinkfile)

	portage_util.writemsg(str((lockfilename,myfd,unlinkfile))+"\n",1)
	return (lockfilename,myfd,unlinkfile)

def unlockfile(mytuple):
	import fcntl

	lockfilename,myfd,unlinkfile = mytuple

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
		fcntl.lockf(myfd,fcntl.LOCK_UN)
	except Exception, e:
		if type(lockfilename) == types.StringType:
			os.close(myfd)
		raise IOError, "Failed to unlock file '%s'\n" % lockfilename

	try:
		# We add the very brief sleep here to force a preemption.
		# This reduces the likelihood of us deleting the file. XXXX
		time.sleep(0.0001)
		fcntl.lockf(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
		# We won the lock, so there isn't competition for it.
		# We can safely delete the file.
		portage_util.writemsg("Got the lockfile...\n",1)
		if unlinkfile:
			#portage_util.writemsg("Unlinking...\n")
			os.unlink(lockfilename)
			portage_util.writemsg("Unlinked lockfile...\n",1)
		fcntl.lockf(myfd,fcntl.LOCK_UN)
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









def hardlink_lockfile(lockfilename, max_wait=14400):
	"""Does the NFS, hardlink shuffle to ensure locking on the disk.
	We create a PRIVATE lockfile, that is just a placeholder on the disk.
	Then we HARDLINK the real lockfile to that private file.
	If our file can 2 references, then we have the lock. :)
	Otherwise we lather, rise, and repeat.
	We default to a 4 hour timeout.
	"""
	start_time = time.time()
	myhardlock = lockfilename+".hard_lockfile."+os.uname()[1]+"-"+str(os.getpid())
	reported_waiting = False
	
	print "Hardlink lockfile:",myhardlock
	
	while(time.time() < (start_time + max_wait)):
		# We only need it to exist.
		myfd = os.open(myhardlock, os.O_CREAT|os.O_RDWR,0660)
		os.close(myfd)
	
		if not os.path.exists(myhardlock):
			raise portage_exception.FileNotFound, _("Created lockfile is missing: %(filename)s") % {"filename":myhardlock}

		mystat = None
		try:
			os.link(myhardlock, lockfilename)
			mystat = os.stat(myhardlock)
		except:
			pass
	
		if mystat and (mystat[stat.ST_NLINK] == 2):
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
			print "   " + lockfilename
		time.sleep(3)
	
	os.unlink(myhardlock)
	return False

def unhardlink_lockfile(lockfilename):
	myhardlock = lockfilename+".hard_lockfile."+os.uname()[1]+"-"+str(os.getpid())
	try:
		if os.path.exists(lockfilename):
			os.unlink(lockfilename)
		if os.path.exists(myhardlock):
			os.unlink(myhardlock)
	except:
		portage_util.writemsg("Something strange happened to our hardlink locks.\n")
