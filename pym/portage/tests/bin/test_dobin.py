# test_dobin.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dobin.py 13062 2009-03-12 00:25:50Z zmedico $

from portage.tests.bin.setup_env import *

class DoBin(BinTestCase):
	def testDoBin(self):
		dobin("does-not-exist", 1)
		xexists_in_D("does-not-exist")
		xexists_in_D("/bin/does-not-exist")
		xexists_in_D("/usr/bin/does-not-exist")
