from portage_util import writemsg
import portage_file
import os, sys
from portage_data import portage_gid

class cache:
	"""
	Maintains the cache information about eclasses used in ebuild.
	"""
	def __init__(self,porttree_root,settings):
		self.porttree_root = porttree_root
		self.settings = settings
		self.depcachedir = self.settings.depcachedir[:]

		self.dbmodule = self.settings.load_best_module("eclass_cache.dbmodule")

		self.packages = {} # {"PV": {"eclass1": ["location", "_mtime_"]}}
		self.eclasses = {} # {"Name": ["location","_mtime_"]}
		
		self.porttrees=self.settings["PORTDIR_OVERLAY"].split()+[self.porttree_root]
		self.update_eclasses()

	def close_caches(self):
		for x in self.packages.keys():
			for y in self.packages[x].keys():
				try:
					self.packages[x][y].sync()
					self.packages[x][y].close()
				except SystemExit, e:
					raise
				except Exception,e:
					writemsg("Exception when closing DB: %s: %s\n" % (Exception,e))
				del self.packages[x][y]
			del self.packages[x]

	def flush_cache(self):
		self.packages = {}
		self.eclasses = {}
		self.update_eclasses()

	def update_eclasses(self):
		self.eclasses = {}
		eclass_len = len(".eclass")
#		for x in suffix_array(self.porttrees, "/eclass"):
		for x in [portage_file.normpath(os.path.join(y,"eclass")) for y in self.porttrees]:
			if x and os.path.exists(x):
				dirlist = os.listdir(x)
				for y in dirlist:
					if y[-eclass_len:]==".eclass":
						ys=y[:-eclass_len]
						try:
							ymtime=os.stat(x+"/"+y).st_mtime
						except OSError:
							continue
						self.eclasses[ys] = [x, ymtime]
	
	def setup_package(self, location, cat, pkg):
		if not self.packages.has_key(location):
			self.packages[location] = {}

		if not self.packages[location].has_key(cat):
			try:
				self.packages[location][cat] = self.dbmodule(self.depcachedir+"/"+location, cat+"-eclass", [], -1, portage_gid)
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("\n!!! Failed to open the dbmodule for eclass caching.\n")
				writemsg("!!! Generally these are permission problems. Caught exception follows:\n")
				writemsg("!!! "+str(e)+"\n")
				writemsg("!!! Dirname:  "+str(self.depcachedir+"/"+location)+"\n")
				writemsg("!!! Basename: "+str(cat+"-eclass")+"\n\n")
				sys.exit(123)
	
	def sync(self, location, cat, pkg):
		if self.packages[location].has_key(cat):
			self.packages[location][cat].sync()
	
	def update_package(self, location, cat, pkg, eclass_list):
		self.setup_package(location, cat, pkg)
		if not eclass_list:
			return 1

		data = {}
		for x in eclass_list:
			if x not in self.eclasses:
				writemsg("Eclass '%s' does not exist for '%s'\n" % (x, cat+"/"+pkg))
				return 0
			data[x] = [self.eclasses[x][0],self.eclasses[x][1]]
		
		self.packages[location][cat][pkg] = data
		self.sync(location,cat,pkg)
		return 1

	def is_current(self, location, cat, pkg, eclass_list):
		self.setup_package(location, cat, pkg)

		if not eclass_list:
			return 1

		if not (self.packages[location][cat].has_key(pkg) and self.packages[location][cat][pkg] and eclass_list):
			return 0

		myp = self.packages[location][cat][pkg]
		for x in eclass_list:
			if not (x in self.eclasses and myp.has_key(x) and myp[x][0] == self.eclasses[x][0] and
				myp[x][1] == self.eclasses[x][1]):
				return 0

		return 1			
