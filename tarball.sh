#!/bin/bash
export PKG="portage"
export TMP="/tmp"
export V="2.0.22"
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
cp ${DEST}/pym/portage.py ${DEST}/pym/portage.py.orig
sed '/^VERSION=/s/^.*$/VERSION="'${V}'"/' < ${DEST}/pym/portage.py.orig > ${DEST}/pym/portage.py
rm ${DEST}/pym/portage.py.orig
cp ChangeLog ${DEST}
cd ${DEST}
find -name CVS -exec rm -rf {} \;
chown -R root.root ${DEST}
cd $TMP
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
