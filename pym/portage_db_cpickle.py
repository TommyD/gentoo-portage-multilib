# $Header$

import anydbm,cPickle,types
from os import chown,access,R_OK,unlink
import os

import portage_db_template

class database(portage_db_template.database):
	def __init__(self,path,category,dbkeys,uid,gid):
		self.path     = path
		self.category = category
		self.dbkeys   = dbkeys
		self.uid      = uid
		self.gid      = gid
		
		self.modified = False
		
		prevmask=os.umask(0)
		if not os.path.exists(self.path):
			os.makedirs(self.path, 02775)

		self.filename = self.path + "/" + self.category + ".cpickle"
		
		if access(self.filename, R_OK):
			mypickle=cPickle.Unpickler(open(self.filename,"r"))
			mypickle.find_global=None
			try:
				self.db = mypickle.load()
			except:
				self.db = {}
		else:
			self.db = {}

		os.umask(prevmask)

	def has_key(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return 1
		return 0
		
	def keys(self):
		return self.db.keys()
	
	def get_values(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return self.db[key]
		return None
	
	def set_values(self,key,val):
		self.modified = True
		self.check_key(key)
		self.db[key] = val
	
	def del_key(self,key):
		if self.has_key(key):
			del self.db[key]
			self.modified = True
			return True
		return False
			
	def sync(self):
		if self.modified:
			try:
				if os.path.exists(self.filename):
					unlink(self.filename)
				cPickle.dump(self.db,open(self.filename,"w"))
				os.chown(self.filename,self.uid,self.gid)
				os.chmod(self.filename, 0664)
			except:
				pass
	
	def close(self):
		self.sync()
		self.db = None;
	
