# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

fowners() {
	if [ ${#} -lt 2 ] ; then
		die "fowners: at least two arguments needed"
	fi

	if [ "$1" == "-R" ]; then
		FO_RECURSIVE="-R"
		shift
	fi
	OWNER="${1}"
	shift

	for FILE in "$@"; do
		chown ${FO_RECURSIVE} "${OWNER}" "${D}${FILE}" || die "Failed to 'chown ${FO_RECURSIVE} ${OWNER} ${D}${FILE}'"
	done
}