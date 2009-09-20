# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import logging
import sys
import textwrap
from itertools import izip
import portage
from portage import os
from portage.output import bold, colorize, darkgreen, green
from portage.sets import SETPREFIX
from portage.util import cmp_sort_key

from _emerge.emergelog import emergelog
from _emerge.Package import Package
from _emerge.UninstallFailure import UninstallFailure
from _emerge.userquery import userquery
from _emerge.countdown import countdown

def unmerge(root_config, myopts, unmerge_action,
	unmerge_files, ldpath_mtimes, autoclean=0,
	clean_world=1, clean_delay=1, ordered=0, raise_on_error=0,
	scheduler=None, writemsg_level=portage.util.writemsg_level):

	if clean_world:
		clean_world = myopts.get('--deselect') != 'n'
	quiet = "--quiet" in myopts
	settings = root_config.settings
	sets = root_config.sets
	vartree = root_config.trees["vartree"]
	candidate_catpkgs=[]
	global_unmerge=0
	xterm_titles = "notitles" not in settings.features
	out = portage.output.EOutput()
	pkg_cache = {}
	db_keys = list(vartree.dbapi._aux_cache_keys)

	def _pkg(cpv):
		pkg = pkg_cache.get(cpv)
		if pkg is None:
			pkg = Package(cpv=cpv, installed=True,
				metadata=izip(db_keys, vartree.dbapi.aux_get(cpv, db_keys)),
				root_config=root_config,
				type_name="installed")
			pkg_cache[cpv] = pkg
		return pkg

	vdb_path = os.path.join(settings["ROOT"], portage.VDB_PATH)
	try:
		# At least the parent needs to exist for the lock file.
		portage.util.ensure_dirs(vdb_path)
	except portage.exception.PortageException:
		pass
	vdb_lock = None
	try:
		if os.access(vdb_path, os.W_OK):
			vdb_lock = portage.locks.lockdir(vdb_path)
		realsyslist = sets["system"].getAtoms()
		syslist = []
		for x in realsyslist:
			mycp = portage.dep_getkey(x)
			if mycp in settings.getvirtuals():
				providers = []
				for provider in settings.getvirtuals()[mycp]:
					if vartree.dbapi.match(provider):
						providers.append(provider)
				if len(providers) == 1:
					syslist.extend(providers)
			else:
				syslist.append(mycp)
	
		mysettings = portage.config(clone=settings)
	
		if not unmerge_files:
			if unmerge_action == "unmerge":
				print
				print bold("emerge unmerge") + " can only be used with specific package names"
				print
				return 0
			else:
				global_unmerge = 1
	
		localtree = vartree
		# process all arguments and add all
		# valid db entries to candidate_catpkgs
		if global_unmerge:
			if not unmerge_files:
				candidate_catpkgs.extend(vartree.dbapi.cp_all())
		else:
			#we've got command-line arguments
			if not unmerge_files:
				print "\nNo packages to unmerge have been provided.\n"
				return 0
			for x in unmerge_files:
				arg_parts = x.split('/')
				if x[0] not in [".","/"] and \
					arg_parts[-1][-7:] != ".ebuild":
					#possible cat/pkg or dep; treat as such
					candidate_catpkgs.append(x)
				elif unmerge_action in ["prune","clean"]:
					print "\n!!! Prune and clean do not accept individual" + \
						" ebuilds as arguments;\n    skipping.\n"
					continue
				else:
					# it appears that the user is specifying an installed
					# ebuild and we're in "unmerge" mode, so it's ok.
					if not os.path.exists(x):
						print "\n!!! The path '"+x+"' doesn't exist.\n"
						return 0
	
					absx   = os.path.abspath(x)
					sp_absx = absx.split("/")
					if sp_absx[-1][-7:] == ".ebuild":
						del sp_absx[-1]
						absx = "/".join(sp_absx)
	
					sp_absx_len = len(sp_absx)
	
					vdb_path = os.path.join(settings["ROOT"], portage.VDB_PATH)
					vdb_len  = len(vdb_path)
	
					sp_vdb     = vdb_path.split("/")
					sp_vdb_len = len(sp_vdb)
	
					if not os.path.exists(absx+"/CONTENTS"):
						print "!!! Not a valid db dir: "+str(absx)
						return 0
	
					if sp_absx_len <= sp_vdb_len:
						# The Path is shorter... so it can't be inside the vdb.
						print sp_absx
						print absx
						print "\n!!!",x,"cannot be inside "+ \
							vdb_path+"; aborting.\n"
						return 0
	
					for idx in range(0,sp_vdb_len):
						if idx >= sp_absx_len or sp_vdb[idx] != sp_absx[idx]:
							print sp_absx
							print absx
							print "\n!!!", x, "is not inside "+\
								vdb_path+"; aborting.\n"
							return 0
	
					print "="+"/".join(sp_absx[sp_vdb_len:])
					candidate_catpkgs.append(
						"="+"/".join(sp_absx[sp_vdb_len:]))
	
		newline=""
		if (not "--quiet" in myopts):
			newline="\n"
		if settings["ROOT"] != "/":
			writemsg_level(darkgreen(newline+ \
				">>> Using system located in ROOT tree %s\n" % \
				settings["ROOT"]))

		if (("--pretend" in myopts) or ("--ask" in myopts)) and \
			not ("--quiet" in myopts):
			writemsg_level(darkgreen(newline+\
				">>> These are the packages that would be unmerged:\n"))

		# Preservation of order is required for --depclean and --prune so
		# that dependencies are respected. Use all_selected to eliminate
		# duplicate packages since the same package may be selected by
		# multiple atoms.
		pkgmap = []
		all_selected = set()
		for x in candidate_catpkgs:
			# cycle through all our candidate deps and determine
			# what will and will not get unmerged
			try:
				mymatch = vartree.dbapi.match(x)
			except portage.exception.AmbiguousPackageName, errpkgs:
				print "\n\n!!! The short ebuild name \"" + \
					x + "\" is ambiguous.  Please specify"
				print "!!! one of the following fully-qualified " + \
					"ebuild names instead:\n"
				for i in errpkgs[0]:
					print "    " + green(i)
				print
				sys.exit(1)
	
			if not mymatch and x[0] not in "<>=~":
				mymatch = localtree.dep_match(x)
			if not mymatch:
				portage.writemsg("\n--- Couldn't find '%s' to %s.\n" % \
					(x, unmerge_action), noiselevel=-1)
				continue

			pkgmap.append(
				{"protected": set(), "selected": set(), "omitted": set()})
			mykey = len(pkgmap) - 1
			if unmerge_action=="unmerge":
					for y in mymatch:
						if y not in all_selected:
							pkgmap[mykey]["selected"].add(y)
							all_selected.add(y)
			elif unmerge_action == "prune":
				if len(mymatch) == 1:
					continue
				best_version = mymatch[0]
				best_slot = vartree.getslot(best_version)
				best_counter = vartree.dbapi.cpv_counter(best_version)
				for mypkg in mymatch[1:]:
					myslot = vartree.getslot(mypkg)
					mycounter = vartree.dbapi.cpv_counter(mypkg)
					if (myslot == best_slot and mycounter > best_counter) or \
						mypkg == portage.best([mypkg, best_version]):
						if myslot == best_slot:
							if mycounter < best_counter:
								# On slot collision, keep the one with the
								# highest counter since it is the most
								# recently installed.
								continue
						best_version = mypkg
						best_slot = myslot
						best_counter = mycounter
				pkgmap[mykey]["protected"].add(best_version)
				pkgmap[mykey]["selected"].update(mypkg for mypkg in mymatch \
					if mypkg != best_version and mypkg not in all_selected)
				all_selected.update(pkgmap[mykey]["selected"])
			else:
				# unmerge_action == "clean"
				slotmap={}
				for mypkg in mymatch:
					if unmerge_action == "clean":
						myslot = localtree.getslot(mypkg)
					else:
						# since we're pruning, we don't care about slots
						# and put all the pkgs in together
						myslot = 0
					if myslot not in slotmap:
						slotmap[myslot] = {}
					slotmap[myslot][localtree.dbapi.cpv_counter(mypkg)] = mypkg

				for mypkg in vartree.dbapi.cp_list(
					portage.dep_getkey(mymatch[0])):
					myslot = vartree.getslot(mypkg)
					if myslot not in slotmap:
						slotmap[myslot] = {}
					slotmap[myslot][vartree.dbapi.cpv_counter(mypkg)] = mypkg

				for myslot in slotmap:
					counterkeys = slotmap[myslot].keys()
					if not counterkeys:
						continue
					counterkeys.sort()
					pkgmap[mykey]["protected"].add(
						slotmap[myslot][counterkeys[-1]])
					del counterkeys[-1]

					for counter in counterkeys[:]:
						mypkg = slotmap[myslot][counter]
						if mypkg not in mymatch:
							counterkeys.remove(counter)
							pkgmap[mykey]["protected"].add(
								slotmap[myslot][counter])

					#be pretty and get them in order of merge:
					for ckey in counterkeys:
						mypkg = slotmap[myslot][ckey]
						if mypkg not in all_selected:
							pkgmap[mykey]["selected"].add(mypkg)
							all_selected.add(mypkg)
					# ok, now the last-merged package
					# is protected, and the rest are selected
		numselected = len(all_selected)
		if global_unmerge and not numselected:
			portage.writemsg_stdout("\n>>> No outdated packages were found on your system.\n")
			return 0
	
		if not numselected:
			portage.writemsg_stdout(
				"\n>>> No packages selected for removal by " + \
				unmerge_action + "\n")
			return 0
	finally:
		if vdb_lock:
			vartree.dbapi.flush_cache()
			portage.locks.unlockdir(vdb_lock)
	
	from portage.sets.base import EditablePackageSet
	
	# generate a list of package sets that are directly or indirectly listed in "world",
	# as there is no persistent list of "installed" sets
	installed_sets = ["world"]
	stop = False
	pos = 0
	while not stop:
		stop = True
		pos = len(installed_sets)
		for s in installed_sets[pos - 1:]:
			if s not in sets:
				continue
			candidates = [x[len(SETPREFIX):] for x in sets[s].getNonAtoms() if x.startswith(SETPREFIX)]
			if candidates:
				stop = False
				installed_sets += candidates
	installed_sets = [x for x in installed_sets if x not in root_config.setconfig.active]
	del stop, pos

	# we don't want to unmerge packages that are still listed in user-editable package sets
	# listed in "world" as they would be remerged on the next update of "world" or the 
	# relevant package sets.
	unknown_sets = set()
	for cp in xrange(len(pkgmap)):
		for cpv in pkgmap[cp]["selected"].copy():
			try:
				pkg = _pkg(cpv)
			except KeyError:
				# It could have been uninstalled
				# by a concurrent process.
				continue

			if unmerge_action != "clean" and \
				root_config.root == "/" and \
				portage.match_from_list(
				portage.const.PORTAGE_PACKAGE_ATOM, [pkg]):
				msg = ("Not unmerging package %s since there is no valid " + \
				"reason for portage to unmerge itself.") % (pkg.cpv,)
				for line in textwrap.wrap(msg, 75):
					out.eerror(line)
				# adjust pkgmap so the display output is correct
				pkgmap[cp]["selected"].remove(cpv)
				all_selected.remove(cpv)
				pkgmap[cp]["protected"].add(cpv)
				continue

			parents = []
			for s in installed_sets:
				# skip sets that the user requested to unmerge, and skip world 
				# unless we're unmerging a package set (as the package would be 
				# removed from "world" later on)
				if s in root_config.setconfig.active or (s == "world" and not root_config.setconfig.active):
					continue

				if s not in sets:
					if s in unknown_sets:
						continue
					unknown_sets.add(s)
					out = portage.output.EOutput()
					out.eerror(("Unknown set '@%s' in %s%s") % \
						(s, root_config.root, portage.const.WORLD_SETS_FILE))
					continue

				# only check instances of EditablePackageSet as other classes are generally used for
				# special purposes and can be ignored here (and are usually generated dynamically, so the
				# user can't do much about them anyway)
				if isinstance(sets[s], EditablePackageSet):

					# This is derived from a snippet of code in the
					# depgraph._iter_atoms_for_pkg() method.
					for atom in sets[s].iterAtomsForPackage(pkg):
						inst_matches = vartree.dbapi.match(atom)
						inst_matches.reverse() # descending order
						higher_slot = None
						for inst_cpv in inst_matches:
							try:
								inst_pkg = _pkg(inst_cpv)
							except KeyError:
								# It could have been uninstalled
								# by a concurrent process.
								continue

							if inst_pkg.cp != atom.cp:
								continue
							if pkg >= inst_pkg:
								# This is descending order, and we're not
								# interested in any versions <= pkg given.
								break
							if pkg.slot_atom != inst_pkg.slot_atom:
								higher_slot = inst_pkg
								break
						if higher_slot is None:
							parents.append(s)
							break
			if parents:
				#print colorize("WARN", "Package %s is going to be unmerged," % cpv)
				#print colorize("WARN", "but still listed in the following package sets:")
				#print "    %s\n" % ", ".join(parents)
				print colorize("WARN", "Not unmerging package %s as it is" % cpv)
				print colorize("WARN", "still referenced by the following package sets:")
				print "    %s\n" % ", ".join(parents)
				# adjust pkgmap so the display output is correct
				pkgmap[cp]["selected"].remove(cpv)
				all_selected.remove(cpv)
				pkgmap[cp]["protected"].add(cpv)
	
	del installed_sets

	numselected = len(all_selected)
	if not numselected:
		writemsg_level(
			"\n>>> No packages selected for removal by " + \
			unmerge_action + "\n")
		return 0

	# Unmerge order only matters in some cases
	if not ordered:
		unordered = {}
		for d in pkgmap:
			selected = d["selected"]
			if not selected:
				continue
			cp = portage.cpv_getkey(iter(selected).next())
			cp_dict = unordered.get(cp)
			if cp_dict is None:
				cp_dict = {}
				unordered[cp] = cp_dict
				for k in d:
					cp_dict[k] = set()
			for k, v in d.iteritems():
				cp_dict[k].update(v)
		pkgmap = [unordered[cp] for cp in sorted(unordered)]

	for x in xrange(len(pkgmap)):
		selected = pkgmap[x]["selected"]
		if not selected:
			continue
		for mytype, mylist in pkgmap[x].iteritems():
			if mytype == "selected":
				continue
			mylist.difference_update(all_selected)
		cp = portage.cpv_getkey(iter(selected).next())
		for y in localtree.dep_match(cp):
			if y not in pkgmap[x]["omitted"] and \
				y not in pkgmap[x]["selected"] and \
				y not in pkgmap[x]["protected"] and \
				y not in all_selected:
				pkgmap[x]["omitted"].add(y)
		if global_unmerge and not pkgmap[x]["selected"]:
			#avoid cluttering the preview printout with stuff that isn't getting unmerged
			continue
		if not (pkgmap[x]["protected"] or pkgmap[x]["omitted"]) and cp in syslist:
			writemsg_level(colorize("BAD","\a\n\n!!! " + \
				"'%s' is part of your system profile.\n" % cp),
				level=logging.WARNING, noiselevel=-1)
			writemsg_level(colorize("WARN","\a!!! Unmerging it may " + \
				"be damaging to your system.\n\n"),
				level=logging.WARNING, noiselevel=-1)
			if clean_delay and "--pretend" not in myopts and "--ask" not in myopts:
				countdown(int(settings["EMERGE_WARNING_DELAY"]),
					colorize("UNMERGE_WARN", "Press Ctrl-C to Stop"))
		if not quiet:
			writemsg_level("\n %s\n" % (bold(cp),), noiselevel=-1)
		else:
			writemsg_level(bold(cp) + ": ", noiselevel=-1)
		for mytype in ["selected","protected","omitted"]:
			if not quiet:
				writemsg_level((mytype + ": ").rjust(14), noiselevel=-1)
			if pkgmap[x][mytype]:
				sorted_pkgs = [portage.catpkgsplit(mypkg)[1:] for mypkg in pkgmap[x][mytype]]
				sorted_pkgs.sort(key=cmp_sort_key(portage.pkgcmp))
				for pn, ver, rev in sorted_pkgs:
					if rev == "r0":
						myversion = ver
					else:
						myversion = ver + "-" + rev
					if mytype == "selected":
						writemsg_level(
							colorize("UNMERGE_WARN", myversion + " "),
							noiselevel=-1)
					else:
						writemsg_level(
							colorize("GOOD", myversion + " "), noiselevel=-1)
			else:
				writemsg_level("none ", noiselevel=-1)
			if not quiet:
				writemsg_level("\n", noiselevel=-1)
		if quiet:
			writemsg_level("\n", noiselevel=-1)

	writemsg_level("\n>>> " + colorize("UNMERGE_WARN", "'Selected'") + \
		" packages are slated for removal.\n")
	writemsg_level(">>> " + colorize("GOOD", "'Protected'") + \
			" and " + colorize("GOOD", "'omitted'") + \
			" packages will not be removed.\n\n")

	if "--pretend" in myopts:
		#we're done... return
		return 0
	if "--ask" in myopts:
		if userquery("Would you like to unmerge these packages?")=="No":
			# enter pretend mode for correct formatting of results
			myopts["--pretend"] = True
			print
			print "Quitting."
			print
			return 0
	#the real unmerging begins, after a short delay....
	if clean_delay and not autoclean:
		countdown(int(settings["CLEAN_DELAY"]), ">>> Unmerging")

	for x in xrange(len(pkgmap)):
		for y in pkgmap[x]["selected"]:
			writemsg_level(">>> Unmerging "+y+"...\n", noiselevel=-1)
			emergelog(xterm_titles, "=== Unmerging... ("+y+")")
			mysplit = y.split("/")
			#unmerge...
			retval = portage.unmerge(mysplit[0], mysplit[1], settings["ROOT"],
				mysettings, unmerge_action not in ["clean","prune"],
				vartree=vartree, ldpath_mtimes=ldpath_mtimes,
				scheduler=scheduler)

			if retval != os.EX_OK:
				emergelog(xterm_titles, " !!! unmerge FAILURE: "+y)
				if raise_on_error:
					raise UninstallFailure(retval)
				sys.exit(retval)
			else:
				if clean_world and hasattr(sets["world"], "cleanPackage")\
						and hasattr(sets["world"], "lock"):
					sets["world"].lock()
					if hasattr(sets["world"], "load"):
						sets["world"].load()
					sets["world"].cleanPackage(vartree.dbapi, y)
					sets["world"].unlock()
				emergelog(xterm_titles, " >>> unmerge success: "+y)

	if clean_world and hasattr(sets["world"], "remove")\
			and hasattr(sets["world"], "lock"):
		sets["world"].lock()
		# load is called inside remove()
		for s in root_config.setconfig.active:
			sets["world"].remove(SETPREFIX+s)
		sets["world"].unlock()

	return 1

