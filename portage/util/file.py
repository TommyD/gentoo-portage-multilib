# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import re
from shlex import shlex
from mappings import ProtectedDict

def iter_read_bash(file):
	"""read file honoring bash commenting rules.  Note that it's considered good behaviour to close filehandles, as such, 
	either iterate fully through this, or use read_bash instead.
	once the file object is no longer referenced, the handle will be closed, but be proactive instead of relying on the 
	garbage collector."""
	f = open(file)
	for s in f:
		s=s.strip()
		if s.startswith("#") or s == "":
			continue
		yield s
	f.close()

def read_bash(file):
	return list(iter_read_bash(file))

def read_dict(file, splitter="=", ignore_malformed=False, source_isiter=False):
	"""
	read key value pairs, splitting on specified splitter, using iter_read_bash for filtering comments
	"""
	d = {}
	if not source_isiter:
		i = iter_read_bash(file)
	else:
		i = file
	line_count = 1
	try:
		for k in i:
			line_count += 1
			try:
				k, v = k.split(splitter, 1)
			except ValueError:
				if not ignore_malformed:
					raise ParseError(file, line_count)
			else:
				if len(v) > 2 and v[0] == v[-1] and v[0] in ("'", '"'):
					v=v[1:-1]
				d[k] = v
	finally:
		del i
	return d

def read_bash_dict(file, vars_dict={}, ignore_malformed=False, sourcing_command=None):
	"""read bash source, yielding a dict of vars
	vars_dict is the initial 'env' for the sourcing, and is protected from modification.
	sourcing_command controls whether a source command exists, if one does and is encountered, then this func
	recursively sources that file
	"""
	from shlex import shlex
	from types import StringTypes
	f = open(file, "r")

	# quite possibly I'm missing something here, but the original portage_util getconfig/varexpand seemed like it 
	# only went halfway.  The shlex posix mode *should* cover everything.

	if len(vars_dict.keys()) != 0:
		d, protected = ProtectedDict(vars_dict), True
	else:
		d, protected = vars_dict, False
	s = bash_parser(f, sourcing_command=sourcing_command, env=d)

	try:
		tok = ""
		try:
			while tok != None:
				key = s.get_token()
				if key == None:
					break
				eq, val = s.get_token(), s.get_token()
				if eq != '=' or val == None:
					if not ignore_malformed:
						raise ParseError(file, s.lineno)
					else:
						break
				d[key] = val
		except ValueError:
			raise ParseError(file, s.lineno)
	finally:
		f.close()
	if protected:
		d = d.new
	return d


var_find = re.compile("\\\\?(\${\w+}|\$\w+)")
backslash_find = re.compile("\\\\.")
def nuke_backslash(s):
	s = s.group()
	if s == "\\\n":	return "\n"
	try:	return chr(ord(s))
	except TypeError:
		return s[1]

class bash_parser(shlex):
	def __init__(self, source, sourcing_command=None, env={}):
		shlex.__init__(self, source, posix=True)
		self.wordchars += "${}/."
		if sourcing_command != None:
			self.source = allow_sourcing
		self.env = env
		self.__pos = 0

	def __setattr__(self, attr, val):
		if attr == "state" and "state" in self.__dict__:
			if (self.state, val) in (('"','a'),('a','"'), ('a', ' '), ("'", 'a')):
				strl = len(self.token)
				if self.__pos != strl:
					self.changed_state.append((self.state, self.token[self.__pos:]))
				self.__pos = strl
		self.__dict__[attr] = val

	def read_token(self):
		self.changed_state = []
		self.__pos = 0
		tok = shlex.read_token(self)
		if tok == None:
			return tok
		self.changed_state.append((self.state, self.token[self.__pos:]))
		tok = ''
		for s, t in self.changed_state:
			if s in ('"', "a"):		tok += self.var_expand(t)
			else:							tok += t
		return tok

	def var_expand(self, val):
		prev, pos = 0, 0
		l=[]
		match = var_find.search(val)
		while match != None:
			pos = match.start()
			if val[pos] == '\\':
				# it's escaped.  either it's \\$ or \\${ , either way, skipping two ahead handles it.
				pos += 2
			else:
				var = val[match.start():match.end()].strip("${}")
				if prev != pos:
					l.append(val[prev:pos])
				if var in self.env:	l.append(self.env[var])
				else:						l.append("")
				prev = pos = match.end()
			match = var_find.search(val, pos)

		# do \\ cleansing, collapsing val down also.
		val = backslash_find.sub(nuke_backslash, ''.join(l) + val[prev:])
		return val

class ParseError(Exception):
	def __init__(self, file, line):	self.file, self.line = file, line
	def __str__(self):	return "error parsing '%s' on or before %i" % (self.file, self.line)
