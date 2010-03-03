# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ["dep_expand"]

import re

from portage.dbapi.cpv_expand import cpv_expand
from portage.dep import Atom, isvalidatom
from portage.exception import InvalidAtom
from portage.versions import catsplit

def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	'''
	@rtype: Atom
	'''
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	orig_dep = mydep
	if isinstance(orig_dep, Atom):
		mydep = orig_dep.cp
	else:
		mydep = orig_dep
		has_cat = '/' in orig_dep
		if not has_cat:
			alphanum = re.search(r'\w', orig_dep)
			if alphanum:
				mydep = orig_dep[:alphanum.start()] + "null/" + \
					orig_dep[alphanum.start():]
		try:
			mydep = Atom(mydep)
		except InvalidAtom:
			# Missing '=' prefix is allowed for backward compatibility.
			if not isvalidatom("=" + mydep):
				raise
			mydep = Atom('=' + mydep)
			orig_dep = '=' + orig_dep
		if not has_cat:
			null_cat, pn = catsplit(mydep.cp)
			mydep = pn
		else:
			mydep = mydep.cp
	expanded = cpv_expand(mydep, mydb=mydb,
		use_cache=use_cache, settings=settings)
	return Atom(orig_dep.replace(mydep, expanded, 1))
