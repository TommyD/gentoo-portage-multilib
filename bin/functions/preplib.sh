# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

preplib() {
	if [ -z "$1" ] ; then
		z="${D}usr/lib"
	else
		z="${D}$1/lib"
	fi

	if [ -d "${z}" ] ; then
		ldconfig -n -N "${z}" || die
	fi
}
