# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org), Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# TODO: move exceptions elsewhere, bind them to a base exception for portage

import logging
from portage.restrictions.packages import OrRestriction, AndRestriction
from portage.package.conditionals import base as Conditional
from portage.util.lists import unique, flatten
from portage.util.strings import iter_tokens

def conditional_converter(node, payload):
	if node[0] == "!":
		return Conditional(node[1:], payload, negate=True)
	return Conditional(node, payload)

	
class DepSet(AndRestriction):
	__slots__ = ("has_conditionals", "conditional_class", "node_conds")
	def __init__(self, dep_str, element_func, operators={"||":OrRestriction}, \
		conditional_converter=conditional_converter, conditional_class=Conditional, empty=False):

		"""dep_str is a dep style syntax, element_func is a callable returning the obj for each element, and
		cleanse_string controls whether or translation of tabs/newlines is required"""

		super(DepSet, self).__init__()
		self.conditional_class = conditional_class
		self.node_conds = {}
		
		if empty:	return

		# anyone who uses this routine as fodder for pushing a rewrite in lisp I reserve the right to deliver an 
		# atomic wedgie upon.
		# ~harring

		conditionals, depsets, has_conditionals = [], [self], [False]
		raw_conditionals = []
		words = iter_tokens(dep_str)
		try:
			for k in words:
				if k == ")":
					# no elements == error.  if closures don't map up, indexerror would be chucked from trying to pop the frame
					# so that is addressed.
					if len(depsets[-1].restrictions) == 0:
						raise ParseError(dep_str)
					elif conditionals[-1].endswith('?'):
						cond = raw_conditionals[:]
						depsets[-2].restrictions.append(conditional_converter(conditionals.pop(-1)[:-1], depsets[-1]))
						raw_conditionals.pop(0)
						for x in depsets[-1]:
							self.node_conds.setdefault(x, []).append(cond)
					else:
						depsets[-2].restrictions.append(operators[conditionals.pop(-1)](depsets[-1]))

					depsets[-1].has_conditionals = has_conditionals.pop(-1)
					depsets.pop(-1)

				elif k.endswith('?') or k in operators:
					# use conditional or custom op. no tokens left == bad dep_str.
					try:							k2 = words.next()
					except StopIteration:	k2 = ''

					if k2 != "(":
						raise ParseError(dep_str)

					# push another frame on
					depsets.append(self.__class__(None, element_func, empty=True, conditional_converter=conditional_converter,
						conditional_class=self.conditional_class))
					conditionals.append(k)
					if k.endswith("?"):
						has_conditionals[-1] = True
						raw_conditionals.append(k[:-1])
					has_conditionals.append(False)

				else:
					# node/element.
					depsets[-1].restrictions.append(element_func(k))
		

		except IndexError:
			# [][-1] for a frame access, which means it was a parse error.
			raise ParseError(dep_str)

		# check if any closures required
		if len(depsets) != 1:
			raise ParseError(dep_str)
		self.has_conditionals = has_conditionals[0]
		for x in self.node_conds:
			self.node_conds[x] = tuple(unique(flatten(self.node_conds[x])))
			
	def __str__(self):	return ' '.join(map(str,self.restrictions))

	def evaluate_depset(self, cond_dict):
		"""passed in a depset, does lookups of the node in cond_dict.
		no entry in cond_dict == conditional is off, else the bool value of the key's val in cond_dict"""

		if not self.has_conditionals:		return self

		flat_deps = DepSet("", str)

		stack = [self.restrictions]
		while len(stack) != 0:
			for node in stack[0]:
				if isinstance(node, self.conditional_class):
					if node.cond in cond_dict:
						if not node.negate:
							stack.append(node.restrictions)
					elif node.negate:
						stack.append(node.restrictions)
				else:
					flat_deps.restrictions.append(node)
			stack.pop(0)
		return flat_deps

	def __iter__(self):
		return iter(self.restrictions)

	def match(self, *a):
		raise NotImplementedError
	force_False = force_True = match

class ParseError(Exception):
	def __init__(self, s):	self.dep_str = s
	def __str__(self):	return "%s is unparseable" % self.s


