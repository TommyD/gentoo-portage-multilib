# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

import types
import os
import stat
from copy import deepcopy
from string import join

import portage_db_template
import portage_locks

class database(portage_db_template.database):
	def module_init(self):
		self.lastkey  = None # Cache
		self.lastval  = None # Cache

		self.fullpath = self.path + "/" + self.category + "/"

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
		
	def has_key(self,key):
		if os.path.exists(self.fullpath+key):
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

	def get_values(self,key):
		if not key:
			raise KeyError, "key is not set to a valid value"

		mylock = portage_locks.lockfile(self.fullpath+key, wantnewlockfile=1)
		if self.has_key(key):
			mtime = os.stat(self.fullpath+key)[stat.ST_MTIME]
			myf = open(self.fullpath+key)
			myl = myf.readlines()
			myf.close()
			portage_locks.unlockfile(mylock)

			dict = {"_mtime_":mtime}
			
			if len(myl) != len(self.dbkeys):
				raise ValueError, "Key count mismatch"
			for x in range(0,len(myl)):
				if myl[x] and myl[x][-1] == "\n":
					dict[self.dbkeys[x]] = myl[x][:-1]
				else:
					dict[self.dbkeys[x]] = myl[x]
				
			return dict
		else:
			portage_locks.unlockfile(mylock)
		return None
	
	def set_values(self,key,val):
		if not key:
			raise KeyError, "No key provided. key:%s val:%s" % (key,val)
		if not val:
			raise ValueError, "No value provided. key:%s val:%s" % (key,val)
			
		data = ""
		for x in self.dbkeys:
			data += val[x]+"\n"

		mylock = portage_locks.lockfile(self.fullpath+key, wantnewlockfile=1)
		if os.path.exists(self.fullpath+key):
			os.unlink(self.fullpath+key)

		myf = open(self.fullpath+key,"w")
		myf.write(data)
		myf.flush()
		myf.close()
		
		os.chown(self.fullpath+key, self.uid, self.gid)
		os.chmod(self.fullpath+key, 0664)
		os.utime(self.fullpath+key, (long(val["_mtime_"]),long(val["_mtime_"])))
		portage_locks.unlockfile(mylock)
	
	def del_key(self,key):
		mylock = portage_locks.lockfile(self.fullpath+key, wantnewlockfile=1)
		if self.has_key(key):
			os.unlink(self.fullpath+key)
			portage_locks.unlockfile(mylock)
			self.lastkey = None
			self.lastval = None
			return 1
		portage_locks.unlockfile(mylock)
		return 0
			
	def sync(self):
		return
	
	def close(self):
		return
	
