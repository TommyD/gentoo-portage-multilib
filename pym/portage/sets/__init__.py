# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from ConfigParser import SafeConfigParser, NoOptionError
from portage import load_mod
from portage.const import USER_CONFIG_PATH, GLOBAL_CONFIG_PATH

SETPREFIX = "@"

class SetConfigError(Exception):
	pass

class SetConfig(SafeConfigParser):
	def __init__(self, paths, settings, trees):
		SafeConfigParser.__init__(self)
		self.read(paths)
		self.errors = []
		self.psets = {}
		self.trees = trees
		self.settings = settings
		self._parsed = False
		self.active = []
		self.aliases = {}

	def _parse(self):
		if self._parsed:
			return
		for sname in self.sections():
			# find classname for current section, default to file based sets
			if not self.has_option(sname, "class"):
				classname = "portage.sets.files.StaticFileSet"
			else:
				classname = self.get(sname, "class")
			
			# try to import the specified class
			try:
				setclass = load_mod(classname)
			except (ImportError, AttributeError):
				self.errors.append("Could not import '%s' for section '%s'" % (classname, sname))
				continue
			# prepare option dict for the current section
			optdict = {}
			for oname in self.options(sname):
				optdict[oname] = self.get(sname, oname)
			
			# create single or multiple instances of the given class depending on configuration
			if self.has_option(sname, "multiset") and self.getboolean(sname, "multiset"):
				if hasattr(setclass, "multiBuilder"):
					try:
						self.psets.update(setclass.multiBuilder(optdict, self.settings, self.trees))
					except SetConfigError, e:
						self.errors.append("Configuration error in section '%s': %s" % (sname, str(e)))
						continue
				else:
					self.errors.append("Section '%s' is configured as multiset, but '%s' doesn't support that configuration" % (sname, classname))
					continue
			else:
				try:
					setname = self.get(sname, "name")
				except NoOptionError:
					setname = sname
				if hasattr(setclass, "singleBuilder"):
					try:
						self.psets[setname] = setclass.singleBuilder(optdict, self.settings, self.trees)
					except SetConfigError, e:
						self.errors.append("Configuration error in section '%s': %s" % (sname, str(e)))
						continue
				else:
					self.errors.append("'%s' does not support individual set creation, section '%s' must be configured as multiset" % (classname, sname))
					continue
		self._parsed = True
	
	def getSets(self):
		self._parse()
		return self.psets

	def getSetAtoms(self, setname, ignorelist=None):
		myset = self.getSets()[setname]
		myatoms = myset.getAtoms()
		if ignorelist is None:
			ignorelist = set()
		ignorelist.add(setname)
		for n in myset.getNonAtoms():
			if n[0] == SETPREFIX and n[1:] in self.psets:
				if n[1:] not in ignorelist:
					myatoms.update(self.getSetAtoms(n[1:],
						ignorelist=ignorelist))
		return myatoms

def load_default_config(settings, trees):
	setconfigpaths = [os.path.join(GLOBAL_CONFIG_PATH, "sets.conf")]
	setconfigpaths.append(os.path.join(settings["PORTDIR"], "sets.conf"))
	setconfigpaths += [os.path.join(x, "sets.conf") for x in settings["PORDIR_OVERLAY"].split()]
	setconfigpaths.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH.lstrip(os.path.sep), "sets.conf"))
	return SetConfig(setconfigpaths, settings, trees)

# adhoc test code
if __name__ == "__main__":
	import portage
	sc = load_default_config(portage.settings, portage.db["/"])
	l, e = sc.getSets()
	for x in l:
		print x+":"
		print "DESCRIPTION = %s" % l[x].getMetadata("Description")
		for n in sorted(l[x].getAtoms()):
			print "- "+n
		print
