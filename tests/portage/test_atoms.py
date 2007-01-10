# test_vercmp.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from unittest import TestCase
from portage_versions import vercmp

class VerCmpTestCase(TestCase):
	""" A simple testCase for portage_versions.vercmp()
	"""
	
	def testVerCmpGreater(self):
		
		tests = [ ( "6.0", "5.0"), ("5.0","5")]
		for test in tests:
			self.failIf( vercmp( test[0], test[1] ) <= 0, msg="%s < %s? Wrong!" % (test[0],test[1]) )

	def testVerCmpLess(self):
		"""
		pre < alpha < beta < rc < p -> test each of these, they are inductive (or should be..)
		"""
		tests = [ ( "4.0", "5.0"), ("5", "5.0"), ("1.0_pre2","1.0_p2"),
			("1.0_alpha2", "1.0_p2"),("1.0_alpha1", "1.0_beta1"),("1.0_beta3","1.0_rc3")]
		for test in tests:
			self.failIf( vercmp( test[0], test[1]) >= 0, msg="%s > %s? Wrong!" % (test[0],test[1]))
	
	
	def testVerCmpEqual(self):
		
		tests = [ ("4.0", "4.0") ]
		for test in tests:
			self.failIf( vercmp( test[0], test[1]) != 0, msg="%s != %s? Wrong!" % (test[0],test[1]))
			
	def testVerNotEqual(self):
		
		tests = [ ("1","2"),("1.0_alpha","1.0_pre"),("1.0_beta","1.0_alpha"),
			("0", "0.0")]
		for test in tests:
			self.failIf( vercmp( test[0], test[1]) == 0, msg="%s == %s? Wrong!" % (test[0],test[1]))
