# elog/mod_echo.py - elog dispatch module
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.output import EOutput, colorize
from portage.const import EBUILD_PHASES
from portage.localization import _

_items = []
def process(mysettings, key, logentries, fulltext):
	global _items
	_items.append((mysettings["ROOT"], key, logentries))

def finalize(mysettings=None):
	"""The mysettings parameter is just for backward compatibility since
	an older version of portage will import the module from a newer version
	when it upgrades itself."""
	global _items
	printer = EOutput()
	for root, key, logentries in _items:
		print
		if root == "/":
			printer.einfo(_("Messages for package %s:") %
				colorize("INFORM", key))
		else:
			printer.einfo(_("Messages for package %(pkg)s merged to %(root)s:") %
				{"pkg": colorize("INFORM", key), "root": root})
		print
		for phase in EBUILD_PHASES:
			if phase not in logentries:
				continue
			for msgtype, msgcontent in logentries[phase]:
				fmap = {"INFO": printer.einfo,
						"WARN": printer.ewarn,
						"ERROR": printer.eerror,
						"LOG": printer.einfo,
						"QA": printer.ewarn}
				if isinstance(msgcontent, basestring):
					msgcontent = [msgcontent]
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	_items = []
	return
