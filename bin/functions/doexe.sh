# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

doexe() {
	mynum=${#}
	if [ ${mynum} -lt 1 ] ; then
		die "doexe: at least one argument needed"
	fi
	if [ ! -d "${D}${EXEDESTTREE}" ] ; then
		install -d "${D}${EXEDESTTREE}" || die
	fi

	if [ ! -z "${CBUILD}" ] && [ "${CBUILD}" != "${CHOST}" ]; then
		STRIP=${CHOST}-strip
	else
		STRIP=strip
	fi

	for x in "$@" ; do
		if [ "${FEATURES//*nostrip*/true}" != "true" ] && [ "${RESTRICT//*nostrip*/true}" != "true" ] ; then
			MYVAL=`file "${x}" | grep "ELF"` 
			if [ -n "$MYVAL" ] ; then
				${STRIP} "${x}" || die
			fi
		fi
		if [ -L "${x}" ] ; then
			cp "${x}" "${T}" || die
			mysrc="${T}"/`/usr/bin/basename "${x}"`
		elif [ -d "${x}" ] ; then
			echo "doexe: warning, skipping directory ${x}"
			continue
		else
			mysrc="${x}"
		fi
		install ${EXEOPTIONS} "${mysrc}" "${D}${EXEDESTTREE}" || die
	done
}
