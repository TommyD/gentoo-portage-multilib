# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

prepinfo() {
	if [ -z "$1" ] ; then
		z="${D}usr/share/info"
	else
		if [ -d "${D}$1/share/info" ] ; then
			z="${D}$1/share/info"
		else
			z="${D}$1/info"
		fi
	fi

	[ ! -d "${z}" ] && return 0

	rm -f "${z}"/{dir,dir.info,dir.info.gz} || die

	for x in `find "${z}"/ \( -type f -or -type l \) -maxdepth 1 -mindepth 1 2>/dev/null` ; do
		if [ -L "${x}" ] ; then
		# Symlink ...
			mylink="${x}"
				linkto="`readlink "${x}"`"

				if [ "${linkto##*.}" != "gz" ] ; then
				linkto="${linkto}.gz"
			fi
			if [ "${mylink##*.}" != "gz" ] ; then
				mylink="${mylink}.gz"
			fi
	
			echo "fixing GNU info symlink: ${mylink##*/}"
			ln -snf "${linkto}" "${mylink}" || die
			if [ "${x}" != "${mylink}" ] ; then
				echo "removing old symlink: ${x##*/}"
				rm -f "${x}" || die
			fi
		else
			if [ "${x##*.}" != "gz" ] ; then
				echo "gzipping GNU info page: ${x##*/}"
				gzip -f -9 "${x}" || die
			fi
		fi
	done
}