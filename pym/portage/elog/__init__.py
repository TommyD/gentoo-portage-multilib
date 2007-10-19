# elog/__init__.py - elog core functions
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.const import EBUILD_PHASES
from portage.exception import PortageException
from portage.process import atexit_register
from portage.util import writemsg

from portage.elog.messages import collect_ebuild_messages, collect_messages
from portage.elog.filtering import filter_loglevels

import os

def _merge_logentries(a, b):
	rValue = {}
	phases = set(a)
	phases.update(b)
	for p in phases:
		merged_msgs = []
		rValue[p] = merged_msgs
		for d in a, b:
			msgs = d.get(p)
			if msgs:
				merged_msgs.extend(msgs)
	return rValue

def _combine_logentries(logentries):
	# generate a single string with all log messages
	rValue = []
	for phase in EBUILD_PHASES:
		if not phase in logentries:
			continue
		previous_type = None
		for msgtype, msgcontent in logentries[phase]:
			if previous_type != msgtype:
				previous_type = msgtype
				rValue.append("%s: %s\n" % (msgtype, phase))
			for line in msgcontent:
				rValue.append(line)
			rValue.append("\n")
	return "".join(rValue)

_elog_atexit_handlers = []
_preserve_logentries = {}
def elog_process(cpv, mysettings, phasefilter=None):
	ebuild_logentries = collect_ebuild_messages(os.path.join(mysettings["T"], "logging"))
	all_logentries = collect_messages()
	if all_logentries.has_key(cpv):
		all_logentries[cpv] = _merge_logentries(ebuild_logentries, all_logentries[cpv])
	else:
		all_logentries[cpv] = ebuild_logentries

	for key in _preserve_logentries.keys():
		if all_logentries.has_key(key):
			all_logentries[key] = _merge_logentries(_preserve_logentries[key], all_logentries[key])
		else:
			all_logentries[key] = _preserve_logentries[key]
		del _preserve_logentries[key]

	if phasefilter != None:
		for key in all_logentries:
			all_logentries[key], _preserve_logentries[key] = phasefilter(all_logentries[key])

	my_elog_classes = set(mysettings.get("PORTAGE_ELOG_CLASSES", "").split())

	for key in all_logentries:
		default_logentries = filter_loglevels(all_logentries[key], my_elog_classes)

		# in case the filters matched all messages and no module overrides exist
		if len(default_logentries) == 0 and (not ":" in mysettings.get("PORTAGE_ELOG_SYSTEM", "")):
			return

		default_fulllog = _combine_logentries(default_logentries)

		# pass the processing to the individual modules
		logsystems = mysettings["PORTAGE_ELOG_SYSTEM"].split()
		for s in logsystems:
			# allow per module overrides of PORTAGE_ELOG_CLASSES
			if ":" in s:
				s, levels = s.split(":", 1)
				levels = levels.split(",")
				mod_logentries = filter_loglevels(all_logentries[key], levels)
				mod_fulllog = _combine_logentries(mod_logentries)
			else:
				mod_logentries = default_logentries
				mod_fulllog = default_fulllog
			if len(mod_logentries) == 0:
				continue
			# - is nicer than _ for module names, so allow people to use it.
			s = s.replace("-", "_")
			try:
				# FIXME: ugly ad.hoc import code
				# TODO:  implement a common portage module loader
				name = "portage.elog.mod_" + s
				m = __import__(name)
				for comp in name.split(".")[1:]:
					m = getattr(m, comp)
				def timeout_handler(signum, frame):
					raise PortageException("Timeout in elog_process for system '%s'" % s)
				import signal
				signal.signal(signal.SIGALRM, timeout_handler)
				# Timeout after one minute (in case something like the mail
				# module gets hung).
				signal.alarm(60)
				try:
					m.process(mysettings, str(key), mod_logentries, mod_fulllog)
				finally:
					signal.alarm(0)
				if hasattr(m, "finalize") and not m.finalize in _elog_atexit_handlers:
					_elog_atexit_handlers.append(m.finalize)
					atexit_register(m.finalize)
			except (ImportError, AttributeError), e:
				writemsg("!!! Error while importing logging modules " + \
					"while loading \"mod_%s\":\n" % str(s))
				writemsg("%s\n" % str(e), noiselevel=-1)
			except PortageException, e:
				writemsg("%s\n" % str(e), noiselevel=-1)

