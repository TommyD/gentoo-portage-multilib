# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
# ~harring
class domain:
	def __init__(self, use, distdir, features):
		self.__master = config

	def load_all_repositories(self):
		
