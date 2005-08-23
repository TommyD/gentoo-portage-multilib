# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$


class domain:
	def __init__(self, config):
		self.__master = config

	def load_all_repositories(self):
		
