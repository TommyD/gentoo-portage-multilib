# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

prepallstrip() {
	if [ "${FEATURES//*nostrip*/true}" == "true" ] || [ "${RESTRICT//*nostrip*/true}" == "true" ] ; then
		return 0
	fi

	echo "prepallstrip:"
	prepstrip "${D}" || die
}
