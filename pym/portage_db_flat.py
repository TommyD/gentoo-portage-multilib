# $Header$

import types,os
from copy import deepcopy
from string import join

import portage_db_template

class database(portage_db_template.database):
	def __init__(self,path,category,dbkeys,uid,gid):
		self.path     = path
		self.category = category
		self.dbkeys   = dbkeys
		self.uid      = uid
		self.gid      = gid

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

		if self.has_key(key):
			import os,stat
			mtime = os.stat(self.fullpath+key)[stat.ST_MTIME]
			myf = open(self.fullpath+key)
			myl = myf.readlines()

			dict = {"_mtime_":mtime}
			
			if len(myl) != len(self.dbkeys):
				raise ValueError, "Key count mismatch"
			for x in range(0,len(myl)):
				if myl[x] and myl[x][-1] == "\n":
					dict[self.dbkeys[x]] = myl[x][:-1]
				else:
					dict[self.dbkeys[x]] = myl[x]
				
			return dict
		return None
	
	def set_values(self,key,val):
		if not key:
			raise KeyError, "No key provided. key:%s val:%s" % (key,val)
		if not val:
			raise ValueError, "No value provided. key:%s val:%s" % (key,val)
			
		data = ""
		for x in self.dbkeys:
			data += val[x]+"\n"

		if os.path.exists(self.fullpath+key):
			os.unlink(self.fullpath+key)

		myf = open(self.fullpath+key,"w")
		myf.write(data)
		myf.flush()
		myf.close()
		
		os.chown(self.fullpath+key, self.uid, self.gid)
		os.chmod(self.fullpath+key, 0664)
		os.utime(self.fullpath+key, (long(val["_mtime_"]),long(val["_mtime_"])))
	
	def del_key(self,key):
		if self.has_key(key):
			os.unlink(self.fullpath+key)
			self.lastkey = None
			self.lastval = None
			return 1
		return 0
			
	def sync(self):
		return
	
	def close(self):
		return
	
