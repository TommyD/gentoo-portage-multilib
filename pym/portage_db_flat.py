# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

import types
import os
import stat
from copy import deepcopy
from string import join

import portage_db_template

class database(portage_db_template.database):
	def module_init(self):
		self.lastkey  = None # Cache
		self.lastval  = None # Cache

		self.fullpath = os.path.join(self.path,self.category)

		if not os.path.exists(self.fullpath):
			prevmask=os.umask(0)
			os.makedirs(self.fullpath, 02775)
			os.umask(prevmask)
			try:
				os.chown(self.fullpath, self.uid, self.gid)
				os.chmod(self.fullpath, 02775)
			except SystemExit, e:
				raise
			except:
				pass

		self.flushCache()

	def __addMcache(self,key,val):
		del self.__mcache_list[2]
		self.__mcache_list.insert(0,val)
		del self.__mcache_keys[2]
		self.__mcache_keys.insert(0,key)
        
	def __delMache(self,key):
		i = self.__mcache_list.index(key)
		self.__mcache_list[i] = None
		self.__mcache_keys[i] = None

	def flushCache(self):
		portage_db_template.database.flushCache(self)
		self.__mcache_list = [None,None,None]
		self.__mcache_keys = [None,None,None]

	def has_key(self,key):
		if os.path.exists(os.path.join(self.fullpath,key)):
			return 1
		return 0
	
	def keys(self):
		# XXX: NEED TOOLS SEPERATED
		# return portage.listdir(self.fullpath,filesonly=1)
		mykeys = []
		for x in os.listdir(self.fullpath):
			if os.path.isfile(self.fullpath+x):
				mykeys += [x]
		return mykeys

	def get_timestamp(self,key,locking=True):
		import traceback
		traceback.print_stack()
		if key in self.__mcache_keys:
			return self.__mcache_list[self.__mcache_keys.index(key)]
		lock=portage_locks.lockfile(os.path.join(self.fullpath,key),wantnewlockfile=1)
		try:		x=os.stat(os.path.join(self.fullpath,key))[stat.ST_MTIME]
		except OSError:	x=None
		self.__addMcache(key,x)
		portage_locks.unlockfile(lock)
		return x

	def get_values(self,key):
		if not key:
			raise KeyError, "key is not set to a valid value"

#		mylock = portage_locks.lockfile(self.fullpath+key, wantnewlockfile=1)
#		if self.has_key(key):
		try:
#			self.get_timestamp(key,locking=False)
			myf = open(os.path.join(self.fullpath,key),"r")
			mtime = os.fstat(myf.fileno()).st_mtime
			myl = myf.readlines()
			myf.close()

			dict = {"_mtime_":mtime}
			
			if len(myl) != len(self.dbkeys):
				raise ValueError, "Key count mismatch"
			for x in range(0,len(myl)):
				if myl[x] and myl[x][-1] == "\n":
					dict[self.dbkeys[x]] = myl[x][:-1]
				else:
					dict[self.dbkeys[x]] = myl[x]
				
			return dict
		except OSError:
			return None
	
	def set_values(self,key,val):
		if not key:
			raise KeyError, "No key provided. key:%s val:%s" % (key,val)
		if not val:
			raise ValueError, "No value provided. key:%s val:%s" % (key,val)
		update_fp = os.path.join(self.fullpath, ".update.%i.%s" % (os.getpid(), key))
		myf = open(update_fp, "w")
		myf.writelines( [ val[x] +"\n" for x in self.dbkeys] )
		myf.close()

		os.chown(update_fp, self.uid, self.gid)
		os.chmod(update_fp, 0664)
		os.utime(update_fp, (-1,long(val["_mtime_"])))
		os.rename(update_fp, os.path.join(self.fullpath,key))
	
	def del_key(self,key):
		self.lastkey = None	
		self.lastval = None
		try:
			os.unlink(os.path.join(self.fullpath,key))
		except OSError:
			# either someone beat us to it, or the key doesn't exist.
			# either way, it's gone, so we return false
			return False
		return True
			
	def sync(self):
		return
	
	def close(self):
		return
	
