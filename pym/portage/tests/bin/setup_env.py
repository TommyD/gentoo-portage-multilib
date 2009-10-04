# setup_env.py -- Make sure bin subdir has sane env for testing
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import tempfile

from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.process import spawn

basepath = os.path.join(os.path.dirname(os.path.dirname(
	os.path.abspath(__file__))),
	"..", "..", "..")
bindir = os.path.join(basepath, "bin")
pymdir = os.path.join(basepath, "pym")
basedir = None
env = None

def binTestsCleanup():
	global basedir
	if basedir is None:
		return
	if os.access(basedir, os.W_OK):
		shutil.rmtree(basedir)
		basedir = None

def binTestsInit():
	binTestsCleanup()
	global basedir, env
	basedir = tempfile.mkdtemp()
	env = os.environ.copy()
	env["D"] = os.path.join(basedir, "image")
	env["T"] = os.path.join(basedir, "temp")
	env["S"] = os.path.join(basedir, "workdir")
	env["PF"] = "portage-tests-0.09-r1"
	env["PATH"] = bindir + ":" + env["PATH"]
	env["PORTAGE_BIN_PATH"] = bindir
	env["PORTAGE_PYM_PATH"] = pymdir
	os.mkdir(env["D"])
	os.mkdir(env["T"])
	os.mkdir(env["S"])
	os.chdir(env["S"])

class BinTestCase(TestCase):
	def __init__(self, methodName):
		TestCase.__init__(self, methodName)
		binTestsInit()
	def __del__(self):
		binTestsCleanup()
		if hasattr(TestCase, "__del__"):
			TestCase.__del__(self)

def _exists_in_D(path):
	# Note: do not use os.path.join() here, we assume D to end in /
	return os.access(env["D"] + path, os.W_OK)
def exists_in_D(path):
	if not _exists_in_D(path):
		raise TestCase.failureException
def xexists_in_D(path):
	if _exists_in_D(path):
		raise TestCase.failureException

def portage_func(func, args, exit_status=0):
	# we don't care about the output of the programs,
	# just their exit value and the state of $D
	global env
	f = open('/dev/null', 'wb')
	fd_pipes = {0:0,1:f.fileno(),2:f.fileno()}
	spawn([func] + args.split(), env=env, fd_pipes=fd_pipes)
	f.close()

def create_portage_wrapper(bin):
	def derived_func(*args):
		newargs = list(args)
		newargs.insert(0, bin)
		return portage_func(*newargs)
	return derived_func

for bin in os.listdir(os.path.join(bindir, "ebuild-helpers")):
	if bin.startswith("do") or \
	   bin.startswith("new") or \
	   bin.startswith("prep") or \
	   bin in ["ecompress","ecompressdir","fowners","fperms"]:
		globals()[bin] = create_portage_wrapper(
			os.path.join(bindir, "ebuild-helpers", bin))
