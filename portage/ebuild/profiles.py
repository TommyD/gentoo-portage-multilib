# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.config import profiles
import os, logging
from portage.util.lists import unique
from portage.util.file import iter_read_bash, read_dict, read_bash_dict
from portage.package.atom import atom
from portage.config.central import list_parser

class OnDiskProfile(profiles.base):
	positional = ("base_repo","profile")
	required = ("base_repo", "profile")
	section_ref = ("base_repo")

	def __init__(self, base_repo, profile, incrementals=[]):
		basepath = os.path.join(base_repo.base,"profiles")

		dep_path = os.path.join(basepath, profile, "deprecated")
		if os.path.isfile(dep_path):
			logger.warn("profile '%s' is marked as deprecated, read '%s' please" % (profile, dep_path))
		del dep_path

		parents = [None]
		stack = [os.path.join(basepath, profile.strip())]
		idx = 0

		while len(stack) > idx:
			parent, trg = parents[idx], stack[idx]

			if not os.path.isdir(trg):
				if parent:
					raise profiles.ProfileException("%s doesn't exist, or isn't a dir, referenced by %s" % (trg, parent))
				raise profiles.ProfileException("%s doesn't exist, or isn't a dir" % trg)

			fp = os.path.join(trg, "parent")
			if os.path.isfile(fp):
				l = []
				try:
					f = open(fp,"r")
				except (IOError, OSError):
					raise profiles.ProfileException("failed reading parent from %s" % path)
				for x in f:
					x = x.strip()
					if x.startswith("#") or x == "":
						continue
					l.append(x)
				f.close()
				l.reverse()
				for x in l:
					stack.append(os.path.abspath(os.path.join(trg, x)))
					parents.append(trg)
				del l
			
			idx+=1

		del parents

		# build up visibility limiters.

		stack.reverse()
		pkgs = {}
		for fp in [os.path.join(prof, "packages") for prof in stack]:
			if os.path.exists(fp):
				try:	i = iter_read_bash(os.path.join(prof, "packages"))
				except (IOError, OSError), e:
					raise profiles.ProfileException("failed reading '%s': %s" % (e.filename, str(e)))
				for p in i:
					if p[0] == "-":
						try:	del pkgs[p[0]]
						except KeyError:
							logger.warn("%s is reversed in %s, but isn't set yet!" % (p[1:], fp))
					else:
						pkgs[p] = None

		visibility = []
		sys = []
		for p in pkgs.keys():
			if p[0] == "*":
				# system set.
				sys.append(atom(p[1:]))
			else:
				# note the negation.  this means cat/pkg matchs, but ver must not, else it's masked.
				visibility.append(atom(p, negate_vers=True))
		del pkgs
		self.sys = sys
		self.visibility = visibility

		fp = os.path.join(basepath, "thirdpartymirrors")
		if os.path.isfile(fp):
			mirrors = read_dict(fp, splitter='\t')
		else:
			mirrors = {}

		maskers = []

		for fp in [os.path.join(prof, "package.mask") for prof in stack + [basepath]]:
			if os.path.exists(fp):
				try:	maskers.extend(map(atom, iter_read_bash(fp)))
				except (IOError, OSError), e:
					raise profiles.ProfileException("failed reading '%s': %s" % (fp, str(e)))

		self.maskers = maskers
		confs = [{}] # oh yay.
		for fp in [os.path.join(prof, "make.defaults") for prof in stack]:
			if os.path.exists(fp):
				try:	confs.append(read_bash_dict(fp, vars_dict=confs[-1]))
				except (IOError, OSError), e:
					raise profiles.ProfileException("failed reading '%s': %s" % (fp, str(e)))
		d = {}
		confs.pop(0)
		for dc in confs:
			for k,v in dc.items():
				# potentially make incrementals a dict for ~O(1) here, rather then O(N)
				if k in incrementals:
					v = list_parser(dc[k])
					if k in d:		d[k] += v
					else:				d[k] = v
				else:					d[k] = v

		del confs
		# use_expand
		d["USE_EXPAND"] = d.get("USE_EXPAND",'').split()
		for u in d["USE_EXPAND"]:
			u2 = u.lower()+"_"
			if u in d:
				d["USE"].extend(map(u2.__add__, d[u].split()))
				del d[u]

		# collapsed make.defaults.  now chunkify the bugger.
		self.conf = d

		
