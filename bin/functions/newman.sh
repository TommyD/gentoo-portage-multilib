# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

newman() {
	if [ -z "${T}" ] || [ -z "${2}" ] ; then
		die "newman: Nothing defined to do."
	fi

	rm -rf "${T}/${2}" || die
	cp "${1}" "${T}/${2}" || die
	doman "${T}/${2}" || die
}
