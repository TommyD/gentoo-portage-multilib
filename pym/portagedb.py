# portagedb.py -- module to maintain portage package databases, used by pdb
# Copyright (C) Sept 2001, Chris Houser <chouser@bluweb.com>
# Distributed under the GNU General Public License
# $Header$

import string
import dbm
import pprint

class DB:
	def __init__(self, dbfile):
		self.dbfile = dbfile
		self.db = None

	def doquery(self, queries):
		if not self.db: self.db = dbm.open(self.dbfile, 'r') # open db
		pkghash = {}
		for query in queries:
			# look up query
			try:
				rec = eval(self.db[query], {}, {})
			except KeyError:
				print "Not found: '%s'" % query
				continue
			# build original CONTENTS line
			line = string.join([rec[1]] + [query] + rec[2:], ' ')
			# store result to return later
			if pkghash.has_key(rec[0]):
				pkghash[rec[0]].append(line)
			else:
				pkghash[rec[0]] = [line]
		# print results
		names = pkghash.keys()
		names.sort()
		for pkgname in names:
			print "%s:" % pkgname
			for line in pkghash[pkgname]:
				print "  %s" % line

	def storestream(self, stream, pkgname = None):
		if not self.db: self.db = dbm.open(self.dbfile, 'c') # open db
		if pkgname: print "Storing %s" % pkgname
		while 1:
			line = stream.readline()
			if line == '': break
			# parse the CONTENTS line
			words = string.split(line)
			# store the package name and CONTENTS line
			if words[0] == 'pkgname':
				pkgname = words[1]
				print "Storing %s" % pkgname
			elif words[0] != 'dir':
				rec = [pkgname] + [words[0]] + words[2:]
				self.db[words[1]] = pprint.pformat(rec)
