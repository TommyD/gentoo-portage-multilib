# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

doinfo() {
	if [ ${#} -lt 1 ] ; then
		die "doinfo: at least one argument needed"
	fi
	if [ ! -d "${D}usr/share/info" ] ; then
		install -d "${D}usr/share/info" || die
	fi

	for x in "$@" ; do
		if [ -e "${x}" ] ; then
			install -m0644 "${x}" "${D}usr/share/info" || die
			gzip -f -9 "${D}usr/share/info/${x##*/}" || die
		else
			echo "doinfo: ${x} does not exist"
		fi
	done
}