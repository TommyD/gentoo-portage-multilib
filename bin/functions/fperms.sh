# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

fperms() {
	if [ ${#} -lt 2 ] ; then
		die "fperms: at least two arguments needed"
	fi

	if [ "${1}" == "-R" ]; then
		FP_RECURSIVE="-R"
		shift
	fi
	PERM="${1}"
	shift

	for FILE in "$@"; do
		chmod ${FP_RECURSIVE} "${PERM}" "${D}${FILE}" || die "Unable to 'chmod ${FP_RECURSIVE} ${PERM} ${D}${FILE}"
	done
}