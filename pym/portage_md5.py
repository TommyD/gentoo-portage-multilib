# portage.py -- core Portage functionality
# Copyright 1998-2003 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2
# $Header$

from portage_const import PRIVATE_PATH,PRELINK_BINARY
import os
import shutil
import portage_util
import commands

prelink_capable = False
results = commands.getstatusoutput(PRELINK_BINARY+" --version > /dev/null 2>&1")
if (results[0] >> 8) == 0:
  prelink_capable=1
del results

# We _try_ to load this module. If it fails we do the slow fallback.
try:
	import fchksum
	
	def perform_checksum(filename, calc_prelink=False):
		prelink_tmpfile = PRIVATE_PATH+"/prelink-checksum.tmp"
		if calc_prelink and prelink_capable:
			# Create non-prelinked temporary file to md5sum.
			mylock = lockfile(prelink_tmpfile, wantnewlockfile=1)
			try:
				shutil.copy2(filename,prelink_tmpfile)
			except Exception,e:
				writemsg("!!! Unable to copy file '"+str(filename)+"'.\n")
				writemsg("!!! "+str(e)+"\n")
				sys.exit(1)
			spawn(PRELINK_BINARY+" --undo "+prelink_tmpfile+" &>/dev/null", settings, free=1)
			retval = fchksum.fmd5t(prelink_tmpfile)
			os.unlink(prelink_tmpfile)
			unlockfile(mylock)
			return retval
		else:
			return fchksum.fmd5t(filename)
except ImportError:
	import md5
	def perform_checksum(filename, calc_prelink=prelink_capable):
		prelink_tmpfile = PRIVATE_PATH+"/prelink-checksum.tmp"
		mylock = lockfile(prelink_tmpfile, wantnewlockfile=1)
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
			spawn(PRELINK_BINARY+" --undo "+prelink_tmpfile+" &>/dev/null", settings, free=1)
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
