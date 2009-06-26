# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.AbstractDepPriority import AbstractDepPriority
class UnmergeDepPriority(AbstractDepPriority):
	__slots__ = ("optional", "satisfied",)
	"""
	Combination of properties           Priority  Category

	runtime                                0       HARD
	runtime_post                          -1       HARD
	buildtime                             -2       SOFT
	(none of the above)                   -2       SOFT
	"""

	MAX    =  0
	SOFT   = -2
	MIN    = -2

	def __int__(self):
		if self.runtime:
			return 0
		if self.runtime_post:
			return -1
		if self.buildtime:
			return -2
		return -2

	def __str__(self):
		myvalue = self.__int__()
		if myvalue > self.SOFT:
			return "hard"
		return "soft"

