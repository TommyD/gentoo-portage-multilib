# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

class IndexableSequence(object):
	def __init__(self, get_keys, get_values, recursive=False, returnEmpty=False, 
			returnIterFunc=None, modifiable=False, delfunc=None, updatefunc=None):
		self.__get_keys = get_keys
		self.__get_values = get_values
		self.__cache = {}
		self.__cache_complete = False
		self.__cache_can_be_complete = not recursive and not modifiable
		self.__return_empty = returnEmpty
		self.__returnFunc = returnIterFunc
		self._frozen = not modifiable
		if not self._frozen:
			self.__del_func = delfunc
			self.__update_func = updatefunc

	def __getitem__(self, key):
		if not (self.__cache_complete or self.__cache.has_key(key)):
			self.__cache[key] = self.__get_values(key)
		return self.__cache[key]

	def keys(self):
		return list(self.iterkeys())
	
	def __delitem__(self, key):
		if self._frozen:
			raise AttributeError
		if not key in self:
			raise KeyError(key)
		return self.__del_func(key)

	def __setitem__(self, key, value):
		if self._frozen:
			raise AttributeError
		if not key in self:
			raise KeyError(key)
		return self.__update_func(key, value)

	def __contains__(self, key):
		try:	
			self[key]
			return True
		except KeyError:
			return False

	def iterkeys(self):
#		print "iterkeys called, cache-complete=",self.__cache_complete
		if self.__cache_complete:
			return self.__cache.keys()
		return self.__gen_keys()

	def __gen_keys(self):
		for key in self.__get_keys():
			if not self.__cache.has_key(key):
				self.__cache[key] = self.__get_values(key)
#				print "adding %s:%s" % (str(key), str(self.__cache[key]))
			yield key
		self.__cache_complete = self.__cache_can_be_complete
		return

	def __iter__(self):
		if self.__returnFunc:
			for key, value in self.iteritems():
				if len(value) == 0:
					if self.__return_empty:
						yield key
				else:
					for x in value:
						yield self.__returnFunc(key, x)
		else:
			for key, value in self.iteritems():
				if len(value) == 0:
					if self.__return_empty:
						yield key
				else:
					for x in value:
						yield key+'/'+x
		return

	def items(self):
		return list(self.iteritems())
	
	def iteritems(self):
#		print "iteritems called, cache-complete=",self.__cache_complete
		if self.__cache_complete:
			return self.__cache.items()
		return self.__gen_items()

	def __gen_items(self):
		for key in self.iterkeys():
			yield key, self[key]
		return

