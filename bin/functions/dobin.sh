# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

dobin() {
	if [ ${#} -lt 1 ] ; then
		die "dobin: at least one argument needed"
	fi

	if [ ! -z "${CBUILD}" ] && [ "${CBUILD}" != "${CHOST}" ]; then
		STRIP=${CHOST}-strip
	else
		STRIP=strip
	fi

	if [ ! -d "${D}${DESTTREE}/bin" ] ; then
		install -d "${D}${DESTTREE}/bin" || die
	fi

	for x in "$@" ; do
		if [ -x "${x}" ] ; then
			if [ "${FEATURES//*nostrip*/true}" != "true" ] && [ "${RESTRICT//*nostrip*/true}" != "true" ] ; then
				MYVAL=`file "${x}" | grep "ELF"` 
				if [ -n "$MYVAL" ] ; then
					${STRIP} "${x}" || die
				fi
			fi
			#if executable, use existing perms
			install "${x}" "${D}${DESTTREE}/bin" || die
		else
			#otherwise, use reasonable defaults
			echo ">>> dobin: making ${x} executable..."
			install -m0755 --owner=root --group=root "${x}" "${D}${DESTTREE}/bin" || die
		fi
	done
}
