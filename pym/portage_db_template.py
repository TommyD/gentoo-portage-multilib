
class database:
	def __init__(self,path,category,dbkeys):
		raise NotImplementedError("Method not defined")

	def check_key(self,key):
		if not key:
			raise KeyError, "No key provided. key:%s" % (key)
	
	def clear(self):
		for x in self.list_keys():
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
	
def test_database(db_class,path,category,dbkeys):
	d = db_class(path,category,dbkeys)

	list = d.list_keys()
	if(len(list) == 0):
		d.set_values("test-2.2.3-r1", dbkeys)
		d.set_values("test-2.2.3-r2", dbkeys)
		d.set_values("test-2.2.3-r3", dbkeys)
		d.set_values("test-2.2.3-r4", dbkeys)

	list = d.list_keys()
	print "Key count:",len(list)

	values = d.get_values(list[0])
	print "value count:",len(values)
	
	mykey = "foobar-1.2.3-r4"
	
	d.check_key(mykey)
	d.set_values(mykey, dbkeys)
	del d

	d = db_class(path,category,dbkeys)
	new_vals = d.get_values(mykey)
	if new_vals != dbkeys:
		print "keys do not match:",dbkeys,new_vals
	
	d.del_key(mykey)
	
	print "Should be None:",d.get_values(mykey)

	d.clear()

	d.sync
	d.close
	
	del d
	
	print "Done."