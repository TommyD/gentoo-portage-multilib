# portage_gpg.py -- core Portage functionality
# Copyright 2004-2004 Gentoo Foundation
# Distributed under the GNU Public License v2
# $Header$

import os
import commands
import portage_exception

GPG_BINARY       = "/usr/bin/gpg"
GPG_VERIFY_FLAGS = " --verify -vvv "
GPG_KEYDIR       = " --keydir  '%s' "
GPG_KEYRING      = " --keyring '%s' "

TRUSTED   = 3
MARGINAL  = 2
EXISTS    = 1
UNTRUSTED = 0

def verifyTrusted(filename, keydir=None, keyring=None):
	if verify_gpg(filename,keydir,keyring) == TRUSTED:
		return True
	else:
		return False

def verify(filename, keydir=None, keyring=None):
	"""0 == failed, 1 == key in ring, 2 == key is trusted"""

	if not os.path.isfile(filename):
		raise portage_exception.FileNotFound, filename
	
	if keydir and not os.path.isdir(keydir):
		raise portage_exception.DirectoryNotFound, filename
	
	if keydir and keyring and not os.path.isfile(keydir+"/"+keyring):
		raise portage_exception.FileNotFound, keydir+"/"+keyring

	if not os.path.isfile(filename):
		raise portage_exception.CommandNotFound, filename


	command = GPG_BINARY + GPG_VERIFY_FLAGS
	if keydir:
		command += GPG_KEYDIR % (keydir)
	if keyring:
		command += GPG_KEYRING % (keyring)
	
	command += " '"+filename+"'"

	result,output = commands.getstatusoutput(command)
	
	signal = result & 0xff
	result = (result >> 8)

	if signal:
		raise SignalCaught, "Signal: %d" % (signal)

	if result == 0:
		if output.find("WARNING") != -1:
			return PARTIAL
		return TRUSTED
	elif result == 1:
		return EXISTS
	elif result == 2:
		return FAILED
	else:
		raise UnknownCondition, "GPG returned unknown result: %d" % (result)

