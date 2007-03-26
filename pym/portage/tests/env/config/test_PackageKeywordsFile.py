# test_PackageKeywordsFile.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_PackageKeywordsFile.py 6182 2007-03-06 07:35:22Z antarus $

from portage.tests import TestCase
from portage.env.config import PackageKeywordsFile
from tempfile import mkstemp
import os

class PackageKeywordsFileTestCase(TestCase):

	cpv = 'sys-apps/portage'
	keywords = ['~x86', 'amd64', '-mips']
	
	def testPackageKeywordsFile(self):
		"""
		A simple test to ensure the load works properly
		"""

		self.BuildFile()
		try:
			f = PackageKeywordsFile(self.fname)
			f.load()
			for cpv, keyword in f.iteritems():
				self.assertEqual( cpv, self.cpv )
				[k for k in keyword if self.assertTrue(k in self.keywords)]
		finally:
			self.NukeFile()
	
	def BuildFile(self):
		fd, self.fname = mkstemp()
		f = os.fdopen(fd, 'w')
		f.write("\n".join(self.atoms))
		f.close()

	def NukeFile(self):
		import os
		os.unlink(self.fname)
