
import anydbm,cPickle,types
from os import chown,access,R_OK,unlink
import os.path

import portage_db_template

class database(portage_db_template.database):
	def __init__(self,path,category,dbkeys,uid,gid):
		self.path     = path
		self.category = category
		self.dbkeys   = dbkeys
		self.uid      = uid
		self.gid      = gid
		
		self.modified = 0
		
		if not os.path.exists(self.path):
			prevmask=os.umask(0)
			makedirs(self.path, 02775)
			os.umask(prevmask)

		self.filename = self.path + "/" + self.category + ".cpickle"
		
		if access(self.filename, R_OK):
			mypickle=cPickle.Unpickler(open(self.filename,"r"))
			mypickle.find_global=None
			self.db = mypickle.load()
		else:
			self.db = {}

	def has_key(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return 1
		return 0
		
	def list_keys(self):
		return self.db.keys()
	
	def get_values(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return self.db[key]
		return None
	
	def set_values(self,key,val):
		self.modified = 1
		self.check_key(key)
		self.db[key] = val
	
	def del_key(self,key):
		if self.key_exists(key):
			del self.db[key]
			return True
		return False
			
	def sync(self):
		if self.modified:
			try:
				if os.path.exists(self.filename):
					unlink(self.filename)
				cPickle.dump(self.db,open(self.filename,"w"))
				chown(self.filename,self.uid,self.gid)
				chmod(self.filename, 0664)
			except:
				pass
	
	def close(self):
		self.db.close()
	
