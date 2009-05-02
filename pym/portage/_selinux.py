# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: _selinux.py 12701 2009-02-23 21:05:22Z zmedico $

import selinux
from selinux import is_selinux_enabled
from selinux_aux import setexec, secure_symlink, secure_rename, \
	secure_copy, secure_mkdir, getcontext, get_sid, get_lsid
