#!/bin/bash
export PKG="portage"
export TMP="/tmp"
export V="1.6.5"
export DEST="${TMP}/${PKG}-${V}"
rm -rf ${DEST}
install -d -m0755 ${DEST}
for x in bin cnf man pym src 
do
	cp -ax $x ${DEST}
	rm -rf ${DEST}/${x}/CVS
done
cp ChangeLog ${DEST}
chown -R root.root ${DEST}
cd $TMP
tar cjvf ${TMP}/${PKG}-${V}.tar.bz2 ${PKG}-${V}
