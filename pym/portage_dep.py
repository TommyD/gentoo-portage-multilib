# deps.py -- Portage dependency resolution functions
# Copyright 2003 Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2
# $Id$

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

import os,string,types,sys

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
			subsec = []
			tail = ""
		elif mystr[0] == ")":
			return mylist,mystr[1:]
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
		if subsec:
			mylist = mylist + [subsec]
	return mylist

def use_reduce(deparray, uselist=[], masklist=[], matchall=0):
	"""Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays
	"""
	if ("*" in uselist):
		matchall=1
	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)
		if type(head) == types.ListType:
			rlist = rlist + use_reduce(head, uselist, masklist, matchall)
		else:
			matchon = 1 # Match on true
			if head[-1] == "?": # Use reduce next group on fail.
				if head[0] == "!":
					matchon = 0 # Inverted... match on false
					head = head[1:]
				if matchall or \
           (((head[:-1] in uselist) == matchon) and \
            (head[:-1] not in masklist)):
					# It is set, keep it.
					if mydeparray: # Error check: if nothing more, then error.
						newdeparray = mydeparray.pop(0)
						if type(newdeparray) == types.ListType:
							rlist = rlist + use_reduce(newdeparray, uselist, masklist, matchall)
						elif newdeparray[-1] == "?":
							# This section is for  "a? b? c? target" strings.
							# It recurses the non-conforming series.
							newdlist = [newdeparray]
							while mydeparray:
								newdlist.append(mydeparray.pop(0))
								if (type(newdlist[-1]) == types.ListType) or \
								   (newdlist[-1][-1]!="?"):
									break
							rlist = rlist + use_reduce(newdlist, uselist, masklist, matchall)
							sys.stderr.write("Note: Nested use flags without parenthesis! (Deprecated)\n")
							sys.stderr.write("      "+string.join(map(str,newdlist))+"\n")
						else:
							rlist = rlist + [newdeparray]
					else:
						raise ValueError, "Conditional with no target."
				else:
					if mydeparray: # Not set, drop it.
						del mydeparray[0]
					else:
						raise ValueError, "Conditional with no target."
			else:
				rlist = rlist + [head]
	return rlist
