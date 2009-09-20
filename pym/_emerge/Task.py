# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SlotObject import SlotObject
class Task(SlotObject):
	__slots__ = ("_hash_key", "_hash_value")

	def _get_hash_key(self):
		try:
			return self._hash_key
		except AttributeError:
			raise NotImplementedError(self)

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
		"""
		Emulate tuple.__repr__, but don't show 'foo' as u'foo' for unicode
		strings.
		"""
		return "(%s)" % ", ".join(("'%s'" % x for x in self._get_hash_key()))
