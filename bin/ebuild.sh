#!/bin/bash
# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

if [ "$*" != "depend" ] && [ "$*" != "clean" ]; then
	if [ -f "${T}/successful" ]; then
		rm -f "${T}/successful"
	fi

	# Hurray for per-ebuild logging.
	if [ ! -z "${PORT_LOGDIR}" ]; then
		if [ -z "${PORT_LOGGING}" ]; then
			export PORT_LOGGING=1
			export SANDBOX_WRITE="$SANDBOX_WRITE:${PORT_LOGDIR}"
			install -d "${PORT_LOGDIR}" &>/dev/null
			chown root:portage "${PORT_LOGDIR}" &>/dev/null
			chmod g+rwxs "${PORT_LOGDIR}" &> /dev/null
			touch "${PORT_LOGDIR}/${LOG_COUNTER}-${PF}.log" &> /dev/null
			chmod g+w "${PORT_LOGDIR}/${LOG_COUNTER}-${PF}.log" &> /dev/null
			echo "$*" >> "${PORT_LOGDIR}/${LOG_COUNTER}-${PF}.log"
			$0 $* 2>&1 | tee -a "${PORT_LOGDIR}/${LOG_COUNTER}-${PF}.log"
			if [ "$?" != "0" ]; then
				rm -f "${T}/successful"
				exit 1
			fi
			if [ -f "${T}/successful" ]; then
				rm -f "${T}/successful"
				exit 0
			else
				exit 1
			fi
		fi
	fi

	if [ -f "${T}/environment" ]; then
		source "${T}/environment" &>/dev/null
	fi
fi

if [ -n "$#" ]; then
	ARGS="${*}"
fi

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH

# We need this next line for "die" and "assert". It expands 
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'

OCC="$CC"
OCXX="$CXX"
if [ "$USERLAND" == "GNU" ]; then
	source /etc/profile.env &>/dev/null
fi
[ ! -z "$OCC" ] && export CC="$OCC"
[ ! -z "$OCXX" ] && export CXX="$OCXX"

export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin:${ROOTPATH}"
[ ! -z "$PREROOTPATH" ] && export PATH="${PREROOTPATH%%:}:$PATH"

# Grab our new utility functions.
source /usr/lib/portage/bin/extra_functions.sh

if [ -e /etc/init.d/functions.sh ]; then
	source /etc/init.d/functions.sh  &>/dev/null
elif [ -e /etc/rc.d/config/functions ];	then
	source /etc/rc.d/config/functions &>/dev/null
else
	#Mac OS X
	source /usr/lib/portage/bin/functions.sh &>/dev/null
fi

esyslog() {
	# Custom version of esyslog() to take care of the "Red Star" bug.
	# MUST follow functions.sh to override the "" parameter problem.
	return 0
}

use() {
	local x
	for x in ${USE}; do
		if [ "${x}" == "${1}" ]; then
			if [ -r /dev/fd/1 ]; then
				tty --quiet < /dev/stdout || echo "${x}"
			else
			  echo "${x}"
			fi
			return 0
		fi
	done
	return 1
}

has() {
	local x

	local me=$1
	shift
	
	# All the TTY checks really only help out depend. Which is nice.
	# Logging kills all this anyway. Everything becomes a pipe. --NJ
	for x in "$@"; do
		if [ "${x}" == "${me}" ]; then
			if [ -r /proc/self/fd/1 ]; then
				tty --quiet < /proc/self/fd/1 || echo "${x}"
			elif [ -r /dev/fd/1 ]; then
				echo "/dev/fd/1" >&2
				tty --quiet < /dev/fd/1 || echo "${x}"
			elif [ -r /dev/stdout ]; then
				echo "/dev/stdout" >&2
				tty --quiet < /dev/stdout || echo "${x}"
			else
				echo "${x}"
			fi
			return 0
		fi
	done
	return 1
}

has_version() {
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	if /usr/lib/portage/bin/portageq 'has_version' "${ROOT}" "$1"; then
		return 0
	else
		return 1
	fi
}

best_version() {
	# returns the best/most-current match.
	# Takes single depend-type atoms.
	/usr/lib/portage/bin/portageq 'best_version' "${ROOT}" "$1"
}

use_with() {
	if [ -z "$1" ]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local UW_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UW_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if use $1 &>/dev/null; then
		echo "--with-${UWORD}${UW_SUFFIX}"
		return 0
	else
		echo "--without-${UWORD}"
		return 1
	fi
}

use_enable() {
	if [ -z "$1" ]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local UE_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UE_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if use $1 &>/dev/null; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
		return 0
	else
		echo "--disable-${UWORD}"
		return 1
	fi
}

diefunc() {
	local funcname="$1" lineno="$2" exitcode="$3"
	shift 3
	echo >&2
	echo "!!! ERROR: $CATEGORY/$PF failed." >&2
	echo "!!! Function $funcname, Line $lineno, Exitcode $exitcode" >&2
	echo "!!! ${*:-(no error message)}" >&2
	echo >&2
	exit 1
}

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022
export DESTTREE=/usr
export INSDESTTREE=""
export EXEDESTTREE=""
export DOCDESTTREE=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"	
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}

check_KV()
{
	if [ -z "${KV}" ]; then
		eerror ""
		eerror "Could not determine your kernel version."
		eerror "Make sure that you have /usr/src/linux symlink."
		eerror "And that said kernel has been configured."
		eerror "You can also simply run the following command"
		eerror "in the kernel referenced by /usr/src/linux:"
		eerror " make include/linux/version.h"
		eerror ""
		die
	fi
}

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir()
{
	dodir "$@"
	local x
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${D}/%p/.keep\n" | tr "\n" "\0" | $XARGS -0 -n100 touch || die "Failed to recursive create .keep files"
	else
		for x in "$@"; do
			touch "${D}/${x}/.keep" || die "Failed to create .keep in ${D}/${x}"
		done
	fi
}

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# sandbox support functions
addread()
{
	export SANDBOX_READ="$SANDBOX_READ:$1"
}

addwrite()
{
	export SANDBOX_WRITE="$SANDBOX_WRITE:$1"
}

adddeny()
{
	export SANDBOX_DENY="$SANDBOX_DENY:$1"
}

addpredict()
{
	export SANDBOX_PREDICT="$SANDBOX_PREDICT:$1"
}


unpack() {
	local x
	local y
	local myfail
	local tarvars

	if [ "$USERLAND" == "BSD" ]; then
		tarvars=""
	else
		tarvars="--no-same-owner"	
	fi	

	for x in "$@"; do
		myfail="failure unpacking ${x}"
		echo ">>> Unpacking ${x} to $(pwd)"
		y="$(echo $x | sed 's:.*\.\(tar\)\.[a-zA-Z0-9]*:\1:')"

		case "${x##*.}" in
			tar) 
				tar ${tarvars} -xf "${DISTDIR}/${x}" || die "$myfail"
				;;
			tgz) 
				tar ${tarvars} -xzf "${DISTDIR}/${x}" || die "$myfail"
				;;
			tbz2) 
				bzip2 -dc "${DISTDIR}/${x}" | tar ${tarvars} -xf - || die "$myfail"
				;;
			ZIP|zip) 
				unzip -qo "${DISTDIR}/${x}" || die "$myfail"
				;;
			gz|Z|z) 
				if [ "${y}" == "tar" ]; then
					tar ${tarvars} -xzf "${DISTDIR}/${x}" || die "$myfail"
				else
					gzip -dc "${DISTDIR}/${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			bz2) 
				if [ "${y}" == "tar" ]; then
					bzip2 -dc "${DISTDIR}/${x}" | tar ${tarvars} -xf - || die "$myfail"
				else
					bzip2 -dc "${DISTDIR}/${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			*)
				echo "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
}

econf() {
	if [ -x ./configure ]; then
		if [ ! -z "${CBUILD}" ]; then
			EXTRA_ECONF="--build=${CBUILD} ${EXTRA_ECONF}"
		fi
		./configure \
		    --prefix=/usr \
		    --host=${CHOST} \
		    --mandir=/usr/share/man \
		    --infodir=/usr/share/info \
		    --datadir=/usr/share \
		    --sysconfdir=/etc \
		    --localstatedir=/var/lib \
				${EXTRA_ECONF} \
		    "$@" || die "econf failed" 
	else
		die "no configure script found"
	fi
}

einstall() {
	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ ! -z "${PORTAGE_DEBUG}" ]; then
			make -n prefix=${D}/usr \
			    datadir=${D}/usr/share \
			    infodir=${D}/usr/share/info \
		  	  localstatedir=${D}/var/lib \
			    mandir=${D}/usr/share/man \
			    sysconfdir=${D}/etc \
			    "$@" install
		fi
		make prefix=${D}/usr \
		    datadir=${D}/usr/share \
		    infodir=${D}/usr/share/info \
		    localstatedir=${D}/var/lib \
		    mandir=${D}/usr/share/man \
		    sysconfdir=${D}/etc \
		    "$@" install || die "einstall failed" 
	else
		die "no Makefile found"
	fi
}

pkg_setup()
{
	return 
}

pkg_nofetch()
{
	[ -z "${SRC_URI}" ] && return

	echo "!!! The following are listed in SRC_URI for ${PN}:"
	for MYFILE in `echo ${SRC_URI}`; do
		echo "!!!   $MYFILE"
	done
}

src_unpack() { 
	if [ "${A}" != "" ]; then
		unpack ${A}
	fi	
}

src_compile() { 
	if [ -x ./configure ]; then
		econf 
		emake || die "emake failed"
	fi
}

src_install() 
{ 
	return 
}

pkg_preinst()
{
	return
}

pkg_postinst()
{
	return
}

pkg_prerm()
{
	return
}

pkg_postrm()
{
	return
}

# Used to generate the /lib/cpp and /usr/bin/cc wrappers
gen_wrapper() {
	cat > $1 << END
#!/bin/sh

$2 "\$@"
END

	chmod 0755 $1
}

dyn_setup()
{
	if [ "$USERLAND" == "Linux" ]; then	
		# The next bit is to ease the broken pkg_postrm()'s
		# some of the gcc ebuilds have that nuke the new
		# /lib/cpp and /usr/bin/cc wrappers ...
	
		# Make sure we can have it disabled somehow ....
		if [ "${DISABLE_GEN_GCC_WRAPPERS}" != "yes" ]; then
			# Create /lib/cpp if missing or a symlink
			if [ -L /lib/cpp -o ! -e /lib/cpp ]; then
				[ -L /lib/cpp ] && rm -f /lib/cpp
				gen_wrapper /lib/cpp cpp
			fi
			# Create /usr/bin/cc if missing for a symlink
			if [ -L /usr/bin/cc -o ! -e /usr/bin/cc ]; then
				[ -L /usr/bin/cc ] && rm -f /usr/bin/cc
				gen_wrapper /usr/bin/cc gcc
			fi
		fi
	fi
	pkg_setup || die "pkg_setup function failed; exiting."
}

dyn_unpack() {
	trap "abort_unpack" SIGINT SIGQUIT
	local newstuff="no"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in ${AA}; do
			echo ">>> Checking ${x}'s mtime..."
			if [ "${DISTDIR}/${x}" -nt "${WORKDIR}" ]; then
				echo ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				rm -rf "${WORKDIR}"
				break
			fi
		done
		if [ "${EBUILD}" -nt "${WORKDIR}" ]; then
			echo ">>> ${EBUILD} has been updated; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		elif [ ! -f "${BUILDDIR}/.unpacked" ]; then
			echo ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		fi
	fi
	if [ -e "${WORKDIR}" ]; then
		if [ "$newstuff" == "no" ]; then
			echo ">>> WORKDIR is up-to-date, keeping..."
			return 0
		fi
	fi
	
	install -m0700 -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	[ -d "$WORKDIR" ] && cd "${WORKDIR}"
	echo ">>> Unpacking source..."
	src_unpack
	touch "${BUILDDIR}/.unpacked" || die "IO Failure -- Failed 'touch .unpacked' in BUILDIR"
	echo ">>> Source unpacked."
	cd "$BUILDDIR"
	trap SIGINT SIGQUIT
}

dyn_clean() {
	rm -rf "${BUILDDIR}/image"
	rm -rf "${BUILDDIR}/build-info"

	if ! has keeptemp $FEATURES; then
		rm -rf "${T}"/*
	else
		mv "${T}/environment" "${T}/environment.keeptemp"
	fi

	if ! has keepwork $FEATURES; then
		rm -rf "${BUILDDIR}/.compiled"
		rm -rf "${BUILDDIR}/.unpacked"
		rm -rf "${WORKDIR}"
	fi

	if [ -f "${BUILDDIR}/.unpacked" ]; then
		find "${BUILDDIR}" -type d ! -regex "^${WORKDIR}" | sort -r | tr "\n" "\0" | $XARGS -0 rmdir &>/dev/null
	fi
	true
}

into() {
	if [ $1 == "/" ]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
		if [ ! -d "${D}${DESTTREE}" ]; then
			install -d "${D}${DESTTREE}"
		fi
	fi
}

insinto() {
	if [ "$1" == "/" ]; then
		export INSDESTTREE=""
	else
		export INSDESTTREE=$1
		if [ ! -d "${D}${INSDESTTREE}" ]; then
			install -d "${D}${INSDESTTREE}"
		fi
	fi
}

exeinto() {
	if [ "$1" == "/" ]; then
		export EXEDESTTREE=""
	else
		export EXEDESTTREE="$1"
		if [ ! -d "${D}${EXEDESTTREE}" ]; then
			install -d "${D}${EXEDESTTREE}"
		fi
	fi
}

docinto() {
	if [ "$1" == "/" ]; then
		export DOCDESTTREE=""
	else
		export DOCDESTTREE="$1"
		if [ ! -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}" ]; then
			install -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}"
		fi
	fi
}

insopts() {
	INSOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
 		else
			INSOPTIONS="$INSOPTIONS $x"
		fi
	done
	export INSOPTIONS
}

diropts() {
	DIROPTIONS=""
	for x in $*; do
		DIROPTIONS="${DIROPTIONS} $x"
	done
	export DIROPTIONS
}

exeopts() {
	EXEOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			EXEOPTIONS="$EXEOPTIONS $x"
		fi
	done
	export EXEOPTIONS
}

libopts() {
	LIBOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			LIBOPTIONS="$LIBOPTIONS $x"
		fi
	done
	export LIBOPTIONS
}

abort_handler() {
	local msg
	if [ "$2" != "fail" ]; then
		msg="${EBUILD}: ${1} aborted; exiting."
	else
		msg="${EBUILD}: ${1} failed; exiting."
	fi
	echo 
	echo "$msg" 
	echo
	eval ${3}
	#unset signal handler
	trap SIGINT SIGQUIT
}

abort_compile() {
	abort_handler "src_compile" $1
	rm -f "${BUILDDIR}/.compiled"
	exit 1
}

abort_unpack() {
	abort_handler "src_unpack" $1
	rm -f "${BUILDDIR}/.unpacked"
	rm -rf "${BUILDDIR}/work"
	exit 1
}

abort_package() {
	abort_handler "dyn_package" $1
	rm -f "${BUILDDIR}/.packaged"
	rm -f "${PKGDIR}"/All/${PF}.t*
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf "${BUILDDIR}/image"
	exit 1
}

dyn_compile() {
	trap "abort_compile" SIGINT SIGQUIT
	[ "${CFLAGS-unset}"      != "unset" ] && export CFLAGS
	[ "${CXXFLAGS-unset}"    != "unset" ] && export CXXFLAGS
	[ "${LIBCFLAGS-unset}"   != "unset" ] && export LIBCFLAGS
	[ "${LIBCXXFLAGS-unset}" != "unset" ] && export LIBCXXFLAGS
	[ "${LDFLAGS-unset}"     != "unset" ] && export LDFLAGS
	[ "${ASFLAGS-unset}"     != "unset" ] && export ASFLAGS

	[ "${DISTCC_DIR-unset}"  == "unset" ] && export DISTCC_DIR="${PORTAGE_TMPDIR}/.distcc"
	[ ! -z "${DISTCC_DIR}" ] && addwrite "${DISTCC_DIR}"

	if has noauto $FEATURES &>/dev/null && [ ! -f ${BUILDDIR}/.unpacked ]; then
		echo
		echo "!!! We apparently haven't unpacked... This is probably not what you"
		echo "!!! want to be doing... You are using FEATURES=noauto so I'll assume"
		echo "!!! that you know what you are doing... You have 5 seconds to abort..."
		echo

		echo -ne "\a"; sleep 0.25 &>/dev/null; echo -ne "\a"; sleep 0.25 &>/dev/null
		echo -ne "\a"; sleep 0.25 &>/dev/null; echo -ne "\a"; sleep 0.25 &>/dev/null
		echo -ne "\a"; sleep 0.25 &>/dev/null; echo -ne "\a"; sleep 0.25 &>/dev/null
		echo -ne "\a"; sleep 0.25 &>/dev/null; echo -ne "\a"; sleep 0.25 &>/dev/null

		echo -ne "\a"; sleep 0,25 &>/dev/null; echo -ne "\a"; sleep 0,25 &>/dev/null
		echo -ne "\a"; sleep 0,25 &>/dev/null; echo -ne "\a"; sleep 0,25 &>/dev/null
		echo -ne "\a"; sleep 0,25 &>/dev/null; echo -ne "\a"; sleep 0,25 &>/dev/null
		echo -ne "\a"; sleep 0,25 &>/dev/null; echo -ne "\a"; sleep 0,25 &>/dev/null
		sleep 3
	fi

	cd "${BUILDDIR}"
	if [ ! -e "build-info" ];	then
		mkdir build-info
	fi
	cp "${EBUILD}" "build-info/${PF}.ebuild"
	
	if [ ${BUILDDIR}/.compiled -nt "${WORKDIR}" ]; then
		echo ">>> It appears that ${PN} is already compiled; skipping."
		echo ">>> (clean to force compilation)"
		trap SIGINT SIGQUIT
		return
	fi
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages use an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	src_compile 
	#|| abort_compile "fail" 
	cd "${BUILDDIR}"
	touch .compiled
	cd build-info
	echo "$CBUILD"   > CBUILD
	echo "$CC"       > CC
	echo "$CDEPEND"  > CDEPEND
	echo "$CFLAGS"   > CFLAGS
	echo "$CHOST"    > CHOST
	echo "$CXX"      > CXX
	echo "$CXXFLAGS" > CXXFLAGS
	echo "$DEPEND"   > DEPEND
	echo "$IUSE"     > IUSE
	echo "$PKGUSE"   > PKGUSE
	echo "$LICENSE"  > LICENSE
	echo "$CATEGORY" > CATEGORY
	echo "$PDEPEND"  > PDEPEND
	echo "$PF"       > PF
	echo "$PROVIDE"  > PROVIDE
	echo "$RDEPEND"  > RDEPEND
	echo "$SLOT"     > SLOT
	echo "$USE"      > USE
	set | bzip2 -9 - > environment.bz2
	cp "${EBUILD}" "${PF}.ebuild"
	if has nostrip $FEATURES $RESTRICT; then
		touch DEBUGBUILD
	fi
	trap SIGINT SIGQUIT
}

dyn_package() {
	trap "abort_package" SIGINT SIGQUIT
	cd "${BUILDDIR}/image"
	tar cpvf - ./ | bzip2 -f > ../bin.tar.bz2 || die "Failed to create tarball"
	cd ..
	xpak build-info inf.xpak
	tbz2tool join bin.tar.bz2 inf.xpak "${PF}.tbz2"
	mv "${PF}.tbz2" "${PKGDIR}/All" || die "Failed to move tbz2 to ${PKGDIR}/All"
	rm -f inf.xpak bin.tar.bz2
	if [ ! -d "${PKGDIR}/${CATEGORY}" ]; then
		install -d "${PKGDIR}/${CATEGORY}"
	fi
	ln -sf "../All/${PF}.tbz2" "${PKGDIR}/${CATEGORY}/${PF}.tbz2" || die "Failed to create symlink in ${PKGDIR}/${CATEGORY}"
	echo ">>> Done."
	cd "${BUILDDIR}"
	touch .packaged || die "Failed to 'touch .packaged' in ${BUILDDIR}"
	trap SIGINT SIGQUIT
}

dyn_install() {
	trap "abort_install" SIGINT SIGQUIT
	rm -rf "${BUILDDIR}/image"
	mkdir "${BUILDDIR}/image"
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	echo
	echo ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	src_install 
	#|| abort_install "fail"
	prepall
	cd "${D}"

	declare -i UNSAFE=0
	for i in $(find "${D}/" -type f -perm -2002); do
		UNSAFE=$(($UNSAFE + 1))
		echo "UNSAFE SetGID: $i"
	done
	for i in $(find "${D}/" -type f -perm -4002); do
		UNSAFE=$(($UNSAFE + 1))
		echo "UNSAFE SetUID: $i"
	done
	
	if [[ $UNSAFE > 0 ]]; then
		die "There are ${UNSAFE} unsafe files. Portage will not install them."
	fi
	
	find "${D}/" -user  portage -print0 | $XARGS -0 -n100 chown root
	if [ "$USERLAND" == "BSD" ]; then
		find "${D}/" -group portage -print0 | $XARGS -0 -n100 chgrp wheel
	else
		find "${D}/" -group portage -print0 | $XARGS -0 -n100 chgrp root
	fi

	echo ">>> Completed installing into ${D}"
	echo
	cd ${BUILDDIR}
	trap SIGINT SIGQUIT
}

dyn_preinst() {
	pkg_preinst

	# set IMAGE depending if this is a binary or compile merge
	[ "${EMERGE_FROM}" == "binary" ] && IMAGE=${PKG_TMPDIR}/${PF}/bin \
					|| IMAGE=${D}

	# remove man pages
	if has noman $FEATURES; then
		rm -fR "${IMAGE}/usr/share/man"
	fi

	# remove info pages
	if has noinfo $FEATURES; then
		rm -fR "${IMAGE}/usr/share/info"
	fi

	# remove docs
	if has nodoc $FEATURES; then
		rm -fR "${IMAGE}/usr/share/doc"
	fi

	# Smart FileSystem Permissions
	if has sfperms $FEATURES; then
		for i in $(find ${IMAGE}/ -type f -perm -4000); do
			ebegin ">>> SetUID: [chmod go-r] $i "
			chmod go-r "$i"
			eend $?
		done
		for i in $(find ${IMAGE}/ -type f -perm -2000); do
			ebegin ">>> SetGID: [chmod o-r] $i "
			chmod o-r "$i"
			eend $?
		done
	fi

	# SELinux file labeling (needs to always be last in dyn_preinst)
	if use selinux; then
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f /selinux/context -a -x /usr/sbin/setfiles ]; then
			echo ">>> Setting SELinux security labels"
			if [ -f ${POLICYDIR}/file_contexts/file_contexts ]; then
				cp -f "${POLICYDIR}/file_contexts/file_contexts" "${T}"
			else
				make -C "${POLICYDIR}" FC=${T}/file_contexts "${T}/file_contexts"
			fi

			addwrite /selinux/context
			/usr/sbin/setfiles -r "${IMAGE}" "${T}/file_contexts" "${IMAGE}" \
				|| die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			echo "!!! Unable to set SELinux security labels"
		fi
	fi
	trap SIGINT SIGQUIT
}

dyn_spec() {
	tar czf "/usr/src/redhat/SOURCES/${PF}.tar.gz" "${O}/${PF}.ebuild" "${O}/files" || die "Failed to create base rpm tarball."

	cat <<__END1__ > ${PF}.spec
Summary: ${DESCRIPTION}
Name: ${PN}
Version: ${PV}
Release: ${PR}
Copyright: GPL
Group: portage/${CATEGORY}
Source: ${PF}.tar.gz
Buildroot: ${D}
%description
${DESCRIPTION}

${HOMEPAGE}

%prep
%setup -c

%build

%install

%clean

%files
/
__END1__

}

dyn_rpm() {
	dyn_spec
	rpm -bb "${PF}.spec" || die "Failed to integrate rpm spec file"
	install -D "/usr/src/redhat/RPMS/i386/${PN}-${PV}-${PR}.i386.rpm" "${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm" || die "Failed to move rpm"
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 2002 Gentoo Technologies, Inc."
	echo 
	echo "How to use the ebuild command:"
	echo 
	echo "The first argument to ebuild should be an existing .ebuild file."
	echo
	echo "One or more of the following options can then be specified.  If more"
	echo "than one option is specified, each will be executed in order."
	echo
	echo "  setup       : execute package specific setup actions"
	echo "  fetch       : download source archive(s) and patches"
	echo "  unpack      : unpack/patch sources (auto-fetch if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack if needed)"
	echo "  merge       : merge image into live filesystem, recording files in db"
	echo "                (auto-fetch/unpack/compile if needed)"
	echo "  unmerge     : remove package from live filesystem"
	echo "  package     : create tarball package of type ${PACKAGE}"
	echo "                (will be stored in ${PKGDIR}/All)"
	echo "  clean       : clean up all source and temporary files"
	echo
	echo "The following settings will be used for the ebuild process:"
	echo
	echo "  package     : ${PF}" 
	echo "  slot        : ${SLOT}" 
	echo "  category    : ${CATEGORY}" 
	echo "  description : ${DESCRIPTION}"
	echo "  system      : ${CHOST}" 
	echo "  c flags     : ${CFLAGS}" 
	echo "  c++ flags   : ${CXXFLAGS}" 
	echo "  make flags  : ${MAKEOPTS}" 
	echo -n "  build mode  : "
	if has nostrip $FEATURES $RESTRICT;	then
		echo "debug (large)"
	else
		echo "production (stripped)"
	fi
	echo "  merge to    : ${ROOT}" 
	echo
	if [ -n "$USE" ]; then
		echo "Additionally, support for the following optional features will be enabled:"
		echo 
		echo "  ${USE}"
	fi
	echo
}

# debug-print() gets called from many places with verbose status information useful
# for tracking down problems. The output is in $T/eclass-debug.log.
# You can set ECLASS_DEBUG_OUTPUT to redirect the output somewhere else as well.
# The special "on" setting echoes the information, mixing it with the rest of the
# emerge output.
# You can override the setting by exporting a new one from the console, or you can
# set a new default in make.*. Here the default is "" or unset.

# in the future might use e* from /etc/init.d/functions.sh if i feel like it
debug-print() {
	# if $T isn't defined, we're in dep calculation mode and 
	# shouldn't do anything
	[ -z "$T" ] && return 0

	while [ "$1" ]; do
	
		# extra user-configurable targets
		if [ "$ECLASS_DEBUG_OUTPUT" == "on" ]; then
			echo "debug: $1"
		elif [ -n "$ECLASS_DEBUG_OUTPUT" ]; then
			echo "debug: $1" >> $ECLASS_DEBUG_OUTPUT
		fi
		
		# default target
		echo "$1" >> "${T}/eclass-debug.log"
		# let the portage user own/write to this file
		chmod g+w "${T}/eclass-debug.log" &>/dev/null
		
		shift
	done
}

# The following 2 functions are debug-print() wrappers

debug-print-function() {
	str="$1: entering function" 
	shift
	debug-print "$str, parameters: $*"
}

debug-print-section() {
	debug-print "now in section $*"
}

# Sources all eclasses in parameters
declare -ix ECLASS_DEPTH=0
inherit() {
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ $ECLASS_DEPTH > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	local location

	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"

		# PECLASS is used to restore the ECLASS var after recursion.
		PECLASS="$ECLASS"
		export ECLASS="$1"

		# any future resolution code goes here
		if [ -n "$PORTDIR_OVERLAY" ]; then
			local overlay
			for overlay in ${PORTDIR_OVERLAY}; do
				olocation="${overlay}/eclass/${1}.eclass"
				if [ -e "$olocation" ]; then
					location="${olocation}"
					debug-print "  eclass exists: ${location}"
					break
				fi
			done
		fi
		debug-print "inherit: $1 -> $location"

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.
	
		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_DEPEND B_RDEPEND B_CDEPEND B_PDEPEND
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${CDEPEND-unset}" != "unset" ] && B_CDEPEND="${CDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset   DEPEND   RDEPEND   CDEPEND   PDEPEND
		#turn on glob expansion
		set +f
		
		source "$location" || export ERRORMSG="died sourcing $location in inherit()"
		[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"
		
		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${DEPEND-unset}"  != "unset" ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${CDEPEND-unset}" != "unset" ] && export E_CDEPEND="${E_CDEPEND} ${CDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_DEPEND-unset}"  != "unset" ] && DEPEND="${B_DEPEND}"
		[ "${B_DEPEND-unset}"  != "unset" ] || unset DEPEND

		[ "${B_RDEPEND-unset}" != "unset" ] && RDEPEND="${B_RDEPEND}"
		[ "${B_RDEPEND-unset}" != "unset" ] || unset RDEPEND

		[ "${B_CDEPEND-unset}" != "unset" ] && CDEPEND="${B_CDEPEND}"
		[ "${B_CDEPEND-unset}" != "unset" ] || unset CDEPEND

		[ "${B_PDEPEND-unset}" != "unset" ] && PDEPEND="${B_PDEPEND}"
		[ "${B_PDEPEND-unset}" != "unset" ] || unset PDEPEND

		#turn on glob expansion
 		set +f
		
		has $1 $INHERITED || export INHERITED="$INHERITED $1"

		export ECLASS="$PECLASS"
		unset PECLASS

		shift
	done
	ECLASS_DEPTH=$(($ECLASS_DEPTH - 1))
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -z "$ECLASS" ]; then
		echo "EXPORT_FUNCTIONS without a defined ECLASS" >&2
		exit 1
	fi
	while [ "$1" ]; do
		debug-print "EXPORT_FUNCTIONS: ${1} -> ${ECLASS}_${1}" 
		eval "$1() { ${ECLASS}_$1 "\$@" ; }" > /dev/null
		shift
	done
}

# adds all parameters to E_DEPEND and E_RDEPEND, which get added to DEPEND
# and RDEPEND after the ebuild has been processed. This is important to
# allow users to use DEPEND="foo" without frying dependencies added by an
# earlier inherit. It also allows RDEPEND to work properly, since a lot
# of ebuilds assume that an unset RDEPEND gets its value from DEPEND.
# Without eclasses, this is true. But with them, the eclass may set
# RDEPEND itself (or at least used to) which would prevent RDEPEND from
# getting its value from DEPEND. This is a side-effect that made eclasses
# have unreliable dependencies.

newdepend() {
	debug-print-function newdepend $*
	debug-print "newdepend: E_DEPEND=$E_DEPEND E_RDEPEND=$E_RDEPEND"

	while [ -n "$1" ]; do
		case $1 in
		"/autotools")
			do_newdepend DEPEND sys-devel/autoconf sys-devel/automake sys-devel/make
			;;
		"/c")
			do_newdepend DEPEND sys-devel/gcc virtual/glibc
			do_newdepend RDEPEND virtual/glibc
			;;
		*)
			do_newdepend DEPEND $1
			;;
		esac
		shift
	done
}

newrdepend() {
	debug-print-function newrdepend $*
	do_newdepend RDEPEND $1
}

newcdepend() {
	debug-print-function newcdepend $*
	do_newdepend CDEPEND $1
}

newpdepend() {
	debug-print-function newpdepend $*
	do_newdepend PDEPEND $1
}

do_newdepend() {
	# This function does a generic change determining whether we're in an
	# eclass or not. If we are, we change the E_* variables for deps.
	debug-print-function do_newdepend $*
	[ -z "$1" ] && die "do_newdepend without arguments"

	# Grab what we're affecting... Figure out if we're affecting eclasses.
	[[ ${ECLASS_DEPTH} > 0 ]] && TARGET="E_$1"
	[[ ${ECLASS_DEPTH} > 0 ]] || TARGET="$1"
	shift # $1 was a variable name.

	while [ -n "$1" ]; do
		# This bit of evil takes TARGET and uses it to evaluate down to a
		# variable. This is a sneaky way to make this infinately expandable.
		# The normal translation of this would look something like this:
		# E_DEPEND="${E_DEPEND} $1"  ::::::  Cool, huh? :)
		eval export ${TARGET}=\"\${${TARGET}} $1\"
		shift
	done
}

# === === === === === === === === === === === === === === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === === === === === === === === === === === === === ===

if [ "$*" != "depend" ] && [ "$*" != "clean" ]; then
	cd ${PORTAGE_TMPDIR} &> /dev/null
	cd ${BUILD_PREFIX} &> /dev/null

	if [ `id -nu` == "portage" ] ; then
		export USER=portage
	fi

	if has distcc ${FEATURES} &>/dev/null; then
		if [ -d /usr/lib/distcc/bin ]; then
			#We can enable distributed compile support
			if [ -z "${PATH/*distcc*/}" ]; then
				# Remove the other reference.
				PATH="$(echo ${PATH} | sed 's/:[^:]*distcc[^:]*:/:/;s/^[^:]*distcc[^:]*://;s/:[^:]*distcc[^:]*$//')"
			fi
			export PATH="/usr/lib/distcc/bin:${PATH}"
			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"
		elif which distcc &>/dev/null; then
			export CC="distcc $CC"
			export CXX="distcc $CXX"
		fi
	fi

	if has ccache ${FEATURES} &>/dev/null; then
		#We can enable compiler cache support
		if [ -z "${PATH/*ccache*/}" ]; then
			# Remove the other reference.
			PATH="$(echo ${PATH} | sed 's/:[^:]*ccache[^:]*:/:/;s/^[^:]*ccache[^:]*://;s/:[^:]*ccache[^:]*$//')"
		fi

		if [ -d /usr/lib/ccache/bin ]; then
			export PATH="/usr/lib/ccache/bin:${PATH}"
		elif [ -d /usr/bin/ccache ]; then
			export PATH="/usr/bin/ccache:${PATH}"
		fi

		[ -z "${CCACHE_DIR}" ] && export CCACHE_DIR="/root/.ccache"

		addread "${CCACHE_DIR}"
		addwrite "${CCACHE_DIR}"

		[ -z "${CCACHE_SIZE}" ] && export CCACHE_SIZE="2G"
		ccache -M ${CCACHE_SIZE} &> /dev/null
	fi

	# XXX: Load up the helper functions.
#	for X in /usr/lib/portage/bin/functions/*.sh; do
#		source ${X} || die "Failed to source ${X}"
#	done
	
else

killparent() {
	trap INT
	kill -KILL ${PORTAGE_MASTER_PID}
}
trap "killparent" INT

fi # "$*"!="depend" && "$*"!="clean"

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

unset   DEPEND   RDEPEND   CDEPEND   PDEPEND
unset E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND

source ${EBUILD} || die "error sourcing ebuild"
[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

#a reasonable default for $S
if [ "$S" = "" ]; then
	export S=${WORKDIR}/${P}
fi

#some users have $TMP/$TMPDIR to a custom dir in their home ...
#this will cause sandbox errors with some ./configure
#scripts, so set it to $T.
export TMP="${T}"
export TMPDIR="${T}"

# Note: this next line is not the same as export RDEPEND=${RDEPEND:-${DEPEND}}
# That will test for unset *or* NULL ("").  We want just to set for unset...

#turn off glob expansion from here on in to prevent *'s and ? in the DEPEND
#syntax from getting expanded :)  Fixes bug #1473
set -f
#if [ -z "`set | grep ^RDEPEND=`" ]; then
if [ "${RDEPEND-unset}" == "unset" ]; then
	export RDEPEND=${DEPEND}
	debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
fi

#add in dependency info from eclasses
DEPEND="$DEPEND $E_DEPEND"
RDEPEND="$RDEPEND $E_RDEPEND"
CDEPEND="$CDEPEND $E_CDEPEND"
PDEPEND="$PDEPEND $E_PDEPEND"

set +f

for myarg in $*; do
	case $myarg in
	nofetch)
		pkg_nofetch
		exit 1
		;;
	prerm|postrm|postinst|config)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			pkg_${myarg}
			#Allow non-zero return codes since they can be caused by &&
		else
			set -x
			pkg_${myarg}
			#Allow non-zero return codes since they can be caused by &&
			set +x
		fi
		;;
	unpack|compile|clean|install)
		if [ "${SANDBOX_DISABLED="0"}" == "0" ]; then
			export SANDBOX_ON="1"
		else
			export SANDBOX_ON="0"
		fi
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
			#Allow non-zero return codes since they can be caused by &&
		else
			set -x
			dyn_${myarg}
			#Allow non-zero return codes since they can be caused by &&
			set +x
		fi
		export SANDBOX_ON="0"
		;;
	help|clean|setup|preinst)
		#pkg_setup needs to be out of the sandbox for tmp file creation;
		#for example, awking and piping a file in /tmp requires a temp file to be created
		#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		;;
	package|rpm)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		;;
	depend)
		export SANDBOX_ON="0"
		set -f
		#the extra `echo` commands remove newlines
		dbkey=${PORTAGE_CACHEDIR}/${CATEGORY}/${PF}
		if [ ! -d ${PORTAGE_CACHEDIR}/${CATEGORY} ]; then
			install -d -g ${PORTAGE_GID} -m4775 "${PORTAGE_CACHEDIR}/${CATEGORY}"
		fi
		# Make it group writable. 666&~002==664
		umask 002
		echo `echo "$DEPEND"`       > $dbkey
		echo `echo "$RDEPEND"`     >> $dbkey
		echo `echo "$SLOT"`        >> $dbkey
		echo `echo "$SRC_URI"`     >> $dbkey
		echo `echo "$RESTRICT"`    >> $dbkey
		echo `echo "$HOMEPAGE"`    >> $dbkey
		echo `echo "$LICENSE"`     >> $dbkey
		echo `echo "$DESCRIPTION"` >> $dbkey
		echo `echo "$KEYWORDS"`    >> $dbkey
		echo `echo "$INHERITED"`   >> $dbkey
		echo `echo "$IUSE"`        >> $dbkey
		echo `echo "$CDEPEND"`     >> $dbkey
		echo `echo "$PDEPEND"`     >> $dbkey
		set +f
		#make sure it is writable by our group:
		exit 0
		;;
	*)
		export SANDBOX_ON="1"
		echo "Please specify a valid command."
		echo
		dyn_help
		exit 1
		;;
	esac
	if [ $? -ne 0 ]; then
		exit 1
	fi
done

if [ "$myarg" != "clean" ]; then
	# Save current environment and touch a success file. (echo for success)
	umask 002
	set | egrep -v "^SANDBOX_" > "${T}/environment" 2>/dev/null
	chown portage:portage "${T}/environment" &>/dev/null
	chmod g+w "${T}/environment" &>/dev/null
fi
touch "${T}/successful"  &>/dev/null
chown portage:portage "${T}/successful" &>/dev/null
chmod g+w "${T}/successful" &>/dev/null

exit 0
