# $Header$

class database:
	def __init__(self,path,category,dbkeys,uid,gid):
		raise NotImplementedError("Method not defined")

	def check_key(self,key):
		if not key:
			raise KeyError, "No key provided. key:%s" % (key)
	
	def clear(self):
		for x in self.keys():
			self.del_key(x)
	
	def __getitem__(self,key):
		return self.get_values(key)
	
	def __setitem__(self,key,values):
		return self.set_values(key,values)

	def has_key(self,key):
		raise NotImplementedError("Method not defined")
	
	def keys(self):
		raise NotImplementedError("Method not defined")

	def get_values(self,key):
		if not key:
			raise KeyError, "key is not set to a valid value"

		raise NotImplementedError("Method not defined")
	
	def set_values(self,key,val):
		self.check_key(key)
		
		raise NotImplementedError("Method not defined")

	def del_key(self,key):
		raise NotImplementedError("Method not defined")
			
	def sync(self):
		raise NotImplementedError("Method not defined")
	
	def close(self):
		raise NotImplementedError("Method not defined")


	
def test_database(db_class,path,category,dbkeys,uid,gid):
	if "_mtime_" not in dbkeys:
		dbkeys+=["_mtime_"]
	d = db_class(path,category,dbkeys,uid,gid)

	print "Module: "+str(d.__module__)

	# XXX: Need a way to do this that actually works.
	for x in dir(database):
		if x not in dir(d):
			print "FUNCTION MISSING:",str(x)

	list = d.keys()
	if(len(list) == 0):
		values = {}
		for x in dbkeys:
			values[x] = x[:]
		values["_mtime_"] = "1079903037"
		d.set_values("test-2.2.3-r1", values)
		d.set_values("test-2.2.3-r2", values)
		d.set_values("test-2.2.3-r3", values)
		d.set_values("test-2.2.3-r4", values)

	list = d.keys()
	print "Key count:",len(list)

	values = d.get_values(list[0])
	print "value count:",len(values)
	
	mykey = "foobar-1.2.3-r4"
	
	d.check_key(mykey)
	d.set_values(mykey, values)
	d.sync()
	del d

	d = db_class(path,category,dbkeys,uid,gid)
	new_vals = d.get_values(mykey)

	if dbkeys and new_vals:
		for x in dbkeys:
			if x not in new_vals.keys():
				print "---",x
		for x in new_vals.keys():
			if x not in dbkeys:
				print "+++",x
	else:
		print "Mismatched:",dbkeys,new_vals
	
	d.del_key(mykey)
	
	print "Should be None:",d.get_values(mykey)

	d.clear()

	d.sync
	d.close
	
	del d
	
	print "Done."
