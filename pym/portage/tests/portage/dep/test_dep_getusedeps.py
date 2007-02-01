# test_dep_getusedeps.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dep_getslot.py 5794 2007-01-27 18:16:08Z antarus $

from unittest import TestCase
from portage.dep import dep_getusedeps

import sys
from portage.tests import test_cpvs, test_slots, test_versions, test_usedeps

class DepGetUseDeps(TestCase):
	""" A simple testcase for dep_getusedeps
	"""

	def testDepGetUseDeps(self):


		for mycpv in test_cpvs:
			for version in test_versions:
				for slot in test_slots:
					for use in test_usedeps:
						cpv = mycpv[:]
						if version:
							cpv += version
						if slot:
							cpv += ":" + slot
						if isinstance( use, list ):
							for u in use:
								cpv = cpv + "[" + u + "]"
							self.assertEqual( dep_getusedeps(
								cpv ), use )
						else:
							if len(use):
								self.assertEqual( dep_getusedeps(
									cpv + "[" + use + "]" ), [use] )
							else:
								self.assertEqual( dep_getusedeps(
									cpv + "[" + use + "]" ), [] )
