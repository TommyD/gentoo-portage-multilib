import os
import template, cache_errors

class FsBased(template.database):
	"""template wrapping fs needed options, and providing _ensure_access as a way to 
	attempt to ensure files have the specified owners/perms"""

	def __init__(self, label, auxdbkeys, basepath=None, gid=-1, perms=0664, **config):
		"""throws InitializationError if needs args aren't specified"""
		if not gid:	
			raise cache_errors.InitializationError(self.__class__, "must specify gid!")
		if not basepath:
			raise cache_errors.InitializationError(self.__class__, "must specify basepath!")

		self._gid = gid
		self._base = basepath
		self._perms = perms
		super(FsBased, self).__init__(label, auxdbkeys, **config)

		if self.label.startswith(os.path.sep):
			# normpath.
			self.label = os.path.sep + os.path.normpath(self.label).lstrip(os.path.sep)


	def _ensure_access(self, path, mtime=-1):
		"""returns true or false if it's able to ensure that path is properly chmod'd and chowned.
		if mtime is specified, attempts to ensure that's correct also"""
		try:
			os.chown(path, -1, self._gid)
			os.chmod(path, self._perms)
			if mtime:
				mtime=long(mtime)
				os.utime(path, (mtime, mtime))
		except OSError, IOError:
			return False
		return True

	def _ensure_dirs(self, path=None):
		"""with path!=None, ensure beyond self._base.  otherwise, ensure self._base"""
		if path:
			path = os.path.dirname(path)
			base = self._base
		else:
			path = self._base
			base='/'

		for dir in path.lstrip(os.path.sep).rstrip(os.path.sep).split(os.path.sep):
			base = os.path.join(base,dir)
			if not os.path.exists(base):
				os.mkdir(base, self._perms | 0111)
				os.chown(base, -1, self._gid)
				

	
def gen_label(base, label):
	"""if supplied label is a path, generate a unique label based upon label, and supplied base path"""
	if label.find(os.path.sep) == -1:
		return label
	label = label.strip("\"").strip("'")
	label = os.path.join(*(label.rstrip(os.path.sep).split(os.path.sep)))
	tail = os.path.split(label)[1]
	return "%s-%X" % (tail, abs(label.__hash__()))

