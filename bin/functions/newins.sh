# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

newins() {
	if [ -z "${T}" ] || [ -z "${2}" ] ; then
		die "newins: Nothing defined to do."
	fi

	rm -rf "${T}/${2}" || die
	cp "${1}" "${T}/${2}" || die
	doins "${T}/${2}" || die
}