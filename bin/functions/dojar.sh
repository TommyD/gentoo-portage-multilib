# Copyright 1999-2003 Gentoo Technologies, Inc.                                 
# Distributed under the terms of the GNU General Public License v2
# Author Karl Trygve Kalleberg <karltk@gentoo.org>
# $Header$
#
# Typical usage:
#  dojar foo.jar bar.jar
#   - installs foo.jar and bar.jar into /usr/share/${PN}/lib, and adds them 
#     both to /usr/share/${PN}/classpath.env
#
# Detailed usage
#  dojar <list-of-jars>
#   - installs <list-of-jars> into /usr/share/${PN}/lib and adds each to
#     /usr/share/${PN}/classpath.env. 
# 
# The classpath.env file is currently merely a convenience for the user as
# it allows him to:
# export CLASSPATH=${CLASSPATH}:`cat /usr/share/foo/classpath.env`
#
# For many packages that set FOO_HOME, placing the jar files into
# lib will allow the user to set FOO_HOME=/usr/share/foo and have the
# scripts work as expected.
#
# Possibly a jarinto will be needed in the future.
#

dojar() {
	if [ -z "$JARDESTTREE" ] ; then
		JARDESTTREE="lib"
	fi

	jarroot="${DESTTREE}/share/${PN}/"
	jardest="${DESTTREE}/share/${PN}/${JARDESTTREE}/"
	pf="${D}${jarroot}/package.env"

	dodir "${jardest}" || die

	for i in $* ; do
		bn="$(basename $i)"
	
		if [ -f "$pf" ] ; then
			oldcp=`grep "CLASSPATH=" "$pf" | sed "s/CLASSPATH=//"`
			grep -v "CLASSPATH=" "$pf" > "${pf}.new"
			echo "CLASSPATH=${oldcp}:${jardest}${bn}" >> "${pf}.new"
			mv "${pf}.new" "$pf" || die
		else
			echo "DESCRIPTION=\"${DESCRIPTION}\"" > "$pf"
			echo "CLASSPATH=${jardest}${bn}" >> "$pf"
		fi

		cp "$i" "${D}${jardest}/" || die
		chmod 0444 "${D}${jardest}/${bn}" || die
	done
}