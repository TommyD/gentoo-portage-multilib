# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

dolib.a() {
	if [ ${#} -lt 1 ] ; then
		die "dolib.a: at least one argument needed"
	fi
	if [ ! -d "${D}${DESTTREE}/lib" ] ; then
		install -d "${D}${DESTTREE}/lib" || die
	fi

	for x in "$@" ; do
		if [ -e "${x}" ] ; then
			install -m0644 "${x}" "${D}${DESTTREE}/lib" || die
		else
			die "dolib.a: ${x} does not exist"
		fi
	done
}