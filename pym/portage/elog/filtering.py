# elog/messages.py - elog core functions
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.const import EBUILD_PHASES

def filter_loglevels(logentries, loglevels):
	# remove unwanted entries from all logentries
	rValue = {}
	loglevels = [x.upper() for x in loglevels]
	for phase in logentries:
		for msgtype, msgcontent in logentries[phase]:
			if msgtype.upper() in loglevels or "*" in loglevels:
				if phase not in rValue:
					rValue[phase] = []
				rValue[phase].append((msgtype, msgcontent))
	return rValue
	
def filter_phases(logentries, phases):
	rValue1 = {}
	rValue2 = {}
	phases = [x.lower() for x in phases]
	for phase in logentries:
		if phase in phases:
			rValue1[phase] = logentries[phase]
		else:
			rValue2[phase] = logentries[phase]
	return (rValue1, rValue2)

def filter_mergephases(logentries):
	myphases = EBUILD_PHASES[:]
	myphases.remove("prerm")
	myphases.remove("postrm")
	return filter_phases(logentries, myphases)

def filter_unmergephases(logentries):
	return filter_phases(logentries, ["prerm", "postrm", "other"])
