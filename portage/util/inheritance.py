# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

def check_for_base(obj, allowed):
	"""Look through __class__ to see if any of the allowed classes are found, returning the first allowed found"""
	for x in allowed:
		if issubclass(obj.__class__, x):
			return x
	return None
