# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

dosed() {
	mysed="s:${D}::g"

	for x in "$@" ; do
		y="${D}${x}"
		if [ -a "${y}" ] ; then
			if [ -f "${y}" ] ; then
				mysrc="${T}"/`/usr/bin/basename "${y}"`
				cp "${y}" "${mysrc}" || die
				sed -e "${mysed}" "${mysrc}" > "${y}" || die
			else
				die "${y} is not a regular file!"
			fi
		else
			mysed="${x}"
		fi
	done
}


