# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.PackageVirtualDbapi import PackageVirtualDbapi

class RootConfig(object):
	"""This is used internally by depgraph to track information about a
	particular $ROOT."""

	pkg_tree_map = {
		"ebuild"    : "porttree",
		"binary"    : "bintree",
		"installed" : "vartree"
	}

	tree_pkg_map = {}
	for k, v in pkg_tree_map.iteritems():
		tree_pkg_map[v] = k

	def __init__(self, settings, trees, setconfig):
		self.trees = trees
		self.settings = settings
		self.iuse_implicit = tuple(sorted(settings._get_implicit_iuse()))
		self.root = self.settings["ROOT"]
		self.setconfig = setconfig
		if setconfig is None:
			self.sets = {}
		else:
			self.sets = self.setconfig.getSets()
		self.visible_pkgs = PackageVirtualDbapi(self.settings)

