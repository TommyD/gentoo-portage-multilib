#!/bin/bash
# affect-fakeroot-perms.sh; Make claimed fakeroot permissions, a reality.
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
$Header$


echo "adjusting $2 using $1" >&2
fakeroot -i "$1" -- find "$2" -exec stat -c '%u:%g;%f=%n' {} \; | \
while read l; do
		o="${l/;*}"
		r="${l/${o}}"
		p="${r/=*}"
		p="${p:1}"
		p="$(printf %o 0x${p})"
		p="${p:${#p}-3}"
		f="${r/*=}"
		chown "$o" "$f"
		chmod "$p" "$f"
		echo "tweaking $f"
	done
