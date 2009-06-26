# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SlotObject import SlotObject
class Task(SlotObject):
	__slots__ = ("_hash_key", "_hash_value")

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			raise NotImplementedError(self)
		return hash_key

	def __eq__(self, other):
		return self._get_hash_key() == other

	def __ne__(self, other):
		return self._get_hash_key() != other

	def __hash__(self):
		hash_value = getattr(self, "_hash_value", None)
		if hash_value is None:
			self._hash_value = hash(self._get_hash_key())
		return self._hash_value

	def __len__(self):
		return len(self._get_hash_key())

	def __getitem__(self, key):
		return self._get_hash_key()[key]

	def __iter__(self):
		return iter(self._get_hash_key())

	def __contains__(self, key):
		return key in self._get_hash_key()

	def __str__(self):
		return str(self._get_hash_key())

