# Copyright 1999-2001 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License, v2 or later
# Author: Geert Bevin <gbevin@theleaf.be>
# $ Header: $

S=${WORKDIR}/bash-${PV}
DESCRIPTION="The standard GNU Bourne again shell"
SRC_URI="ftp://ftp.gnu.org/gnu/bash/bash-${PV}.tar.gz"

HOMEPAGE="http://www.gnu.org/software/bash/bash.html"

DEPEND=">=sys-libs/ncurses-5.2-r2
        readline? ( >=sys-libs/readline-4.1-r2 )"
	
RDEPEND="virtual/glibc"

src_compile() {

    local myconf
    [ "`use readline`" ] && myconf="--with-installed-readline"
    [ -z "`use nls`" ] && myconf="${myconf} --disable-nls"
	./configure --prefix=/ --mandir=/usr/share/man --infodir=/usr/share/info --host=${CHOST} --disable-profiling --with-curses --without-gnu-malloc ${myconf} || die
	emake || die
	
}

src_install() {
	
    dodir /bin
	cp -af /bin/bash ${D}/bin/sbash
    cp ${S}/bash ${D}/bin

}

pkg_prerm() {

	mv /bin/bash /bin/dbash
	cp -af /bin/sbash /bin/bash
	
}

pkg_postrm() {

	rm /bin/dbash
	
}
