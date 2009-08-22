# elog/mod_syslog.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import sys
import syslog
from portage.const import EBUILD_PHASES
from portage import _encodings

_pri = {
	"INFO"   : syslog.LOG_INFO, 
	"WARN"   : syslog.LOG_WARNING, 
	"ERROR"  : syslog.LOG_ERR, 
	"LOG"    : syslog.LOG_NOTICE,
	"QA"     : syslog.LOG_WARNING
}

def process(mysettings, key, logentries, fulltext):
	syslog.openlog("portage", syslog.LOG_ERR | syslog.LOG_WARNING | syslog.LOG_INFO | syslog.LOG_NOTICE, syslog.LOG_LOCAL5)
	for phase in EBUILD_PHASES:
		if not phase in logentries:
			continue
		for msgtype,msgcontent in logentries[phase]:
			msgtext = "".join(msgcontent)
			msgtext = "%s: %s: %s" % (key, phase, msgtext)
			if sys.hexversion < 0x3000000 and isinstance(msgtext, unicode):
				# Avoid TypeError from syslog.syslog()
				msgtext = msgtext.encode(_encodings['content'], 
					'backslashreplace')
			syslog.syslog(_pri[msgtype], msgtext)
	syslog.closelog()
