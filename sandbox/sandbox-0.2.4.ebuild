# Copyright 1999-2001 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License, v2 or later
# Author:  Martin Schlemmer <azarah@gentoo.org>
# $Header$

S=${WORKDIR}/sandbox
DESCRIPTION="Portage SandBox System"
SRC_URI=""
HOMEPAGE=""

DEPEND="virtual/glibc
	=sys-apps/portage-1.8.1"
	

src_unpack() {

	mkdir -p ${S}
	cd ${S}
	cp ${FILESDIR}/sandbox/*sandbox* . || die
	cp ${FILESDIR}/sandbox/Makefile . || die
	
}

src_compile() {

	cp /usr/lib/portage/pym/portage.py .
	cp portage.py portage.py.orig
	cp /usr/lib/portage/bin/ebuild.sh .
	cp ebuild.sh ebuild.sh.orig

	patch <${FILESDIR}/portage.py.diff || die
	patch <${FILESDIR}/ebuild.sh.diff || die
        
	emake || die
}

src_install() {
	
	dodir /usr/bin /usr/lib/sandbox
	dodir /usr/lib/portage/{bin,pym}

	into /usr
	dobin sandbox
	exeinto /usr/lib/sandbox
	doexe libsandbox.so
	insinto /usr/lib/sandbox
	doins sandbox.bashrc
	insinto /usr/lib/portage/pym
	doins portage.py portage.py.orig
	exeinto /usr/lib/portage/bin
	doexe ebuild.sh ebuild.sh.orig
}

pkg_prerm() {

	# Restore the original portage files
	cp -f /usr/lib/portage/pym/portage.py.orig /usr/lib/portage/pym/portage.py
	cp -f /usr/lib/portage/bin/ebuild.sh.orig /usr/lib/portage/bin/ebuild.sh
	# Make the current ebuild use bash instead of sandbox further on
	rm -f /usr/bin/sandbox
	echo '#!/bin/bash' > /usr/bin/sandbox
	echo '/bin/bash -c "$@"' >> /usr/bin/sandbox
	chmod 755 /usr/bin/sandbox
	
}

pkg_postrm() {

	# Remove the temporary sandbox script
	rm -f /usr/bin/sandbox
	
}

