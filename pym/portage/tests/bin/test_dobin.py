# test_dobin.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from setup_env import *

class DoBin(BinTestCase):
	def testDoBin(self):
		dobin("does-not-exist", 1)
		xexists_in_D("does-not-exist")
		xexists_in_D("/bin/does-not-exist")
		xexists_in_D("/usr/bin/does-not-exist")
