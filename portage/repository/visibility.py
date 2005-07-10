# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# icky.
# ~harring
import prototype, errors

class tree(prototype.tree):

	"""wrap an existing repository filtering results based upon passed in restrictions"""
	def __init__(self, repo, restrictions):
		self.raw_repo = repo
		if not isinstance(raw_repo, prototype.tree):
			raise errors.InitializationError("%s is not a repository tree derivative" % str(raw_repo))
		if not isinstance(restrictions, list):
			restrictions = [restrictions]
		self._restrictions = restrictions

	def itermatch(self, atom):
		for cpv in self.raw_repo.itermatch(atom):
			for r in self._restrictions:
				if r.match(cpv):
					yield cpv
