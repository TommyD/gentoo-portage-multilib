
import types,os.path
from marshal import loads,dumps
from copy import deepcopy
from os import makedirs,unlink
from string import join

import portage_db_template

class database(portage_db_template.database):
	def __init__(self,path,category,dbkeys):
		self.path     = path
		self.category = category
		self.dbkeys   = dbkeys

		self.lastkey  = None # Cache
		self.lastval  = None # Cache

		self.fullpath = self.path + "/" + self.category + "/"

		if not os.path.exists(self.fullpath):
			makedirs(self.fullpath)

	def key_exists(self,key):
		if os.path.exists(self.fullpath+key):
			return 1
		return 0
	
	def list_keys(self):
		# XXX: NEED TOOLS SEPERATED
		# return portage.listdir(self.fullpath,filesonly=1)
		mykeys = []
		for x in os.listdir(self.fullpath):
			print x,self.fullpath+x,os.path.isdir(self.fullpath+x)
			if os.path.isfile(self.fullpath+x):
				mykeys += [x]
		return mykeys

	def get_values(self,key):
		if not key:
			raise KeyError, "key is not set to a valid value"

		if self.lastkey == key: # Use the cache
			return copy.deepcopy(self.lastval)

		if self.key_exists(key):
			myf = open(self.fullpath+key)
			myl = myf.readlines()
			if len(myl) != len(self.dbkeys):
				return None
			newl = []

			for l in myl:
				if l[-1] == "\n":
					newl += [l[:-1]]
				else:
					newl += [l]
			self.lastkey = key
			self.lastval = copy.deepcopy(newl)
			return newl
			
		return None
	
	def set_values(self,key,val):
		if not key:
			raise KeyError, "No key provided. key:%s val:%s" % (key,val)
		if not val:
			raise ValueError, "No value provided. key:%s val:%s" % (key,val)
		if len(val) != len(self.dbkeys):
			raise ValueError, "Not enough values provided key:%s val:%s" % (key,val)
		
		data = join(val,"\n")+"\n"
		myf = open(self.fullpath+key,"w")
		myf.write(data)
		myf.flush()
		myf.close()
	
	def del_key(self,key):
		if self.key_exists(key):
			unlink(self.fullpath+key)
			self.lastkey = None
			self.lastval = None
			return 1
		return 0
			
	def sync(self):
		return
	
	def close(self):
		return
	
