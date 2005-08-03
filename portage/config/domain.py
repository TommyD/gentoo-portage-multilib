# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from portage.restrictions.collapsed import DictBased
from portage.restrictions.restrictionSet import OrRestrictionSet, AndRestrictionSet
import os
from errors import BaseException
from portage.util.file import iter_read_bash
from portage.package.atom import atom
from portage.restrictions.collapsed import DictBased
from portage.repository.visibility import filterTree
from portage.util.currying import post_curry
from portage.util.lists import unique

class MissingFile(BaseException):
	def __init__(self, file, setting):	self.file, self.setting = file, setting
	def __str__(self):						return "setting %s points at %s, which doesn't exist." % (self.setting, self.file)

class Failure(BaseException):
	def __init__(self, text):	self.text
	def __str__(self):			return "domain failure: %s" % text


def split_atom(atom):
	return atom.category + "/" + atom.package, atom.restrictions[2:]
def get_key_from_package(pkg):
	return pkg.category + "/" + pkg.package


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
# ~harring
class domain:
	def __init__(self, incrementals, root, profile, repositories, **settings):
		# voodoo, unfortunately (so it goes)
		maskers, unmaskers, keywords, visibility = profile.maskers[:], [], [], profile.visibility

		for key, val in (("package.mask", maskers), ("package.unmask", unmaskers), ("package.keywords", keywords)):
			if key in settings:
				if os.path.exists(settings[key]):
					try:  val.extend(map(atom, iter_read_bash(fp)))
					except (IOError, OSError), e:
						raise Failure("failed reading '%s': %s" % (settings[key], str(e)))
				else:
					raise MissingFile(settings[key], key)
				del settings[key]

		inc_d = set(incrementals)
		for x in profile.conf.keys():
			if x in settings:
				if x in inc_d:
					# strings overwrite, lists append.
					if isinstance(settings[x], (list, tuple)):
						settings[x] += profile.conf[x]
			else:
				settings[x] = profile.conf[x]
		del inc_d

		# visibility mask...
		# if (package.mask and not package.unmask) or system-visibility-filter or not (package.keywords or accept_keywords)

		filter = OrRestrictionSet()
		masker_d = DictBased(maskers, get_key_from_package, split_atom)
		if len(unmaskers):
			masker_d = AndRestrictionSet(masker_d, DictBased(unmaskers, get_key_from_package, split_atom, negate=True))
		filter.add_restriction(masker_d)

		# profile visibility filters.
		if len(visibility):
			filter.add_restriction(DictBased(visibility, get_key_from_package, split_atom))

#		keywords, license = [], []
#		if "accept_keywords" in settings:
#			keywords = settings["accept_keywords"]
						
		self.repos = map(post_curry(filterTree, filter, False), repositories)
