# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

prepalldocs() {
	z="`find "${D}"usr/share/doc \( -type f -or -type l \) -not -name "*.gz" -not -name "*.js" 2>/dev/null`"

	for y in ${z} ; do
		if [ -L "${y}" ] ; then
			# Symlink ...
			mylink="${y}"
			linkto="`readlink "${y}"`"

			if [ "${linkto##*.}" != "gz" ] ; then
				linkto="${linkto}.gz"
			fi
			if [ "${mylink##*.}" != "gz" ] ; then
				mylink="${mylink}.gz"
			fi

			echo "fixing doc symlink: ${mylink##*/}"
			ln -snf "${linkto}" "${mylink}" || die
			if [ "${y}" != "${mylink}" ] ; then
				echo "removing old symlink: ${y##*/}"
				rm -f "${y}" || die
			fi
		else
			if [ "${y##*.}" != "gz" ] ; then
				echo "gzipping doc: ${y##*/}"
				gzip -f -9 "${y}" || die
			fi
		fi	
	done
}
