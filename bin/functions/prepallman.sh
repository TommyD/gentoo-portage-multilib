# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

prepallman() {
	echo "man:"
	for x in "${D}"opt/*/man "${D}"usr/share/man "${D}"usr/local/man "${D}"usr/X11R6/man ; do
		if [ -d "${x}" ]; then
			prepman "`echo "${x}" | sed -e "s:${D}::" -e "s:/man[/]*$::"`" || die
		fi
	done
}