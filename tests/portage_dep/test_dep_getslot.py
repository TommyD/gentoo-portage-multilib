# test_dep_getslot.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_atoms.py 5525 2007-01-10 13:35:03Z antarus $

from unittest import TestCase
from portage_dep import dep_getslot

class DepGetSlot(TestCase):
        """ A simple testcase for isvalidatom
        """

        def testDepGetSlot(self):
		
		slot_char = ":"
		slots = ( "a", "1.2", "1", "IloveVapier", None )
		cpvs = ["sys-apps/portage"]

		for cpv in cpvs:
			for slot in slots:
				if slot:
					self.assertEqual( dep_getslot( 
						 cpv + slot_char + slot ), slot )
				else:
					self.assertEqual( dep_getslot( cpv ), slot )

		self.assertEqual( dep_getslot( "sys-apps/portage:"), "" )
