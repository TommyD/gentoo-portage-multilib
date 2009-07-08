# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

import codecs
from portage.cache import fs_template
from portage.cache import cache_errors
import errno, os, stat
from portage.cache.template import reconstruct_eclasses
# store the current key order *here*.
class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.location = os.path.join(self.location, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))
		write_keys = set(self._known_keys)
		write_keys.add("_eclasses_")
		write_keys.add("_mtime_")
		self._write_keys = sorted(write_keys)
		if not self.readonly and not os.path.exists(self.location):
			self._ensure_dirs()

	def _getitem(self, cpv):
		fp = os.path.join(self.location, cpv)
		try:
			myf = codecs.open(fp, mode='r', encoding='utf_8', errors='replace')
			try:
				d = self._parse_data(myf, cpv)
				if '_mtime_' not in d:
					# Backward compatibility with old cache
					# that uses mtime mangling.
					d['_mtime_'] = long(os.fstat(myf.fileno()).st_mtime)
				return d
			finally:
				myf.close()
		except (IOError, OSError), e:
			if e.errno != errno.ENOENT:
				raise cache_errors.CacheCorruption(cpv, e)
			raise KeyError(cpv)

	def _parse_data(self, data, cpv):
		try:
			d = dict(map(lambda x:x.rstrip("\n").split("=", 1), data))
		except ValueError, e:
			# If a line is missing an "=", the split length is 1 instead of 2.
			raise cache_errors.CacheCorruption(cpv, e)
		return d

	def _setitem(self, cpv, values):
#		import pdb;pdb.set_trace()
		s = cpv.rfind("/")
		fp = os.path.join(self.location,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:
			myf = codecs.open(fp, mode='w',
				encoding='utf_8', errors='replace')
		except (IOError, OSError), e:
			if errno.ENOENT == e.errno:
				try:
					self._ensure_dirs(cpv)
					myf = codecs.open(fp, mode='w',
						encoding='utf_8', errors='replace')
				except (OSError, IOError),e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

		try:
			for k in self._write_keys:
				v = values.get(k)
				if not v:
					continue
				myf.write("%s=%s\n" % (k, v))
		finally:
			myf.close()
		self._ensure_access(fp)

		#update written.  now we move it.

		new_fp = os.path.join(self.location,cpv)
		try:
			os.rename(fp, new_fp)
		except (OSError, IOError), e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
#		import pdb;pdb.set_trace()
		try:
			os.remove(os.path.join(self.location,cpv))
		except OSError, e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def __contains__(self, cpv):
		return os.path.exists(os.path.join(self.location, cpv))


	def __iter__(self):
		"""generator for walking the dir struct"""
		dirs = [self.location]
		len_base = len(self.location)
		while len(dirs):
			try:
				dir_list = os.listdir(dirs[0])
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				dirs.pop(0)
				continue
			for l in dir_list:
				if l.endswith(".cpickle"):
					continue
				p = os.path.join(dirs[0],l)
				st = os.lstat(p)
				if stat.S_ISDIR(st.st_mode):
					dirs.append(p)
					continue
				yield p[len_base+1:]
			dirs.pop(0)

