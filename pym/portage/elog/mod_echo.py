# elog/mod_echo.py - elog dispatch module
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.output import EOutput
from portage.const import EBUILD_PHASES

_items = []
def process(mysettings, key, logentries, fulltext):
	global _items
	_items.append((mysettings, key, logentries))

def finalize():
	global _items
	printer = EOutput()
	for mysettings, key, logentries in _items:
		root_msg = ""
		if mysettings["ROOT"] != "/":
			root_msg = " merged to %s" % mysettings["ROOT"]
		print
		printer.einfo("Messages for package %s%s:" % (key, root_msg))
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
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	_items = []
	return
