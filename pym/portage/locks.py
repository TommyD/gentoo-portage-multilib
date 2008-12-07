# portage: Lock management code
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ["lockdir", "unlockdir", "lockfile", "unlockfile", \
	"hardlock_name", "hardlink_is_mine", "hardlink_lockfile", \
	"unhardlink_lockfile", "hardlock_cleanup"]

import errno, os, stat, time, types
from portage.exception import DirectoryNotFound, FileNotFound, \
	InvalidData, TryAgain
from portage.data import portage_gid
from portage.util import writemsg
from portage.localization import _

HARDLINK_FD = -2

# Used by emerge in order to disable the "waiting for lock" message
# so that it doesn't interfere with the status display.
_quiet = False

def lockdir(mydir):
	return lockfile(mydir,wantnewlockfile=1)
def unlockdir(mylock):
	return unlockfile(mylock)

def lockfile(mypath, wantnewlockfile=0, unlinkfile=0,
	waiting_msg=None, flags=0):
	"""Creates all dirs upto, the given dir. Creates a lockfile
	for the given directory as the file: directoryname+'.portage_lockfile'."""
	import fcntl

	if not mypath:
		raise InvalidData("Empty path given")

	if type(mypath) == types.StringType and mypath[-1] == '/':
		mypath = mypath[:-1]

	if type(mypath) == types.FileType:
		mypath = mypath.fileno()
	if type(mypath) == types.IntType:
		lockfilename    = mypath
		wantnewlockfile = 0
		unlinkfile      = 0
	elif wantnewlockfile:
		base, tail = os.path.split(mypath)
		lockfilename = os.path.join(base, "." + tail + ".portage_lockfile")
		del base, tail
		unlinkfile   = 1
	else:
		lockfilename = mypath
	
	if type(mypath) == types.StringType:
		if not os.path.exists(os.path.dirname(mypath)):
			raise DirectoryNotFound(os.path.dirname(mypath))
		if not os.path.exists(lockfilename):
			old_mask=os.umask(000)
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR,0660)
			try:
				if os.stat(lockfilename).st_gid != portage_gid:
					os.chown(lockfilename,os.getuid(),portage_gid)
			except OSError, e:
				if e[0] == 2: # No such file or directory
					return lockfile(mypath, wantnewlockfile=wantnewlockfile,
						unlinkfile=unlinkfile, waiting_msg=waiting_msg,
						flags=flags)
				else:
					writemsg("Cannot chown a lockfile. This could cause inconvenience later.\n");
			os.umask(old_mask)
		else:
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR,0660)

	elif type(mypath) == types.IntType:
		myfd = mypath

	else:
		raise ValueError("Unknown type passed in '%s': '%s'" % \
			(type(mypath), mypath))

	# try for a non-blocking lock, if it's held, throw a message
	# we're waiting on lockfile and use a blocking attempt.
	locking_method = fcntl.lockf
	try:
		fcntl.lockf(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
	except IOError, e:
		if "errno" not in dir(e):
			raise
		if e.errno in (errno.EACCES, errno.EAGAIN):
			# resource temp unavailable; eg, someone beat us to the lock.
			if flags & os.O_NONBLOCK:
				raise TryAgain(mypath)

			global _quiet
			if _quiet:
				pass
			elif waiting_msg is None:
				if isinstance(mypath, int):
					writemsg("waiting for lock on fd %i\n" % myfd,
						noiselevel=-1)
				else:
					writemsg("waiting for lock on %s\n" % lockfilename,
						noiselevel=-1)
			elif waiting_msg:
				writemsg(waiting_msg + "\n", noiselevel=-1)
			# try for the exclusive lock now.
			fcntl.lockf(myfd,fcntl.LOCK_EX)
		elif e.errno == errno.ENOLCK:
			# We're not allowed to lock on this FS.
			os.close(myfd)
			link_success = False
			if lockfilename == str(lockfilename):
				if wantnewlockfile:
					try:
						if os.stat(lockfilename)[stat.ST_NLINK] == 1:
							os.unlink(lockfilename)
					except OSError:
						pass
					link_success = hardlink_lockfile(lockfilename)
			if not link_success:
				raise
			locking_method = None
			myfd = HARDLINK_FD
		else:
			raise

		
	if type(lockfilename) == types.StringType and \
		myfd != HARDLINK_FD and _fstat_nlink(myfd) == 0:
		# The file was deleted on us... Keep trying to make one...
		os.close(myfd)
		writemsg("lockfile recurse\n",1)
		lockfilename, myfd, unlinkfile, locking_method = lockfile(
			mypath, wantnewlockfile=wantnewlockfile, unlinkfile=unlinkfile,
			waiting_msg=waiting_msg, flags=flags)

	writemsg(str((lockfilename,myfd,unlinkfile))+"\n",1)
	return (lockfilename,myfd,unlinkfile,locking_method)

def _fstat_nlink(fd):
	"""
	@param fd: an open file descriptor
	@type fd: Integer
	@rtype: Integer
	@return: the current number of hardlinks to the file
	"""
	try:
		return os.fstat(fd).st_nlink
	except EnvironmentError, e:
		if e.errno == errno.ENOENT:
			# Some filesystems such as CIFS return
			# ENOENT which means st_nlink == 0.
			return 0
		raise

def unlockfile(mytuple):
	import fcntl

	#XXX: Compatability hack.
	if len(mytuple) == 3:
		lockfilename,myfd,unlinkfile = mytuple
		locking_method = fcntl.flock
	elif len(mytuple) == 4:
		lockfilename,myfd,unlinkfile,locking_method = mytuple
	else:
		raise InvalidData

	if(myfd == HARDLINK_FD):
		unhardlink_lockfile(lockfilename)
		return True
	
	# myfd may be None here due to myfd = mypath in lockfile()
	if type(lockfilename) == types.StringType and not os.path.exists(lockfilename):
		writemsg("lockfile does not exist '%s'\n" % lockfilename,1)
		if myfd is not None:
			os.close(myfd)
		return False

	try:
		if myfd is None:
			myfd = os.open(lockfilename, os.O_WRONLY,0660)
			unlinkfile = 1
		locking_method(myfd,fcntl.LOCK_UN)
	except OSError:
		if type(lockfilename) == types.StringType:
			os.close(myfd)
		raise IOError("Failed to unlock file '%s'\n" % lockfilename)

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
			writemsg("Got the lockfile...\n",1)
			if _fstat_nlink(myfd) == 1:
				os.unlink(lockfilename)
				writemsg("Unlinked lockfile...\n",1)
				locking_method(myfd,fcntl.LOCK_UN)
			else:
				writemsg("lockfile does not exist '%s'\n" % lockfilename,1)
				os.close(myfd)
				return False
	except Exception, e:
		writemsg("Failed to get lock... someone took it.\n",1)
		writemsg(str(e)+"\n",1)

	# why test lockfilename?  because we may have been handed an
	# fd originally, and the caller might not like having their
	# open fd closed automatically on them.
	if type(lockfilename) == types.StringType:
		os.close(myfd)

	return True




def hardlock_name(path):
	return path+".hardlock-"+os.uname()[1]+"-"+str(os.getpid())

def hardlink_is_mine(link,lock):
	try:
		return os.stat(link).st_nlink == 2
	except OSError:
		return False

def hardlink_lockfile(lockfilename, max_wait=14400):
	"""Does the NFS, hardlink shuffle to ensure locking on the disk.
	We create a PRIVATE lockfile, that is just a placeholder on the disk.
	Then we HARDLINK the real lockfile to that private file.
	If our file can 2 references, then we have the lock. :)
	Otherwise we lather, rise, and repeat.
	We default to a 4 hour timeout.
	"""

	start_time = time.time()
	myhardlock = hardlock_name(lockfilename)
	reported_waiting = False
	
	while(time.time() < (start_time + max_wait)):
		# We only need it to exist.
		myfd = os.open(myhardlock, os.O_CREAT|os.O_RDWR,0660)
		os.close(myfd)
	
		if not os.path.exists(myhardlock):
			raise FileNotFound(
				_("Created lockfile is missing: %(filename)s") % \
				{"filename" : myhardlock})

		try:
			res = os.link(myhardlock, lockfilename)
		except OSError:
			pass

		if hardlink_is_mine(myhardlock, lockfilename):
			# We have the lock.
			if reported_waiting:
				writemsg("\n", noiselevel=-1)
			return True

		if reported_waiting:
			writemsg(".", noiselevel=-1)
		else:
			reported_waiting = True
			from portage.const import PORTAGE_BIN_PATH
			msg = "\nWaiting on (hardlink) lockfile:" + \
				" (one '.' per 3 seconds)\n" + \
				"%s/clean_locks can fix stuck locks.\n" % PORTAGE_BIN_PATH + \
				"Lockfile: %s\n" % lockfilename
			writemsg(msg, noiselevel=-1)
		time.sleep(3)
	
	os.unlink(myhardlock)
	return False

def unhardlink_lockfile(lockfilename):
	myhardlock = hardlock_name(lockfilename)
	if hardlink_is_mine(myhardlock, lockfilename):
		# Make sure not to touch lockfilename unless we really have a lock.
		try:
			os.unlink(lockfilename)
		except OSError:
			pass
	try:
		os.unlink(myhardlock)
	except OSError:
		pass

def hardlock_cleanup(path, remove_all_locks=False):
	mypid  = str(os.getpid())
	myhost = os.uname()[1]
	mydl = os.listdir(path)

	results = []
	mycount = 0

	mylist = {}
	for x in mydl:
		if os.path.isfile(path+"/"+x):
			parts = x.split(".hardlock-")
			if len(parts) == 2:
				filename = parts[0]
				hostpid  = parts[1].split("-")
				host  = "-".join(hostpid[:-1])
				pid   = hostpid[-1]
				
				if filename not in mylist:
					mylist[filename] = {}
				if host not in mylist[filename]:
					mylist[filename][host] = []
				mylist[filename][host].append(pid)

				mycount += 1


	results.append("Found %(count)s locks" % {"count":mycount})
	
	for x in mylist:
		if myhost in mylist[x] or remove_all_locks:
			mylockname = hardlock_name(path+"/"+x)
			if hardlink_is_mine(mylockname, path+"/"+x) or \
			   not os.path.exists(path+"/"+x) or \
				 remove_all_locks:
				for y in mylist[x]:
					for z in mylist[x][y]:
						filename = path+"/"+x+".hardlock-"+y+"-"+z
						if filename == mylockname:
							continue
						try:
							# We're sweeping through, unlinking everyone's locks.
							os.unlink(filename)
							results.append(_("Unlinked: ") + filename)
						except OSError:
							pass
				try:
					os.unlink(path+"/"+x)
					results.append(_("Unlinked: ") + path+"/"+x)
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except OSError:
					pass
			else:
				try:
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except OSError:
					pass

	return results

