# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ['dep_check', 'dep_eval', 'dep_wordreduce', 'dep_zapdeps']

import logging

import portage
from portage.dep import Atom, dep_opconvert, match_from_list, paren_reduce, \
	remove_slot, use_reduce
from portage.exception import InvalidAtom, InvalidDependString, ParseError
from portage.localization import _
from portage.util import writemsg, writemsg_level
from portage.versions import catpkgsplit, cpv_getkey, pkgcmp

def _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings, myroot="/",
	trees=None, use_mask=None, use_force=None, **kwargs):
	"""
	In order to solve bug #141118, recursively expand new-style virtuals so
	as to collapse one or more levels of indirection, generating an expanded
	search space. In dep_zapdeps, new-style virtuals will be assigned
	zero cost regardless of whether or not they are currently installed. Virtual
	blockers are supported but only when the virtual expands to a single
	atom because it wouldn't necessarily make sense to block all the components
	of a compound virtual.  When more than one new-style virtual is matched,
	the matches are sorted from highest to lowest versions and the atom is
	expanded to || ( highest match ... lowest match )."""
	newsplit = []
	mytrees = trees[myroot]
	portdb = mytrees["porttree"].dbapi
	atom_graph = mytrees.get("atom_graph")
	parent = mytrees.get("parent")
	virt_parent = mytrees.get("virt_parent")
	graph_parent = None
	eapi = None
	if parent is not None:
		if virt_parent is not None:
			graph_parent = virt_parent
			eapi = virt_parent[0].metadata['EAPI']
		else:
			graph_parent = parent
			eapi = parent.metadata["EAPI"]
	repoman = not mysettings.local_config
	if kwargs["use_binaries"]:
		portdb = trees[myroot]["bintree"].dbapi
	myvirtuals = mysettings.getvirtuals()
	pprovideddict = mysettings.pprovideddict
	myuse = kwargs["myuse"]
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			newsplit.append(_expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, use_mask=use_mask,
				use_force=use_force, **kwargs))
			continue

		if not isinstance(x, Atom):
			try:
				x = Atom(x)
			except InvalidAtom:
				if portage.dep._dep_check_strict:
					raise ParseError(
						_("invalid atom: '%s'") % x)
				else:
					# Only real Atom instances are allowed past this point.
					continue
			else:
				if x.blocker and x.blocker.overlap.forbid and \
					eapi in ("0", "1") and portage.dep._dep_check_strict:
					raise ParseError(
						_("invalid atom: '%s'") % (x,))
				if x.use and eapi in ("0", "1") and \
					portage.dep._dep_check_strict:
					raise ParseError(
						_("invalid atom: '%s'") % (x,))

		if repoman and x.use and x.use.conditional:
			evaluated_atom = remove_slot(x)
			if x.slot:
				evaluated_atom += ":%s" % x.slot
			evaluated_atom += str(x.use._eval_qa_conditionals(
				use_mask, use_force))
			x = Atom(evaluated_atom)

		if not repoman and \
			myuse is not None and isinstance(x, Atom) and x.use:
			if x.use.conditional:
				x = x.evaluate_conditionals(myuse)

		mykey = x.cp
		if not mykey.startswith("virtual/"):
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue
		mychoices = myvirtuals.get(mykey, [])
		if x.blocker:
			# Virtual blockers are no longer expanded here since
			# the un-expanded virtual atom is more useful for
			# maintaining a cache of blocker atoms.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue

		if repoman or not hasattr(portdb, 'match_pkgs'):
			if portdb.cp_list(x.cp):
				newsplit.append(x)
			else:
				# TODO: Add PROVIDE check for repoman.
				a = []
				for y in mychoices:
					a.append(Atom(x.replace(x.cp, y.cp, 1)))
				if not a:
					newsplit.append(x)
				elif len(a) == 1:
					newsplit.append(a[0])
				else:
					newsplit.append(['||'] + a)
			continue

		pkgs = []
		# Ignore USE deps here, since otherwise we might not
		# get any matches. Choices with correct USE settings
		# will be preferred in dep_zapdeps().
		matches = portdb.match_pkgs(x.without_use)
		# Use descending order to prefer higher versions.
		matches.reverse()
		for pkg in matches:
			# only use new-style matches
			if pkg.cp.startswith("virtual/"):
				pkgs.append(pkg)
		if not (pkgs or mychoices):
			# This one couldn't be expanded as a new-style virtual.  Old-style
			# virtuals have already been expanded by dep_virtual, so this one
			# is unavailable and dep_zapdeps will identify it as such.  The
			# atom is not eliminated here since it may still represent a
			# dependency that needs to be satisfied.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue

		a = []
		for pkg in pkgs:
			virt_atom = '=' + pkg.cpv
			if x.use:
				virt_atom += str(x.use)
			virt_atom = Atom(virt_atom)
			# According to GLEP 37, RDEPEND is the only dependency
			# type that is valid for new-style virtuals. Repoman
			# should enforce this.
			depstring = pkg.metadata['RDEPEND']
			pkg_kwargs = kwargs.copy()
			pkg_kwargs["myuse"] = pkg.use.enabled
			if edebug:
				writemsg_level(_("Virtual Parent:      %s\n") \
					% (pkg,), noiselevel=-1, level=logging.DEBUG)
				writemsg_level(_("Virtual Depstring:   %s\n") \
					% (depstring,), noiselevel=-1, level=logging.DEBUG)

			# Set EAPI used for validation in dep_check() recursion.
			mytrees["virt_parent"] = (pkg, virt_atom)

			try:
				mycheck = dep_check(depstring, mydbapi, mysettings,
					myroot=myroot, trees=trees, **pkg_kwargs)
			finally:
				# Restore previous EAPI after recursion.
				if virt_parent is not None:
					mytrees["virt_parent"] = virt_parent
				else:
					del mytrees["virt_parent"]

			if not mycheck[0]:
				raise ParseError(
					"%s: %s '%s'" % (y[0], mycheck[1], depstring))

			# pull in the new-style virtual
			mycheck[1].append(virt_atom)
			a.append(mycheck[1])
			if atom_graph is not None:
				atom_graph.add(virt_atom, graph_parent)
		# Plain old-style virtuals.  New-style virtuals are preferred.
		if not pkgs:
				for y in mychoices:
					new_atom = Atom(x.replace(x.cp, y.cp, 1))
					matches = portdb.match(new_atom)
					# portdb is an instance of depgraph._dep_check_composite_db, so
					# USE conditionals are already evaluated.
					if matches and mykey in \
						portdb.aux_get(matches[-1], ['PROVIDE'])[0].split():
						a.append(new_atom)
						if atom_graph is not None:
							atom_graph.add(new_atom, graph_parent)

		if not a and mychoices:
			# Check for a virtual package.provided match.
			for y in mychoices:
				new_atom = Atom(x.replace(x.cp, y.cp, 1))
				if match_from_list(new_atom,
					pprovideddict.get(new_atom.cp, [])):
					a.append(new_atom)
					if atom_graph is not None:
						atom_graph.add(new_atom, graph_parent)

		if not a:
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
		elif len(a) == 1:
			newsplit.append(a[0])
		else:
			newsplit.append(['||'] + a)

	return newsplit

def dep_eval(deplist):
	if not deplist:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if isinstance(x, list):
				if dep_eval(x)==1:
					return 1
			elif x==1:
					return 1
		#XXX: unless there's no available atoms in the list
		#in which case we need to assume that everything is
		#okay as some ebuilds are relying on an old bug.
		if len(deplist) == 1:
			return 1
		return 0
	else:
		for x in deplist:
			if isinstance(x, list):
				if dep_eval(x)==0:
					return 0
			elif x==0 or x==2:
				return 0
		return 1

def dep_zapdeps(unreduced, reduced, myroot, use_binaries=0, trees=None):
	"""
	Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies.
	"""
	if trees is None:
		trees = portage.db
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if not reduced or unreduced == ["||"] or dep_eval(reduced):
		return []

	if unreduced[0] != "||":
		unresolved = []
		for x, satisfied in zip(unreduced, reduced):
			if isinstance(x, list):
				unresolved += dep_zapdeps(x, satisfied, myroot,
					use_binaries=use_binaries, trees=trees)
			elif not satisfied:
				unresolved.append(x)
		return unresolved

	# We're at a ( || atom ... ) type level and need to make a choice
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	# Our preference order is for an the first item that:
	# a) contains all unmasked packages with the same key as installed packages
	# b) contains all unmasked packages
	# c) contains masked installed packages
	# d) is the first item

	preferred_installed = []
	preferred_in_graph = []
	preferred_any_slot = []
	preferred_non_installed = []
	unsat_use_in_graph = []
	unsat_use_installed = []
	unsat_use_non_installed = []
	other = []

	# unsat_use_* must come after preferred_non_installed
	# for correct ordering in cases like || ( foo[a] foo[b] ).
	choice_bins = (
		preferred_in_graph,
		preferred_installed,
		preferred_any_slot,
		preferred_non_installed,
		unsat_use_in_graph,
		unsat_use_installed,
		unsat_use_non_installed,
		other,
	)

	# Alias the trees we'll be checking availability against
	parent   = trees[myroot].get("parent")
	priority = trees[myroot].get("priority")
	graph_db = trees[myroot].get("graph_db")
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	# Sort the deps into installed, not installed but already 
	# in the graph and other, not installed and not in the graph
	# and other, with values of [[required_atom], availablility]
	for x, satisfied in zip(deps, satisfieds):
		if isinstance(x, list):
			atoms = dep_zapdeps(x, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [x]
		if vardb is None:
			# When called by repoman, we can simply return the first choice
			# because dep_eval() handles preference selection.
			return atoms

		all_available = True
		all_use_satisfied = True
		slot_map = {}
		cp_map = {}
		for atom in atoms:
			if atom.blocker:
				continue
			# Ignore USE dependencies here since we don't want USE
			# settings to adversely affect || preference evaluation.
			avail_pkg = mydbapi.match(atom.without_use)
			if avail_pkg:
				avail_pkg = avail_pkg[-1] # highest (ascending order)
				avail_slot = Atom("%s:%s" % (atom.cp,
					mydbapi.aux_get(avail_pkg, ["SLOT"])[0]))
			if not avail_pkg:
				all_available = False
				all_use_satisfied = False
				break

			if atom.use:
				avail_pkg_use = mydbapi.match(atom)
				if not avail_pkg_use:
					all_use_satisfied = False
				else:
					# highest (ascending order)
					avail_pkg_use = avail_pkg_use[-1]
					if avail_pkg_use != avail_pkg:
						avail_pkg = avail_pkg_use
						avail_slot = Atom("%s:%s" % (atom.cp,
							mydbapi.aux_get(avail_pkg, ["SLOT"])[0]))

			slot_map[avail_slot] = avail_pkg
			pkg_cp = cpv_getkey(avail_pkg)
			highest_cpv = cp_map.get(pkg_cp)
			if highest_cpv is None or \
				pkgcmp(catpkgsplit(avail_pkg)[1:],
				catpkgsplit(highest_cpv)[1:]) > 0:
				cp_map[pkg_cp] = avail_pkg

		this_choice = (atoms, slot_map, cp_map, all_available)
		if all_available:
			# The "all installed" criterion is not version or slot specific.
			# If any version of a package is already in the graph then we
			# assume that it is preferred over other possible packages choices.
			all_installed = True
			for atom in set(Atom(atom.cp) for atom in atoms \
				if not atom.blocker):
				# New-style virtuals have zero cost to install.
				if not vardb.match(atom) and not atom.startswith("virtual/"):
					all_installed = False
					break
			all_installed_slots = False
			if all_installed:
				all_installed_slots = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if not vardb.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_installed_slots = False
						break
			if graph_db is None:
				if all_use_satisfied:
					if all_installed:
						if all_installed_slots:
							preferred_installed.append(this_choice)
						else:
							preferred_any_slot.append(this_choice)
					else:
						preferred_non_installed.append(this_choice)
				else:
					if all_installed_slots:
						unsat_use_installed.append(this_choice)
					else:
						unsat_use_non_installed.append(this_choice)
			else:
				all_in_graph = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if not graph_db.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_in_graph = False
						break
				circular_atom = None
				if all_in_graph:
					if parent is None or priority is None:
						pass
					elif priority.buildtime:
						# Check if the atom would result in a direct circular
						# dependency and try to avoid that if it seems likely
						# to be unresolvable. This is only relevant for
						# buildtime deps that aren't already satisfied by an
						# installed package.
						cpv_slot_list = [parent]
						for atom in atoms:
							if atom.blocker:
								continue
							if vardb.match(atom):
								# If the atom is satisfied by an installed
								# version then it's not a circular dep.
								continue
							if atom.cp != parent.cp:
								continue
							if match_from_list(atom, cpv_slot_list):
								circular_atom = atom
								break
				if circular_atom is not None:
					other.append(this_choice)
				else:
					if all_use_satisfied:
						if all_in_graph:
							preferred_in_graph.append(this_choice)
						elif all_installed:
							if all_installed_slots:
								preferred_installed.append(this_choice)
							else:
								preferred_any_slot.append(this_choice)
						else:
							preferred_non_installed.append(this_choice)
					else:
						if all_in_graph:
							unsat_use_in_graph.append(this_choice)
						elif all_installed_slots:
							unsat_use_installed.append(this_choice)
						else:
							unsat_use_non_installed.append(this_choice)
		else:
			other.append(this_choice)

	# Prefer choices which contain upgrades to higher slots. This helps
	# for deps such as || ( foo:1 foo:2 ), where we want to prefer the
	# atom which matches the higher version rather than the atom furthest
	# to the left. Sorting is done separately for each of choice_bins, so
	# as not to interfere with the ordering of the bins. Because of the
	# bin separation, the main function of this code is to allow
	# --depclean to remove old slots (rather than to pull in new slots).
	for choices in choice_bins:
		if len(choices) < 2:
			continue
		for choice_1 in choices[1:]:
			atoms_1, slot_map_1, cp_map_1, all_available_1 = choice_1
			cps = set(cp_map_1)
			for choice_2 in choices:
				if choice_1 is choice_2:
					# choice_1 will not be promoted, so move on
					break
				atoms_2, slot_map_2, cp_map_2, all_available_2 = choice_2
				intersecting_cps = cps.intersection(cp_map_2)
				if not intersecting_cps:
					continue
				has_upgrade = False
				has_downgrade = False
				for cp in intersecting_cps:
					version_1 = cp_map_1[cp]
					version_2 = cp_map_2[cp]
					difference = pkgcmp(catpkgsplit(version_1)[1:],
						catpkgsplit(version_2)[1:])
					if difference != 0:
						if difference > 0:
							has_upgrade = True
						else:
							has_downgrade = True
							break
				if has_upgrade and not has_downgrade:
					# promote choice_1 in front of choice_2
					choices.remove(choice_1)
					index_2 = choices.index(choice_2)
					choices.insert(index_2, choice_1)
					break

	for allow_masked in (False, True):
		for choices in choice_bins:
			for atoms, slot_map, cp_map, all_available in choices:
				if all_available or allow_masked:
					return atoms

	assert(False) # This point should not be reachable

def dep_check(depstring, mydbapi, mysettings, use="yes", mode=None, myuse=None,
	use_cache=1, use_binaries=0, myroot="/", trees=None):
	"""Takes a depend string and parses the condition."""
	edebug = mysettings.get("PORTAGE_DEBUG", None) == "1"
	#check_config_instance(mysettings)
	if trees is None:
		trees = globals()["db"]
	if use=="yes":
		if myuse is None:
			#default behavior
			myusesplit = mysettings["PORTAGE_USE"].split()
		else:
			myusesplit = myuse
			# We've been given useflags to use.
			#print "USE FLAGS PASSED IN."
			#print myuse
			#if "bindist" in myusesplit:
			#	print "BINDIST is set!"
			#else:
			#	print "BINDIST NOT set."
	else:
		#we are being run by autouse(), don't consult USE vars yet.
		# WE ALSO CANNOT USE SETTINGS
		myusesplit=[]

	#convert parenthesis to sublists
	try:
		mysplit = paren_reduce(depstring)
	except InvalidDependString as e:
		return [0, str(e)]

	mymasks = set()
	useforce = set()
	useforce.add(mysettings["ARCH"])
	if use == "all":
		# This masking/forcing is only for repoman.  In other cases, relevant
		# masking/forcing should have already been applied via
		# config.regenerate().  Also, binary or installed packages may have
		# been built with flags that are now masked, and it would be
		# inconsistent to mask them now.  Additionally, myuse may consist of
		# flags from a parent package that is being merged to a $ROOT that is
		# different from the one that mysettings represents.
		mymasks.update(mysettings.usemask)
		mymasks.update(mysettings.archlist())
		mymasks.discard(mysettings["ARCH"])
		useforce.update(mysettings.useforce)
		useforce.difference_update(mymasks)
	try:
		mysplit = use_reduce(mysplit, uselist=myusesplit,
			masklist=mymasks, matchall=(use=="all"), excludeall=useforce)
	except InvalidDependString as e:
		return [0, str(e)]

	# Do the || conversions
	mysplit = dep_opconvert(mysplit)

	if mysplit == []:
		#dependencies were reduced to nothing
		return [1,[]]

	# Recursively expand new-style virtuals so as to
	# collapse one or more levels of indirection.
	try:
		mysplit = _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings,
			use=use, mode=mode, myuse=myuse,
			use_force=useforce, use_mask=mymasks, use_cache=use_cache,
			use_binaries=use_binaries, myroot=myroot, trees=trees)
	except ParseError as e:
		return [0, str(e)]

	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0, _("Invalid token")]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	try:
		selected_atoms = dep_zapdeps(mysplit, mysplit2, myroot,
			use_binaries=use_binaries, trees=trees)
	except InvalidAtom as e:
		if portage.dep._dep_check_strict:
			raise # This shouldn't happen.
		# dbapi.match() failed due to an invalid atom in
		# the dependencies of an installed package.
		return [0, _("Invalid atom: '%s'") % (e,)]

	return [1, selected_atoms]

def dep_wordreduce(mydeplist,mysettings,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	deplist=mydeplist[:]
	for mypos, token in enumerate(deplist):
		if isinstance(deplist[mypos], list):
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mysettings,mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		elif token[:1] == "!":
			deplist[mypos] = False
		else:
			mykey = deplist[mypos].cp
			if mysettings and mykey in mysettings.pprovideddict and \
			        match_from_list(deplist[mypos], mysettings.pprovideddict[mykey]):
				deplist[mypos]=True
			elif mydbapi is None:
				# Assume nothing is satisfied.  This forces dep_zapdeps to
				# return all of deps the deps that have been selected
				# (excluding those satisfied by package.provided).
				deplist[mypos] = False
			else:
				if mode:
					x = mydbapi.xmatch(mode, deplist[mypos])
					if mode.startswith("minimum-"):
						mydep = []
						if x:
							mydep.append(x)
					else:
						mydep = x
				else:
					mydep=mydbapi.match(deplist[mypos],use_cache=use_cache)
				if mydep!=None:
					tmp=(len(mydep)>=1)
					if deplist[mypos][0]=="!":
						tmp=False
					deplist[mypos]=tmp
				else:
					#encountered invalid string
					return None
	return deplist
