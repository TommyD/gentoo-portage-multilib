# Copyright: 2005-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)
# $Id$

__all__ = ["Mapping", "MutableMapping", "UserDict", "ProtectedDict",
	"LazyLoad", "slot_dict_class"]

import sys
import warnings
import weakref

class Mapping(object):
	"""
	In python-3.0, the UserDict.DictMixin class has been replaced by
	Mapping and MutableMapping from the collections module, but 2to3
	doesn't currently account for this change:

	    http://bugs.python.org/issue2876

	As a workaround for the above issue, use this class as a substitute
	for UserDict.DictMixin so that code converted via 2to3 will run.
	"""

	def __iter__(self):
		return self.iterkeys()

	def keys(self):
		return list(self.__iter__())

	def has_key(self, key):
		warnings.warn("portage.cache.mappings.Mapping.has_key() " + \
			"is deprecated, use the in operator instead", DeprecationWarning)
		return key in self

	def __contains__(self, key):
		try:
			value = self[key]
		except KeyError:
			return False
		return True

	def iteritems(self):
		for k in self:
			yield (k, self[k])

	def iterkeys(self):
		return self.__iter__()

	def itervalues(self):
		for _, v in self.iteritems():
			yield v

	def values(self):
		return [v for _, v in self.iteritems()]

	def items(self):
		return list(self.iteritems())

	def get(self, key, default=None):
		try:
			return self[key]
		except KeyError:
			return default

	def __repr__(self):
		return repr(dict(self.iteritems()))

	def __len__(self):
		return len(self.keys())

	if sys.hexversion >= 0x3000000:
		items = iteritems
		keys = __iter__
		values = itervalues

class MutableMapping(Mapping):
	"""
	A mutable vesion of the Mapping class.
	"""

	def clear(self):
		for key in self.keys():
			del self[key]

	def setdefault(self, key, default=None):
		try:
			return self[key]
		except KeyError:
			self[key] = default
		return default

	def pop(self, key, *args):
		if len(args) > 1:
			raise TypeError("pop expected at most 2 arguments, got " + \
				repr(1 + len(args)))
		try:
			value = self[key]
		except KeyError:
			if args:
				return args[0]
			raise
		del self[key]
		return value

	def popitem(self):
		try:
			k, v = self.iteritems().next()
		except StopIteration:
			raise KeyError('container is empty')
		del self[k]
		return (k, v)

	def update(self, other=None, **kwargs):
		if other is None:
			pass
		elif hasattr(other, 'iteritems'):
			# Use getattr to avoid interference from 2to3.
			for k, v in getattr(other, 'iteritems')():
				self[k] = v
		elif hasattr(other, 'items'):
			# Use getattr to avoid interference from 2to3.
			for k, v in getattr(other, 'items')():
				self[k] = v
		elif hasattr(other, 'keys'):
			for k in other.keys():
				self[k] = other[k]
		else:
			for k, v in other:
				self[k] = v
		if kwargs:
			self.update(kwargs)

class UserDict(MutableMapping):
	"""
	Use this class as a substitute for UserDict.UserDict so that
	code converted via 2to3 will run:

	     http://bugs.python.org/issue2876
	"""

	def __init__(self, *args, **kwargs):

		if len(args) > 1:
			raise TypeError(
				"expected at most 1 positional argument, got " + \
				repr(len(args)))

		if args:
			self.update(args[0])

		if kwargs:
			self.update(kwargs)

	def __repr__(self):
		return repr(self.data)

	def __contains__(self, key):
		return key in self.data

	def __iter__(self):
		return iter(self.data)

	def __len__(self):
		return len(self.data)

	def __getitem__(self, key):
		return self.data[key]

	def __setitem__(self, key, item):
		self.data[key] = item

	def __delitem__(self, key):
		del self.data[key]

	def clear(self):
		self.data.clear()

	if sys.hexversion >= 0x3000000:
		keys = __iter__

class ProtectedDict(MutableMapping):
	"""
	given an initial dict, this wraps that dict storing changes in a secondary dict, protecting
	the underlying dict from changes
	"""
	__slots__=("orig","new","blacklist")

	def __init__(self, orig):
		self.orig = orig
		self.new = {}
		self.blacklist = {}


	def __setitem__(self, key, val):
		self.new[key] = val
		if key in self.blacklist:
			del self.blacklist[key]


	def __getitem__(self, key):
		if key in self.new:
			return self.new[key]
		if key in self.blacklist:
			raise KeyError(key)
		return self.orig[key]


	def __delitem__(self, key):
		if key in self.new:
			del self.new[key]
		elif key in self.orig:
			if key not in self.blacklist:
				self.blacklist[key] = True
				return
		raise KeyError(key)
			

	def __iter__(self):
		for k in self.new.iterkeys():
			yield k
		for k in self.orig.iterkeys():
			if k not in self.blacklist and k not in self.new:
				yield k

	def __contains__(self, key):
		return key in self.new or (key not in self.blacklist and key in self.orig)

	def has_key(self, key):
		warnings.warn("portage.cache.mapping.ProtectedDict.has_key() is"
			" deprecated, use the in operator instead",
			DeprecationWarning)
		return key in self

	if sys.hexversion >= 0x3000000:
		keys = __iter__

class LazyLoad(Mapping):
	"""
	Lazy loading of values for a dict
	"""
	__slots__=("pull", "d")

	def __init__(self, pull_items_func, initial_items=[]):
		self.d = {}
		for k, v in initial_items:
			self.d[k] = v
		self.pull = pull_items_func

	def __getitem__(self, key):
		if key in self.d:
			return self.d[key]
		elif self.pull != None:
			self.d.update(self.pull())
			self.pull = None
		return self.d[key]

	def __iter__(self):
		if self.pull is not None:
			self.d.update(self.pull())
			self.pull = None
		return iter(self.d)

	def has_key(self, key):
		warnings.warn("portage.cache.mappings.LazyLoad.has_key() is "
			"deprecated, use the in operator instead",
			DeprecationWarning)
		return key in self


	def __contains__(self, key):
		if key in self.d:
			return True
		elif self.pull != None:
			self.d.update(self.pull())
			self.pull = None
		return key in self.d

	if sys.hexversion >= 0x3000000:
		keys = __iter__

_slot_dict_classes = weakref.WeakValueDictionary()

def slot_dict_class(keys, prefix="_val_"):
	"""
	Generates mapping classes that behave similar to a dict but store values
	as object attributes that are allocated via __slots__. Instances of these
	objects have a smaller memory footprint than a normal dict object.

	@param keys: Fixed set of allowed keys
	@type keys: Iterable
	@param prefix: a prefix to use when mapping
		attribute names from keys
	@type prefix: String
	@rtype: SlotDict
	@returns: A class that constructs SlotDict instances
		having the specified keys.
	"""
	if isinstance(keys, frozenset):
		keys_set = keys
	else:
		keys_set = frozenset(keys)
	v = _slot_dict_classes.get((keys_set, prefix))
	if v is None:

		class SlotDict(object):

			allowed_keys = keys_set
			_prefix = prefix
			__slots__ = ("__weakref__",) + \
				tuple(prefix + k for k in allowed_keys)

			def __init__(self, *args, **kwargs):

				if len(args) > 1:
					raise TypeError(
						"expected at most 1 positional argument, got " + \
						repr(len(args)))

				if args:
					self.update(args[0])

				if kwargs:
					self.update(kwargs)

			def __iter__(self):
				for k, v in self.iteritems():
					yield k

			def __len__(self):
				l = 0
				for i in self.iteritems():
					l += 1
				return l

			def keys(self):
				return list(self)

			def iteritems(self):
				for k in self.allowed_keys:
					try:
						yield (k, getattr(self, self._prefix + k))
					except AttributeError:
						pass

			def items(self):
				return list(self.iteritems())

			def itervalues(self):
				for k, v in self.iteritems():
					yield v

			def values(self):
				return list(self.itervalues())

			def __delitem__(self, k):
				try:
					delattr(self, self._prefix + k)
				except AttributeError:
					raise KeyError(k)

			def __setitem__(self, k, v):
				setattr(self, self._prefix + k, v)

			def setdefault(self, key, default=None):
				try:
					return self[key]
				except KeyError:
					self[key] = default
				return default

			def update(self, other=None, **kwargs):
				if other is None:
					pass
				elif hasattr(other, 'iteritems'):
					# Use getattr to avoid interference from 2to3.
					for k, v in getattr(other, 'iteritems')():
						self[k] = v
				elif hasattr(other, 'items'):
					# Use getattr to avoid interference from 2to3.
					for k, v in getattr(other, 'items')():
						self[k] = v
				elif hasattr(other, 'keys'):
					for k in other.keys():
						self[k] = other[k]
				else:
					for k, v in other:
						self[k] = v
				if kwargs:
					self.update(kwargs)

			def __getitem__(self, k):
				try:
					return getattr(self, self._prefix + k)
				except AttributeError:
					raise KeyError(k)

			def get(self, key, default=None):
				try:
					return self[key]
				except KeyError:
					return default

			def __contains__(self, k):
				return hasattr(self, self._prefix + k)

			def has_key(self, k):
				warnings.warn("portage.cache.mappings.SlotDict.has_key()" + \
					" is deprecated, use the in operator instead",
					DeprecationWarning)
				return k in self

			def pop(self, key, *args):
				if len(args) > 1:
					raise TypeError(
						"pop expected at most 2 arguments, got " + \
						repr(1 + len(args)))
				try:
					value = self[key]
				except KeyError:
					if args:
						return args[0]
					raise
				del self[key]
				return value

			def popitem(self):
				try:
					k, v = self.iteritems().next()
				except StopIteration:
					raise KeyError('container is empty')
				del self[k]
				return (k, v)

			def copy(self):
				c = self.__class__()
				c.update(self)
				return c

			def clear(self):
				for k in self.allowed_keys:
					try:
						delattr(self, self._prefix + k)
					except AttributeError:
						pass

			def __str__(self):
				return str(dict(self.iteritems()))

			if sys.hexversion >= 0x3000000:
				items = iteritems
				keys = __iter__
				values = itervalues

		v = SlotDict
		_slot_dict_classes[v.allowed_keys] = v
	return v
