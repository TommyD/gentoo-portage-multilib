# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import copy
from _emerge.SlotObject import SlotObject

class AbstractDepPriority(SlotObject):
	__slots__ = ("buildtime", "runtime", "runtime_post")

	def __lt__(self, other):
		return self.__int__() < other

	def __le__(self, other):
		return self.__int__() <= other

	def __eq__(self, other):
		return self.__int__() == other

	def __ne__(self, other):
		return self.__int__() != other

	def __gt__(self, other):
		return self.__int__() > other

	def __ge__(self, other):
		return self.__int__() >= other

	def copy(self):
		return copy.copy(self)
