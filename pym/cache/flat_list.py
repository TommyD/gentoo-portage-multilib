import os, stat
import fs_template
import cache_errors

# store the current key order *here*.
auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
	'PDEPEND',   'PROVIDE')

class database(fs_template.FsBased):


	def __init__(self, label, auxdbkeys, **config):
		super(database,self).__init__(label, auxdbkeys, **config)
		self._base = os.path.join(self._base, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))
		if len(self._known_keys) > len(auxdbkey_order):
			raise Exception("less ordered keys then auxdbkeys")


	def __getitem__(self, cpv):
		d = {}
		try:
			myf = open(os.path.join(self._base, cpv),"r")
			for k,v in zip(auxdbkey_order, myf):
				d[k] = v.rstrip("\n")
		except (OSError, IOError),e:
			if isinstance(e,IOError) and e.errno == 2:
				raise KeyError(cpv)
			raise cache_errors.CacheCorruption(cpv, e)

		try:	d["_mtime_"] = os.lstat(os.path.join(self._base, cpv)).st_mtime
		except OSError, e:	raise cache_errors.CacheCorruption(cpv, e)

		return d


	def _setitem(self, cpv, values):
		try:	myf=open(os.path.join(self._base, cpv), "w")
		except (OSError, IOError), e:
			try:	
				s = os.path.split(cpv)
				if len(s[0]) == 0:
					s = s[1]
				else:
					s = s[0]
				os._ensure_dirs(s)

			except (OSError, IOError), e:
				raise cache_errors.CacheCorruption(cpv, e)

		try:	
			myf.writelines([values.get(x,"")+"\n" for x in auxdbkey_order])
			myf.close()
			self._ensure_access(os.path.join(self._base, cpv), mtime=values["_mtime_"])

		except (IOError, OSError), e:
			try:	myf.close()
			except (OSError, IOError): pass
			try:	os.remove(os.path.join(self._base, cpv))
			except (OSError, IOError): pass
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
		try:
			os.remove(os.path.join(self._base,cpv))
		except OSError, e:
			if e.errno == 2:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def has_key(self, cpv):
		return os.path.exists(os.path.join(self._base, cpv))


	def keys(self):
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

