#!/bin/bash
# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

export SANDBOX_PREDICT="${SANDBOX_PREDICT}:/proc/self/maps:/dev/console:/usr/lib/portage/pym:/dev/random"
export SANDBOX_WRITE="${SANDBOX_WRITE}:/dev/shm:${PORTAGE_TMPDIR}"
export SANDBOX_READ="${SANDBOX_READ}:/dev/shm:${PORTAGE_TMPDIR}"

if [ "$*" != "depend" ] && [ "$*" != "clean" ] && [ "$*" != "nofetch" ]; then
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
			{ $0 "$@" || rm -f "${T}/successful" ; } 2>&1 \
			  | tee -i -a "${PORT_LOGDIR}/${LOG_COUNTER}-${PF}.log"
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

declare -rx EBUILD_PHASE="$*"

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && old_IFS="${IFS}"'
alias restore_IFS='if [ "${old_IFS:-unset}" != "unset" ]; then IFS="${old_IFS}"; unset old_IFS; else unset IFS; fi'

OCC="$CC"
OCXX="$CXX"
if [ "$USERLAND" == "GNU" ]; then
	source /etc/profile.env &>/dev/null
fi
if [ -f "${PORTAGE_BASHRC}" ]; then
	source "${PORTAGE_BASHRC}"
fi
[ ! -z "$OCC" ] && export CC="$OCC"
[ ! -z "$OCXX" ] && export CXX="$OCXX"

export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin:${ROOTPATH}"
[ ! -z "$PREROOTPATH" ] && export PATH="${PREROOTPATH%%:}:$PATH"

if [ -e /etc/init.d/functions.sh ]; then
	source /etc/init.d/functions.sh  &>/dev/null
elif [ -e /etc/rc.d/config/functions ];	then
	source /etc/rc.d/config/functions &>/dev/null
else
	#Mac OS X
	source /usr/lib/portage/bin/functions.sh &>/dev/null
fi

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex, bug #60147)
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


# source the existing profile.bashrc's.
save_IFS
IFS=$'\n'
for dir in ${PROFILE_PATHS}; do
	if [ -f "${dir}/profile.bashrc" ]; then
		source "${dir}/profile.bashrc"
	fi
done
restore_IFS


esyslog() {
	# Custom version of esyslog() to take care of the "Red Star" bug.
	# MUST follow functions.sh to override the "" parameter problem.
	return 0
}


use() {
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

usev() {
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

useq() {
	local u="${1}"
	local neg=0
	if [ "${u:0:1}" == "!" ]; then
		u="${u:1}"
		neg=1
	fi
	local x
	
	# Make sure we have this USE flag in IUSE
	if ! hasq "${u}" ${IUSE} ${E_IUSE} && ! hasq "${u}" ${PORTAGE_ARCHLIST} selinux; then
		echo "QA Notice: USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}" >&2
	fi

	for x in ${USE}; do
		if [ "${x}" == "${u}" ]; then
			if [ ${neg} -eq 1 ]; then
				return 1
			else
				return 0
			fi
		fi
	done
	if [ ${neg} -eq 1 ]; then
		return 0
	else
		return 1
	fi
}

has() {
	if hasq "$@"; then
		echo "${1}"
		return 0
	fi
	return 1
}

hasv() {
	if hasq "$@"; then
		echo "${1}"
		return 0
	fi
	return 1
}

hasq() {
	local x

	local me=$1
	shift
	
	# All the TTY checks really only help out depend. Which is nice.
	# Logging kills all this anyway. Everything becomes a pipe. --NJ
	for x in "$@"; do
		if [ "${x}" == "${me}" ]; then
			return 0
		fi
	done
	return 1
}

has_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		echo -n "QA Notice: has_version() in global scope: " >&2
		if [ ${ECLASS_DEPTH} -gt 0 ]; then
			echo "eclass ${ECLASS}" >&2
		else
			echo "${CATEGORY}/${PF}" >&2
		fi
	fi
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	if /usr/lib/portage/bin/portageq 'has_version' "${ROOT}" "$1"; then
		return 0
	else
		return 1
	fi
}

portageq() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		echo -n "QA Notice: portageq in global scope: " >&2
		if [ ${ECLASS_DEPTH} -gt 0 ]; then
			echo "eclass ${ECLASS}" >&2
		else
			echo "${CATEGORY}/${PF}" >&2
		fi
	fi
	/usr/lib/portage/bin/portageq "$@"
}


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------


best_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		echo -n "QA Notice: best_version() in global scope: " >&2
		if [ ${ECLASS_DEPTH} -gt 0 ]; then
			echo "eclass ${ECLASS}" >&2
		else
			echo "${CATEGORY}/${PF}" >&2
		fi
	fi
	# returns the best/most-current match.
	# Takes single depend-type atoms.
	/usr/lib/portage/bin/portageq 'best_version' "${ROOT}" "$1"
}

use_with() {
	if [ -z "$1" ]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return 1
	fi

	local UW_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UW_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if useq $1; then
		echo "--with-${UWORD}${UW_SUFFIX}"
	else
		echo "--without-${UWORD}"
	fi
	return 0
}

use_enable() {
	if [ -z "$1" ]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return 1
	fi

	local UE_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UE_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if useq $1; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
	else
		echo "--disable-${UWORD}"
	fi
	return 0
}

diefunc() {
	local funcname="$1" lineno="$2" exitcode="$3"
	shift 3
	echo >&2
	echo "!!! ERROR: $CATEGORY/$PF failed." >&2
	echo "!!! Function $funcname, Line $lineno, Exitcode $exitcode" >&2
	echo "!!! ${*:-(no error message)}" >&2
	echo "!!! If you need support, post the topmost build error, NOT this status message." >&2
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
		y="${x%.*}"
		y="${y##*.}"

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
		if hasq autoconfig $FEATURES && ! hasq autoconfig $RESTRICT; then
			if [ -e /usr/share/gnuconfig/ -a -x /bin/basename ]; then
				local x
				for x in $(find ${S} -type f -name config.guess -o -name config.sub) ; do
					einfo "econf: updating $x with /usr/share/gnuconfig/$(/bin/basename ${x})"
					cp /usr/share/gnuconfig/$(/bin/basename ${x}) ${x}
				done
			fi
		fi
		if [ ! -z "${CBUILD}" ]; then
			EXTRA_ECONF="--build=${CBUILD} ${EXTRA_ECONF}"
		fi
		
		# if the profile defines a location to install libs to aside from default, pass it on.
		if [ ! -z "${ECONF_LIBDIR}" ]; then
			EXTRA_ECONF="--libdir=/usr/${ECONF_LIBDIR} ${EXTRA_ECONF}"
		fi
		
		echo ./configure \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			${EXTRA_ECONF} \
			"$@"

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
	fi
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

src_test()
{
	addpredict /
	if make check -n &> /dev/null; then
		echo ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! make check; then
			hasq maketest $FEATURES && die "Make check failed. See above for details."
			hasq maketest $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif make test -n &> /dev/null; then
		echo ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! make test; then
			hasq maketest $FEATURES && die "Make test failed. See above for details."
			hasq maketest $FEATURES || eerror "Make test failed. See above for details."
		fi
	else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT="${SANDBOX_PREDICT%:/}"
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

pkg_config()
{
	eerror "This ebuild does not have a config function."
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
	pkg_setup
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

	if ! hasq keeptemp $FEATURES; then
		rm -rf "${T}"/*
	else
		mv "${T}/environment" "${T}/environment.keeptemp"
	fi

	if ! hasq keepwork $FEATURES; then
		rm -rf "${BUILDDIR}/.compiled"
		rm -rf "${BUILDDIR}/.unpacked"
		rm -rf "${BUILDDIR}/.installed"
		rm -rf "${BUILDDIR}/build-info"
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
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
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
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
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
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
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

abort_test() {
	abort_handler "dyn_test" $1
	rm -f "${BUILDDIR}/.tested"
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

	if hasq noauto $FEATURES &>/dev/null && [ ! -f ${BUILDDIR}/.unpacked ]; then
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

	echo "$ASFLAGS"     > ASFLAGS
	echo "$CBUILD"      > CBUILD
	echo "$CC"          > CC
	echo "$CDEPEND"     > CDEPEND
	echo "$CFLAGS"      > CFLAGS
	echo "$CHOST"       > CHOST
	echo "$CXX"         > CXX
	echo "$CXXFLAGS"    > CXXFLAGS
	echo "$DEPEND"      > DEPEND
	echo "$IUSE"        > IUSE
	echo "$PKGUSE"      > PKGUSE
	echo "$LDFLAGS"     > LDFLAGS
	echo "$LIBCFLAGS"   > LIBCFLAGS
	echo "$LIBCXXFLAGS" > LIBCXXFLAGS
	echo "$LICENSE"     > LICENSE
	echo "$CATEGORY"    > CATEGORY
	echo "$PDEPEND"     > PDEPEND
	echo "$PF"          > PF
	echo "$PROVIDE"     > PROVIDE
	echo "$RDEPEND"     > RDEPEND
	echo "$SLOT"        > SLOT
	echo "$USE"         > USE
	set | bzip2 -9 -    > environment.bz2
	cp "${EBUILD}" "${PF}.ebuild"
	if hasq nostrip $FEATURES $RESTRICT; then
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


dyn_test() {
	trap "abort_test" SIGINT SIGQUIT
	cd "${S}"

	if hasq maketest $RESTRICT; then
		ewarn "Skipping make test/check due to ebuild restriction."
		echo ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	elif ! hasq maketest $FEATURES; then
		echo ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	else
		src_test
	fi

	cd "${BUILDDIR}"
	touch .tested || die "Failed to 'touch .tested' in ${BUILDDIR}"
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
	
	find "${D}/" -user portage -print0 | $XARGS -0 -n100 chown root
	if [ "$USERLAND" == "BSD" ]; then
		find "${D}/" -group portage -print0 | $XARGS -0 -n100 chgrp wheel
	else
		find "${D}/" -group portage -print0 | $XARGS -0 -n100 chgrp root
	fi

	touch "${BUILDDIR}/.installed"
	echo ">>> Completed installing into ${D}"
	echo
	cd ${BUILDDIR}
	trap SIGINT SIGQUIT
}

dyn_preinst() {
	# set IMAGE depending if this is a binary or compile merge
	[ "${EMERGE_FROM}" == "binary" ] && IMAGE=${PKG_TMPDIR}/${PF}/bin \
					|| IMAGE=${D}

	pkg_preinst

	# remove man pages
	if hasq noman $FEATURES; then
		rm -fR "${IMAGE}/usr/share/man"
	fi

	# remove info pages
	if hasq noinfo $FEATURES; then
		rm -fR "${IMAGE}/usr/share/info"
	fi

	# remove docs
	if hasq nodoc $FEATURES; then
		rm -fR "${IMAGE}/usr/share/doc"
	fi

	# remove share dir if unnessesary
	if hasq nodoc $FEATURES -o hasq noman $FEATURES -o hasq noinfo $FEATURES; then
		rmdir "${IMAGE}/usr/share" &> /dev/null
	fi

	# Smart FileSystem Permissions
	if hasq sfperms $FEATURES; then
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

	# total suid control.
	if hasq suidctl $FEATURES > /dev/null ; then
		sfconf=/etc/portage/suidctl.conf
		echo ">>> Preforming suid scan in ${IMAGE}"
		for i in $(find ${IMAGE}/ -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				suid="`grep ^${i/${IMAGE}/}$ ${sfconf}`"
				if [ "${suid}" = "${i/${IMAGE}/}" ]; then
					echo "- ${i/${IMAGE}/} is an approved suid file"
				else
					echo ">>> Removing sbit on non registered ${i/${IMAGE}/}"
					for x in 5 4 3 2 1 0; do echo -ne "\a"; sleep 0.25 ; done
					echo -ne "\a"
					chmod ugo-s "${i}"
					grep ^#${i/${IMAGE}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						echo ">>> Appending commented out entry to ${sfconf} for ${PF}"
						ls_ret=`ls -ldh "${i}"`
						echo "## ${ls_ret%${IMAGE}*}${ls_ret#*${IMAGE}}" >> ${sfconf}
						echo "#${i/${IMAGE}/}" >> ${sfconf}
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				echo "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi

	# SELinux file labeling (needs to always be last in dyn_preinst)
	if useq selinux; then
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
	rpmbuild -bb "${PF}.spec" || die "Failed to integrate rpm spec file"
	install -D "/usr/src/redhat/RPMS/i386/${PN}-${PV}-${PR}.i386.rpm" "${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm" || die "Failed to move rpm"
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2004 Gentoo Foundation"
	echo
	echo "How to use the ebuild command:"
	echo
	echo "The first argument to ebuild should be an existing .ebuild file."
	echo
	echo "One or more of the following options can then be specified.  If more"
	echo "than one option is specified, each will be executed in order."
	echo
	echo "  help        : show this help screen"
	echo "  setup       : execute package specific setup actions"
	echo "  fetch       : download source archive(s) and patches"
	echo "  digest      : creates a digest and a manifest file for the package"
	echo "  manifest    : creates a manifest file for the package"
	echo "  unpack      : unpack/patch sources (auto-fetch if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack if needed)"
	echo "  test        : test package (auto-fetch/unpack/compile if needed)"
	echo "  preinst     : execute pre-install instructions"
	echo "  postinst    : execute post-install instructions"
	echo "  install     : installs the package to the temporary install directory"
	echo "  qmerge      : merge image into live filesystem, recording files in db"
	echo "  merge       : does fetch, unpack, compile, install and qmerge"
	echo "  prerm       : execute pre-removal instructions"
	echo "  postrm      : execute post-removal instructions"
	echo "  unmerge     : remove package from live filesystem"
	echo "  config      : execute package specific configuration actions"
	echo "  package     : create tarball package in ${PKGDIR}/All"
	echo "  rpm         : builds a RedHat RPM package"
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
	if hasq nostrip $FEATURES $RESTRICT; then
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
	local PECLASS

	local B_IUSE
	local B_DEPEND
	local B_RDEPEND
	local B_CDEPEND
	local B_PDEPEND
	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"

		# PECLASS is used to restore the ECLASS var after recursion.
		PECLASS="$ECLASS"
		export ECLASS="$1"

		if [ "$EBUILD_PHASE" != "depend" ]; then
			if ! hasq $ECLASS $INHERITED; then
				echo
				echo "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF" >&2
				echo
			fi
		fi

		# any future resolution code goes here
		if [ -n "$PORTDIR_OVERLAY" ]; then
			local overlay
			for overlay in ${PORTDIR_OVERLAY}; do
				olocation="${overlay}/eclass/${1}.eclass"
				if [ -e "$olocation" ]; then
					location="${olocation}"
					debug-print "  eclass exists: ${location}"
				fi
			done
		fi
		debug-print "inherit: $1 -> $location"

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.
	
		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_IUSE B_DEPEND B_RDEPEND B_CDEPEND B_PDEPEND
		[ "${IUSE-unset}"    != "unset" ] && B_IUSE="${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${CDEPEND-unset}" != "unset" ] && B_CDEPEND="${CDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset   IUSE   DEPEND   RDEPEND   CDEPEND   PDEPEND
		#turn on glob expansion
		set +f
		
		source "$location" || export ERRORMSG="died sourcing $location in inherit()"
		[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"
		
		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${IUSE-unset}"    != "unset" ] && export E_IUSE="${E_IUSE} ${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${CDEPEND-unset}" != "unset" ] && export E_CDEPEND="${E_CDEPEND} ${CDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_IUSE-unset}"    != "unset" ] && IUSE="${B_IUSE}"
		[ "${B_IUSE-unset}"    != "unset" ] || unset IUSE

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
		
		hasq $1 $INHERITED || export INHERITED="$INHERITED $1"

		export ECLASS="$PECLASS"

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
			do_newdepend DEPEND sys-devel/gcc virtual/libc
			do_newdepend RDEPEND virtual/libc
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
		eval export ${TARGET}=\"\${${TARGET}} \$1\"
		shift
	done
}

# this is a function for removing any directory matching a passed in pattern from
# PATH
remove_path_entry() {
	save_IFS
	IFS=":"
	stripped_path="${PATH}"
	while [ -n "$1" ]; do
		cur_path=""
		for p in ${stripped_path}; do
			if [ "${p/${1}}" == "${p}" ]; then
				cur_path="${cur_path}:${p}"
			fi
		done
		stripped_path="${cur_path#:*}"
		shift
	done
	restore_IFS
	PATH="${stripped_path}"
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

	if hasq distcc ${FEATURES} &>/dev/null; then
		if [ -d /usr/lib/distcc/bin ]; then
			#We can enable distributed compile support
			if [ -z "${PATH/*distcc*/}" ]; then
				# Remove the other reference.
				remove_path_entry "distcc"
			fi
			export PATH="/usr/lib/distcc/bin:${PATH}"
			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"
		elif which distcc &>/dev/null; then
			export CC="distcc $CC"
			export CXX="distcc $CXX"
		fi
	fi

	if hasq ccache ${FEATURES} &>/dev/null; then
		#We can enable compiler cache support
		if [ -z "${PATH/*ccache*/}" ]; then
			# Remove the other reference.
			remove_path_entry "ccache"
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
	kill ${PORTAGE_MASTER_PID}
}
trap "killparent" INT

fi # "$*"!="depend" && "$*"!="clean"

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND

declare -r T P PN PV PVR PR A D EBUILD EMERGE_FROM O PPID FILESDIR
declare -r PORTAGE_TMPDIR

QA_INTERCEPTORS="javac java-config python python-config perl grep egrep fgrep sed gcc g++ cc bash awk nawk gawk pkg-config"
# level the QA interceptors if we're in depend
if hasq "depend" "$@"; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=`type -pf ${BIN}`
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		FUNC_SRC="${BIN}() {
		echo -n \"QA Notice: ${BIN} in global scope: \" >&2
		if [ \$ECLASS_DEPTH -gt 0 ]; then
			echo \"eclass \${ECLASS}\" >&2
		else
			echo \"\${CATEGORY}/\${PF}\" >&2
		fi
		${BODY}
		}";
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset src bin_path body
fi

source ${EBUILD} || die "error sourcing ebuild"
[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

# Expand KEYWORDS
# We need to turn off pathname expansion for -* in KEYWORDS and
# we need to escape ~ to avoid tilde expansion
set -f
KEYWORDS="`eval echo ${KEYWORDS//~/\\~}`"
set +f

hasq nostrip ${RESTRICT} && export DEBUGBUILD=1

#a reasonable default for $S
if [ "$S" = "" ]; then
	export S=${WORKDIR}/${P}
fi

#wipe the interceptors.  we don't want saved.
if hasq "depend" "$@"; then
	unset -f $QA_INTERCEPTORS
	unset QA_INTERCEPTORS
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
if [ "${RDEPEND-unset}" == "unset" ]; then
	export RDEPEND=${DEPEND}
	debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
fi

#add in dependency info from eclasses
IUSE="$IUSE $E_IUSE"
DEPEND="$DEPEND $E_DEPEND"
RDEPEND="$RDEPEND $E_RDEPEND"
CDEPEND="$CDEPEND $E_CDEPEND"
PDEPEND="$PDEPEND $E_PDEPEND"

unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND

if [ "${EBUILD_PHASE}" != "depend" ]; then
	# Lock the dbkey variables after the global phase
	declare -r DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE DESCRIPTION
	declare -r KEYWORDS INHERITED IUSE CDEPEND PDEPEND PROVIDE
fi

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
	unpack|compile|test|clean|install)
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

		# Handled in portage.py now
		#dbkey=${PORTAGE_CACHEDIR}/${CATEGORY}/${PF}

		if [ ! -d "${dbkey%/*}" ]; then
			install -d -g ${PORTAGE_GID} -m2775 "${dbkey%/*}"
		fi

		# Make it group writable. 666&~002==664
		umask 002

		#the extra `echo` commands remove newlines
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
		echo `echo "$PROVIDE"`     >> $dbkey
		echo `echo "$UNUSED_01"`   >> $dbkey
		echo `echo "$UNUSED_02"`   >> $dbkey
		echo `echo "$UNUSED_03"`   >> $dbkey
		echo `echo "$UNUSED_04"`   >> $dbkey
		echo `echo "$UNUSED_05"`   >> $dbkey
		echo `echo "$UNUSED_06"`   >> $dbkey
		echo `echo "$UNUSED_07"`   >> $dbkey
		echo `echo "$UNUSED_08"`   >> $dbkey
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

	#if [ $? -ne 0 ]; then
	#	exit 1
	#fi
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
