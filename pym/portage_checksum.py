# portage_checksum.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the GNU Public License v2
# $Header$

from portage_const import PRIVATE_PATH,PRELINK_BINARY
import os
import shutil
import portage_exec
import portage_util
import portage_locks
import commands
import sha

prelink_capable = False
results = commands.getstatusoutput(PRELINK_BINARY+" --version > /dev/null 2>&1")
if (results[0] >> 8) == 0:
  prelink_capable=1
del results

def perform_md5(x, calc_prelink=0):
	return perform_checksum(x, md5hash, calc_prelink)[0]

def perform_sha1(x, calc_prelink=0):
	return perform_checksum(x, sha1hash, calc_prelink)[0]

# We _try_ to load this module. If it fails we do the slow fallback.
try:
	import fchksum
	
	def md5hash(filename):
		return fchksum.fmd5t(filename)

except ImportError:
	import md5
	def md5hash(filename):
		f = open(filename, 'rb')
		blocksize=32768
		data = f.read(blocksize)
		size = 0L
		sum = md5.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		return (sum.hexdigest(),size)

def sha1hash(filename):
	f = open(filename, 'rb')
	blocksize=32768
	data = f.read(blocksize)
	size = 0L
	sum = sha.new()
	while data:
		sum.update(data)
		size = size + len(data)
		data = f.read(blocksize)
	f.close()

	return (sum.hexdigest(),size)

def perform_checksum(filename, hash_function=md5hash, calc_prelink=0):
	myfilename      = filename[:]
	prelink_tmpfile = PRIVATE_PATH+"/prelink-checksum.tmp"
	mylock          = None
	
	if calc_prelink and prelink_capable:
		mylock = portage_locks.lockfile(prelink_tmpfile, wantnewlockfile=1)
		# Create non-prelinked temporary file to md5sum.
		# Raw data is returned on stdout, errors on stderr.
		# Non-prelinks are just returned.
		try:
			shutil.copy2(filename,prelink_tmpfile)
		except Exception,e:
			writemsg("!!! Unable to copy file '"+str(filename)+"'.\n")
			writemsg("!!! "+str(e)+"\n")
			sys.exit(1)
		portage_exec.spawn(PRELINK_BINARY+" --undo "+prelink_tmpfile+" &>/dev/null", free=1)
		myfilename=prelink_tmpfile

	myhash, mysize = hash_function(myfilename)

	if calc_prelink and prelink_capable:
		os.unlink(prelink_tmpfile)
		portage_locks.unlockfile(mylock)

	return (myhash,mysize)
