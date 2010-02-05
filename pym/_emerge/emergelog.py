# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from __future__ import print_function

import codecs
import sys
import time
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.data import secpass
from portage.output import xtermTitle

_emerge_log_dir = '/var/log'
_disable = False

def emergelog(xterm_titles, mystr, short_msg=None):

	if _disable:
		return

	mystr = portage._unicode_decode(mystr)

	if short_msg is not None:
		short_msg = portage._unicode_decode(short_msg)

	if xterm_titles and short_msg:
		if "HOSTNAME" in os.environ:
			short_msg = os.environ["HOSTNAME"]+": "+short_msg
		xtermTitle(short_msg)
	try:
		file_path = os.path.join(_emerge_log_dir, 'emerge.log')
		mylogfile = codecs.open(_unicode_encode(file_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='a', encoding=_encodings['content'],
			errors='backslashreplace')
		portage.util.apply_secpass_permissions(file_path,
			uid=portage.portage_uid, gid=portage.portage_gid,
			mode=0o660)
		mylock = None
		try:
			mylock = portage.locks.lockfile(mylogfile)
			# seek because we may have gotten held up by the lock.
			# if so, we may not be positioned at the end of the file.
			mylogfile.seek(0, 2)
			mylogfile.write(str(time.time())[:10]+": "+mystr+"\n")
			mylogfile.flush()
		finally:
			if mylock:
				portage.locks.unlockfile(mylock)
			mylogfile.close()
	except (IOError,OSError,portage.exception.PortageException) as e:
		if secpass >= 1:
			print("emergelog():",e, file=sys.stderr)
