# deps.py -- Portage dependency resolution functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

# DEPEND SYNTAX:
#
# 'use?' only affects the immediately following word!
# Nesting is the only legal way to form multiple '[!]use?' requirements.
#
# Where: 'a' and 'b' are use flags, and 'z' is a depend atom.
#
# "a? z"           -- If 'a' in [use], then b is valid.
# "a? ( z )"       -- Syntax with parenthesis.
# "a? b? z"        -- Deprecated.
# "a? ( b? z )"    -- Valid
# "a? ( b? ( z ) ) -- Valid
#

import os,string,types,sys,copy
import portage_exception

def strip_empty(myarr):
	for x in range(len(myarr)-1, -1, -1):
		if not myarr[x]:
			del myarr[x]
	return myarr

def paren_reduce(mystr,tokenize=1):
	"Accepts a list of strings, and converts '(' and ')' surrounded items to sub-lists"
	mylist = []
	while mystr:
		if ("(" not in mystr) and (")" not in mystr):
			freesec = mystr
			subsec = None
			tail = ""
		elif mystr[0] == ")":
			return [mylist,mystr[1:]]
		elif ("(" in mystr) and (mystr.index("(") < mystr.index(")")):
			freesec,subsec = mystr.split("(",1)
			subsec,tail = paren_reduce(subsec,tokenize)
		else:
			subsec,tail = mystr.split(")",1)
			if tokenize:
				subsec = strip_empty(subsec.split(" "))
				return mylist+subsec,tail
			return mylist+[subsec],tail
		mystr = tail
		if freesec:
			if tokenize:
				mylist = mylist + strip_empty(freesec.split(" "))
			else:
				mylist = mylist + [freesec]
		if subsec is not None:
			mylist = mylist + [subsec]
	return mylist

def use_reduce(deparray, uselist=[], masklist=[], matchall=0, excludeall=[]):
	"""Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays
	"""
	# Quick validity checks
	for x in range(1,len(deparray)):
		if deparray[x] in ["||","&&"]:
			if len(deparray) == x:
				# Operator is the last element
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
			if type(deparray[x+1]) != types.ListType:
				# Operator is not followed by a list
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		# Conditional with no target
		raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
	
	#XXX: Compatibility -- Still required?
	if ("*" in uselist):
		matchall=1
	
	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)

		if type(head) == types.ListType:
			rlist = rlist + [use_reduce(head, uselist, masklist, matchall, excludeall)]

		else:
			if head[-1] == "?": # Use reduce next group on fail.
				# Pull any other use conditions and the following atom or list into a separate array
				newdeparray = [head]
				while isinstance(newdeparray[-1], str) and newdeparray[-1][-1] == "?":
					if mydeparray:
						newdeparray.append(mydeparray.pop(0))
					else:
						raise ValueError, "Conditional with no target."

				# Deprecation checks
				warned = 0
				if len(newdeparray[-1]) == 0:
					sys.stderr.write("Note: Empty target in string. (Deprecated)\n")
					warned = 1
				if len(newdeparray) != 2:
					sys.stderr.write("Note: Nested use flags without parenthesis (Deprecated)\n")
					warned = 1
				if warned:
					sys.stderr.write("  --> "+string.join(map(str,[head]+newdeparray))+"\n")

				# Check that each flag matches
				ismatch = True
				for head in newdeparray[:-1]:
					head = head[:-1]
					if head[0] == "!":
						head = head[1:]
						if not matchall and head in uselist or head in excludeall:
							ismatch = False
							break
					elif head not in masklist:
						if not matchall and head not in uselist:
							ismatch = False
							break
					else:
						ismatch = False

				# If they all match, process the target
				if ismatch:
					target = newdeparray[-1]
					if isinstance(target, list):
						rlist += [use_reduce(target, uselist, masklist, matchall, excludeall)]
					else:
						rlist += [target]

			else:
				rlist += [head]

	return rlist


def dep_opconvert(deplist):
	"""Move || and && to the beginning of the following arrays"""
	# Hack in management of the weird || for dep_wordreduce, etc.
	# dep_opconvert: [stuff, ["||", list, of, things]]
	# At this point: [stuff, "||", [list, of, things]]
	retlist = []
	x = 0
	while x != len(deplist):
		if isinstance(deplist[x], list):
			retlist.append(dep_opconvert(deplist[x]))
		elif deplist[x] == "||" or deplist[x] == "&&":
			retlist.append([deplist[x]] + dep_opconvert(deplist[x+1]))
			x += 1
		else:
			retlist.append(deplist[x])
		x += 1
	return retlist






class DependencyGraph:
	"""Self-contained directed graph of abstract nodes.

	This is a enhanced version of the digraph class. It supports forward
	and backward dependencies as well as primitive circular dependency
	resolution. It is fully self contained and requires only that nodes
	added to the graph are immutable.

	There are no validity checks done on the values passed to any method,
	but is written so that invalid data will either cause an exception to
	be raised. For this reason, this should not be used as part of any
	external API."""


	def __init__(self):
		"""Create an empty graph."""
		# The entire graph is stored inside this one dictionary.
		# The keys represent each node within the graph. Each node
		# is paired with a list of nodes depending on it and a list
		# of nodes it depends on. The complete structure is:
		# { node : ( [node], [node] ) }
		self.graph = {}

	def clone(self):
		"""Create an exact duplicate of this graph."""
		clone = DependencyGraph()
		# A manual copy should save a slight amount of time, but
		# is dependent on whether python's deepcopy is implemented
		# in python or not. It is at the moment.
		for node in self.graph:
			clone.graph[node] = (self.graph[node][0][:],
			                     self.graph[node][1][:])
		return clone

	def has_node(self, node):
		"""Indicate the existance of a node in the graph."""
		return self.graph.has_key(node)

	def add_node(self, node):
		"""Add a node to the graph if it hasn't been already."""
		if self.graph.has_key(node):
			return
		self.graph[node] = ([], [])

	def add_relationship(self, parent, child):
		"""Add a relationship between two pre-existing nodes."""
		# This code needs to raise an exception if either the
		# parent or child have not in fact been added prior.
		if parent not in self.graph[child][0]:
			self.graph[child][0].append(parent)
			self.graph[parent][1].append(child)

	def get_relationships(self, node):
		"""Retrieve parent and children lists of a node.

		@rtype: ( [node], [node] )
		"""
		# This code also needs to raise an exception if the node
		# has not been added prior.
		relationships = (self.graph[node][0][:],
		                 self.graph[node][1][:])
		return relationships

	def remove_node(self, node):
		"""Remove a node from the graph, destroying any relationships.

		Any relationships destroyed by removing this node are returned.

		@rtype: ( [node], [node] )
		"""
		# This code also needs to raise an exception if the node
		# has not been added prior.

		# This could be speeded up by killing the get_relationships
		# call and duplicating the code here. Should only be done if
		# absolutely necessary.
		relationships = self.get_relationships(node)

		# Ensuring that all relationships are destroyed keeps the
		# graph in a sane state. A node must _never_ depend on another
		# node that does not exist in the graph.
		for parent in relationships[0]:
			self.graph[parent][1].remove(node)
		for child in relationships[1]:
			self.graph[child][0].remove(node)

		# Kill of the other side of the relationships in one shot.
		del self.graph[node]

		return relationships

	def get_all_nodes(self):
		"""Return a list of every node in the graph.

		@rtype: [node]
		"""
		return self.graph.keys()

	def get_leaf_nodes(self):
		"""Return a list of all nodes that have no child dependencies.

		If all nodes have child dependencies and the graph is not
		empty, circular dependency resolution is attempted. In such a
		circumstance, only one node is ever returned and is passed back
		by way of an exception.

		@rtype: [node]
		"""
		# If the graph is empty, just return an empty list.
		if not self.graph:
			return []

		# Iterate through the graph's nodes and add any that have no
		# child dependencies. If we find such nodes, return them.
		nodes = []
		for node in self.graph:
			if not self.graph[node][1]:
				nodes.append(node)
		if nodes:
			return nodes

		# If we've got this far, then a circular dependency set that
		# contains every node. However, there is usually a subset of
		# nodes that are self-contained. We will find the subset with
		# the most parents so that circular dependencies can be dealt
		# with (and not have to be recalculated) as early as possible.

		# Create a list of tuples containing the number of parents
		# paired with the corresponding node.
		counts = []
		# We'll keep a record of the actual parents for later on.
		parents = {}
		for node in self.graph:
			parents[node] = self.get_parent_nodes(node, depth=0)
			counts += [(len(parents[node]), node)]

		# Reverse sort the generated list.
		counts.sort()
		counts.reverse()

		# Find the first node that is in a circular dependency set.
		for count in counts:
			node = count[1]
			children = self.get_child_nodes(node, depth=0)
			if node in children:
				break

		# Now we'll order the nodes in the set by parent count.
		counts = []
		for node in children:
			counts += [(len(parents[node]), node)]

		# Reverse sort the generated list.
		counts.sort()
		counts.reverse()

		# Return the first node in the list.
		# XXX: This needs to be changed into an exception.
		return [counts[0][1]]

	def get_root_nodes(self):
		"""Return the smallest possible list of starting nodes.

		Ordinarily, all nodes with no parent nodes are returned.
		However, if there are any circular dependencies that can
		not be reached through one of these nodes, they will be
		resolved and a suitable starting node chosen.

		@rtype: [node]
		"""
		# XXX: This is a minimalist implementation that can be highly
		# optimized later on.

		# Create a copy of our graph.
		graph = self.clone()

		# Keep processing the graph until it is empty.
		roots = []
		while graph.get_all_nodes():

			# Get a list of all leaf nodes in the graph.
			nodes = graph.get_leaf_nodes()

			# Add any of the leaves that don't have a parent.
			for node in nodes:
				if not graph.get_parent_nodes(node):
					roots.append(node)

			# Remove the nodes from the graph after checking
			# so that we don't remove the parent of a child
			# and falsely detect the child as having no parents.
			for node in nodes:
				graph.remove_node(node)

		# Return the list of roots found.
		return roots

	def get_parent_nodes(self, node, depth=1):
		"""Return a list of nodes that depend on a node.

		The examined node will be included in the returned list
		if the node exists in a circular dependency.

		@param depth: Maximum depth to recurse to, or 0 for all.
		@rtype: [node]
		"""
		return self.__traverse_nodes(node, depth, 0)

	def get_child_nodes(self, node, depth=1):
		"""Return a list of nodes depended on by node.

		The examined node will be included in the returned list
		if the node exists in a circular dependency.

		@param depth: Maximum depth to recurse to, or 0 for all.
		@rtype: [node]
		"""
		return self.__traverse_nodes(node, depth, 1)

	def __traverse_nodes(self, origin, depth, path):
		# Set depth to the maximum if it is 0.
		if not depth:
			depth = len(self.graph)
		traversed = []  # The list of nodes to be returned

		# This function _needs_ to be fast, so we use a stack
		# based implementation rather than recursive calls.
		stack = []      # Stack of previous depths
		node = origin   # The current node we are checking
		index = 0       # Progress through the node's relations
		length = len(self.graph[node][path])

		# Repeat while the stack is not empty or there are more
		# relations to be processed for the current node.
		while stack or length != index:

			# If we're finished at the current depth, move back up.
			if index == length:
				(depth, node, index, length) = stack.pop()

			# Otherwise, process the next relation.
			else:
				relation = self.graph[node][path][index]
				# Add the relation to our list if necessary...
				if relation not in traversed:
					traversed.append(relation)
					# ...and then check if we can go deeper
					if depth != 1:
						# Add state to the stack.
						stack += [(depth, node, index, length)]
						# Reset state for the new node.
						depth -= 1
						node = relation
						index = 0
						length = len(self.graph[node][path])
						# Restart the loop.
						continue

			# Move onto the next relation.
			index += 1

		# Return our list.
		return traversed
