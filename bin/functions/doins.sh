# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

doins() {
	if [ $# -lt 1 ] ; then
		die "doins: at least one argument needed"
	fi
	if [ ! -d "${D}${INSDESTTREE}" ] ; then
		install -d "${D}${INSDESTTREE}" || die
	fi

	for x in "$@" ; do
		if [ -L "$x" ] ; then
			cp "$x" "${T}" || die
			mysrc="${T}"/`/usr/bin/basename "${x}"`
		elif [ -d "$x" ] ; then
			echo "doins: warning, skipping directory ${x}"
			continue
		else
			mysrc="${x}"
		fi
		install ${INSOPTIONS} "${mysrc}" "${D}${INSDESTTREE}" || die
	done
}
