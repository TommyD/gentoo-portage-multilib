# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

dohard() {
	if [ ${#} -ne 2 ] ; then
		die "dohard: two arguments needed"
	fi

	mysrc="${1}"
	mydest="${2}"
	ln -f "${D}${mysrc}" "${D}${mydest}" || die
}
