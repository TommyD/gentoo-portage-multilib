# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

prepallinfo() {
	if [ ! -d "${D}usr/share/info" ]; then
		return 0
	fi

	echo "info:"
	prepinfo || die
}
