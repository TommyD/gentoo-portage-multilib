# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

dosym() {
	if [ ${#} -ne 2 ] ; then
		die "dosym: two arguments needed"
	fi

	target="${1}"
	linkname="${2}"
	ln -snf "${target}" "${D}${linkname}" || die
}
