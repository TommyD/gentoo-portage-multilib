#!/bin/bash

if [ -z "$1" ]; then
	echo
	echo "You need to have the version specified."
	echo "e.g.: $0 2.0.39"
	echo
	exit 0
fi

export PKG="portage"
export TMP="/tmp"
export V="$1"
export DEST="${TMP}/${PKG}-${V}"
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
chown -R root.root ${DEST}
cd $TMP
rm -f ${PKG}-${V}/bin/emerge.py
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
