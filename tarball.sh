#!/bin/bash
# $Header$

if [ -z "$1" ]; then
	echo
	echo "You need to have the version specified."
	echo "e.g.: $0 2.0.39-r37"
	echo
	exit 0
fi

export PKG="portage"
export TMP="/tmp"
export V="$1"
export DEST="${TMP}/${PKG}-${V}"
export PREVEB="2.0.48_pre2"
rm -rf ${DEST}
install -d -m0755 ${DEST}
#get any binaries out of the way
cd src/sandbox
make clean
cd ../..
for x in bin cnf man pym src 
do
	cp -ax $x ${DEST}
done
# Clean invalid sandbox sources
rm -rf ${DEST}/src/{sandbox,sandbox-dev}
cp ${DEST}/pym/portage.py ${DEST}/pym/portage.py.orig
sed '/^VERSION=/s/^.*$/VERSION="'${V}'"/' < ${DEST}/pym/portage.py.orig > ${DEST}/pym/portage.py
cp ${DEST}/man/emerge.1 ${DEST}/man/emerge.1.orig
sed "s/##VERSION##/${V}/g" < ${DEST}/man/emerge.1.orig > ${DEST}/man/emerge.1
rm ${DEST}/pym/portage.py.orig ${DEST}/man/emerge.1.orig
cp ChangeLog ${DEST}
cd ${DEST}
find -name CVS -exec rm -rf {} \;
find -name '*~' -exec rm -rf {} \;
chown -R root.root ${DEST}
cd $TMP
rm -f ${PKG}-${V}/bin/emerge.py ${PKG}-${V}/bin/{pmake,sandbox} ${PKG}-${V}/{bin,pym}/*.py[oc]
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}

if [ -L ${TMP}/portage-copy ]; then
	echo "Copying to portage-copy"
	cp ${TMP}/${PKG}-${V}.tar.bz2 ${TMP}/portage-copy/
	cp /usr/portage/sys-apps/portage/portage-${PREVEB}.ebuild ${TMP}/portage-copy/portage-${V}.ebuild
fi
if [ -L ${TMP}/portage-web ]; then
	echo "Copying to portage-web"
	cp ${TMP}/${PKG}-${V}.tar.bz2 ${TMP}/portage-web/
	cp /usr/portage/sys-apps/portage/portage-${PREVEB}.ebuild ${TMP}/portage-copy/portage-${V}.ebuild
fi
if [ -d /usr/portage.cvs/sys-apps/portage/ ]; then
	cp /usr/portage/sys-apps/portage/portage-${PREVEB}.ebuild /usr/portage/sys-apps/portage/portage-${V}.ebuild
	cp /usr/portage/sys-apps/portage/portage-${PREVEB}.ebuild /usr/portage.cvs/sys-apps/portage/portage-${V}.ebuild
	rm -f /usr/portage/sys-apps/portage/files/digest-portage-${V}
	rm -f /usr/portage.cvs/sys-apps/portage/files/digest-portage-${V}
	rm -f /bigmama/share/archive/mirrors/gentoo/distfiles/portage-${V}.tar.bz2
	rm -f $(python -c "import portage; print portage.settings['DISTDIR']+\"/${PKG}-${V}.tar.bz2\"")
	ebuild /usr/portage/sys-apps/portage/portage-${V}.ebuild fetch digest
	cp /usr/portage/sys-apps/portage/files/digest-portage-${V} /usr/portage.cvs/sys-apps/portage/files/digest-portage-${V}
fi
