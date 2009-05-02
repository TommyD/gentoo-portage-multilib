# xpak/test_decodeint.py
# Copright Gentoo Foundation 2006
# Portage Unit Testing Functionality
# $Id: test_decodeint.py 12626 2009-02-18 22:50:14Z zmedico $

from portage.tests import TestCase
from portage.xpak import decodeint, encodeint

class testDecodeIntTestCase(TestCase):

	def testDecodeInt(self):
		
		for n in xrange(1000):
			self.assertEqual(decodeint(encodeint(n)), n)
