# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

try:
	anydbm_module = __import__("anydbm")
except ImportError:
	# python 3.x
	import dbm as anydbm_module
try:
	import cPickle as pickle
except ImportError:
	import pickle
from portage import _unicode_encode
from portage import os
import sys
from portage.cache import fs_template
from portage.cache import cache_errors


class database(fs_template.FsBased):

	autocommits = True
	cleanse_keys = True
	serialize_eclasses = False

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)

		default_db = config.get("dbtype","anydbm")
		if not default_db.startswith("."):
			default_db = '.' + default_db

		self._db_path = os.path.join(self.location, fs_template.gen_label(self.location, self.label)+default_db)
		self.__db = None
		try:
			# dbm.open() will not work with bytes in python-3.1:
			#   TypeError: can't concat bytes to str
			self.__db = anydbm_module.open(self._db_path,
				'w', self._perms)
		except anydbm_module.error:
			# XXX handle this at some point
			try:
				self._ensure_dirs()
				self._ensure_dirs(self._db_path)
			except (OSError, IOError) as e:
				raise cache_errors.InitializationError(self.__class__, e)

			# try again if failed
			try:
				if self.__db == None:
					# dbm.open() will not work with bytes in python-3.1:
					#   TypeError: can't concat bytes to str
					self.__db = anydbm_module.open(self._db_path,
						'c', self._perms)
			except anydbm_module.error as e:
				raise cache_errors.InitializationError(self.__class__, e)
		self._ensure_access(self._db_path)

	def iteritems(self):
		return iter(self.__db.items())

	def _getitem(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return pickle.loads(self.__db[_unicode_encode(cpv)])

	def _setitem(self, cpv, values):
		self.__db[_unicode_encode(cpv)] = pickle.dumps(values,pickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self.__db[cpv]

	def __iter__(self):
		return iter(list(self.__db.keys()))

	def __contains__(self, cpv):
		return cpv in self.__db

	def __del__(self):
		if "__db" in self.__dict__ and self.__db != None:
			self.__db.sync()
			self.__db.close()

	if sys.hexversion >= 0x3000000:
		items = iteritems
