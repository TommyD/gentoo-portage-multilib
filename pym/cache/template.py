import cache_errors

class database(object):
	# XXX questionable on storing the auxdbkeys
	def __init__(self, label, auxdbkeys, readonly=False, **config):
		""" initialize the derived class; specifically, store label/keys"""
		self._known_keys = auxdbkeys
		self.label = label
		self.readonly = readonly

	
	def __getitem__(self, cpv):
		"""get cpv's values.
		override this in derived classess"""
		raise NotImplementedError


	def __setitem__(self, cpv, values):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		self._setitem(cpv, values)
			

	def _setitem(self, name, values):
		"""__setitem__ calls this after readonly checks.  override it in derived classes"""
		raise NotImplementedError


	def __delitem__(self, cpv):
		"""delete a key from the cache.
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		self._delitem(cpv)


	def _delitem(self,cpv):
		"""__delitem__ calls this after readonly checks.  override it in derived classes"""
		raise NotImplementedError


	def has_key(self, cpv):
		raise NotImplementedError


	def keys(self):
		raise NotImplementedError


	def get_matches(self, match_dict):
		"""generic function for walking the entire cache db, matching restrictions to
		filter what cpv's are returned.  Derived classes should override this if they
		can implement a faster method then pulling each cpv:values, and checking it.
		
		For example, RDBMS derived classes should push the matching logic down to the
		actual RDBM."""

		import re
		restricts = {}
		for key,match in match_dict.iteritems():
			# XXX this sucks.
			try:
				if isinstance(match, str):
					restricts[key] = re.compile(match).match
				else:
					restricts[key] = re.compile(match[0],match[1]).match
			except re.error, e:
				raise InvalidRestriction(key, match, e)
			if key not in self.__known_keys:
				raise InvalidRestriction(key, match, "Key isn't valid")

		for cpv in self.keys():
			cont = True
			vals = self[cpv]
			for key, match in restricts.iteritems():
				if not match(vals[key]):
					cont = False
					break
			if cont:
#				yield cpv,vals
				yield cpv

