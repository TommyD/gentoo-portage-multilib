# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# TODO: move exceptions elsewhere, bind them to a base exception for portage

from portage.package.cpv import Atom
import logging

class Conditional(object):
	def __init__(self, node, payload):
		self.node, self.payload = node, payload

	def __str__(self):	return "%s? ( %s )" % (self.node, self.payload)

class DepSet(object):
	def __init__(self, dep_str, element_func, cleanse_string=True, collapse=True):
		"""dep_str is a dep style syntax, element_func is a callable returning the obj for each element, and
		cleanse_string controls whether or translation of tabs/newlines is required"""
		pos = 0
		if cleanse_string:
			dep_str = ' '.join(dep_str.split())
		strlen = len(dep_str)
		self.elements = []
		last_parsed = 0

		while pos < strlen:
			while pos < strlen and dep_str[pos].isspace():
				pos+=1
			next_pos = dep_str.find(" ", pos)
#			import pdb;pdb.set_trace()
			if next_pos < 0:
				self.elements.append(element_func(dep_str[pos:]))
				pos = strlen
			elif dep_str[next_pos - 1] == '?':
				# use conditional.
				block_start = next_pos
				while dep_str[block_start].isspace() and block_start < strlen:
					block_start += 1
				if block_start == strlen or dep_str[block_start] != '(':
					raise ParseError(dep_str)
				# point of optimization.  rather then reparsing every level, collapse it so single parsing.
				levels=1
				block_end = block_start = block_start + 1
				while levels:
					block_end += 1
					while block_end < strlen and dep_str[block_end] not in ('(',')'):
						block_end += 1
					if block_end == strlen:
						raise ParseError(dep_str)
					elif dep_str[block_end] == '(':
						levels += 1
					elif dep_str[block_end] == ')':
						levels -= 1
				d = self.__class__(dep_str[block_start:block_end].strip(), element_func, cleanse_string=False)
				self.elements.append(Conditional(dep_str[pos:next_pos - 1], d))
				pos = block_end + 1
			else:
				# node/element.
				self.elements.append(element_func(dep_str[pos:next_pos].strip()))
				pos = next_pos


	def __str__(self):	return ' '.join(map(str,self.elements))


class ParseError(Exception):
	def __init__(self, s):	self.dep_str = s
	def __str__(self):	return "%s is unparseable" % self.s
