#!/bin/bash
export PKG="portage"
export TMP="/tmp"
export V="1.8.9_pre36"
export DEST="${TMP}/${PKG}-${V}"
rm -rf ${DEST}
install -d -m0755 ${DEST}
for x in bin cnf man pym src 
do
	cp -ax $x ${DEST}
	rm -rf ${DEST}/${x}/CVS
done
cp ${DEST}/pym/portage.py ${DEST}/pym/portage.py.orig
sed "s/@portage_version@/${V}/" < ${DEST}/pym/portage.py.orig > ${DEST}/pym/portage.py
rm ${DEST}/pym/portage.py.orig
rm -rf ${DEST}/src/sandbox/CVS
cp ChangeLog ${DEST}
chown -R root.root ${DEST}
cd $TMP
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
