# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

def load_module(name):
	m = __import__(name)
	nl = name.split('.')
	# __import__ returns nl[0]... so.
	nl.pop(0)
	while len(nl):
		m = getattr(m, nl[0])
		nl.pop(0)
	return m	

def load_attribute(name):
	i = name.rfind(".")
	if i == -1:
		raise ValueError("name isn't an attribute, it's a module... : %s" % name)
	m = load_module(name[:i])
	m = getattr(m, name[i+1:])
	return m
