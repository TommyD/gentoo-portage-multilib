from portage.cache import fs_template
from portage.cache import cache_errors
from portage import os
from portage import _unicode_encode
import codecs
import errno
import stat

# store the current key order *here*.
class database(fs_template.FsBased):

	autocommits = True

	# do not screw with this ordering. _eclasses_ needs to be last
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE', 'EAPI', 'PROPERTIES', 'DEFINED_PHASES')

	def __init__(self, label, auxdbkeys, **config):
		super(database,self).__init__(label, auxdbkeys, **config)
		self._base = os.path.join(self._base, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if len(self._known_keys) > len(self.auxdbkey_order) + 2:
			raise Exception("less ordered keys then auxdbkeys")
		if not os.path.exists(self._base):
			self._ensure_dirs()


	def _getitem(self, cpv):
		d = {}
		try:
			myf = codecs.open(_unicode_encode(os.path.join(self._base, cpv)),
				mode='r', encoding='utf_8', errors='replace')
			for k,v in zip(self.auxdbkey_order, myf):
				d[k] = v.rstrip("\n")
		except (OSError, IOError),e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			raise cache_errors.CacheCorruption(cpv, e)

		try:
			d["_mtime_"] = long(os.fstat(myf.fileno()).st_mtime)
		except OSError, e:	
			myf.close()
			raise cache_errors.CacheCorruption(cpv, e)
		myf.close()
		return d


	def _setitem(self, cpv, values):
		s = cpv.rfind("/")
		fp=os.path.join(self._base,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:
			myf = codecs.open(_unicode_encode(fp), mode='w',
				encoding='utf_8', errors='replace')
		except (OSError, IOError), e:
			if errno.ENOENT == e.errno:
				try:
					self._ensure_dirs(cpv)
					myf = codecs.open(_unicode_encode(fp), mode='w',
						encoding='utf_8', errors='replace')
				except (OSError, IOError),e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)
		

		for x in self.auxdbkey_order:
			myf.write(values.get(x,"")+"\n")

		myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])
		#update written.  now we move it.
		new_fp = os.path.join(self._base,cpv)
		try:
			os.rename(fp, new_fp)
		except (OSError, IOError), e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
		try:
			os.remove(os.path.join(self._base,cpv))
		except OSError, e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def __contains__(self, cpv):
		return os.path.exists(os.path.join(self._base, cpv))


	def __iter__(self):
		"""generator for walking the dir struct"""
		dirs = [self._base]
		len_base = len(self._base)
		while len(dirs):
			for l in os.listdir(dirs[0]):
				if l.endswith(".cpickle"):
					continue
				p = os.path.join(dirs[0],l)
				st = os.lstat(p)
				if stat.S_ISDIR(st.st_mode):
					dirs.append(p)
					continue
				yield p[len_base+1:]
			dirs.pop(0)


	def commit(self):	pass
