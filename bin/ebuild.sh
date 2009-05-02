#!/bin/bash
# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: ebuild.sh 13570 2009-04-30 21:14:27Z zmedico $

PORTAGE_BIN_PATH="${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}"
PORTAGE_PYM_PATH="${PORTAGE_PYM_PATH:-/usr/lib/portage/pym}"

export SANDBOX_PREDICT="${SANDBOX_PREDICT:+${SANDBOX_PREDICT}:}/proc/self/maps:/dev/console:/dev/random"
export SANDBOX_WRITE="${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/shm:/dev/stdout:/dev/stderr:${PORTAGE_TMPDIR}"
export SANDBOX_READ="${SANDBOX_READ:+${SANDBOX_READ}:}/:/dev/shm:/dev/stdin:${PORTAGE_TMPDIR}"
# Don't use sandbox's BASH_ENV for new shells because it does
# 'source /etc/profile' which can interfere with the build
# environment by modifying our PATH.
unset BASH_ENV

# sandbox's bashrc sources /etc/profile which unsets ROOTPATH,
# so we have to back it up and restore it.
if [ -n "${PORTAGE_ROOTPATH}" ] ; then
	export ROOTPATH=${PORTAGE_ROOTPATH}
	unset PORTAGE_ROOTPATH
fi

if [ ! -z "${PORTAGE_GPG_DIR}" ]; then
	SANDBOX_PREDICT="${SANDBOX_PREDICT}:${PORTAGE_GPG_DIR}"
fi

# These two functions wrap sourcing and calling respectively.  At present they
# perform a qa check to make sure eclasses and ebuilds and profiles don't mess
# with shell opts (shopts).  Ebuilds/eclasses changing shopts should reset them 
# when they are done.

qa_source() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	source "$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while sourcing '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while sourcing '$*'"
	return $retval
}

qa_call() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	"$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while calling '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while calling '$*'"
	return $retval
}

# Subshell/helper die support (must export for the die helper).
export EBUILD_MASTER_PID=$$
trap 'exit 1' SIGTERM

EBUILD_SH_ARGS="$*"

shift $#

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE

ROOTPATH=${ROOTPATH##:}
ROOTPATH=${ROOTPATH%%:}
PREROOTPATH=${PREROOTPATH##:}
PREROOTPATH=${PREROOTPATH%%:}
PATH=$PORTAGE_BIN_PATH/ebuild-helpers:$PREROOTPATH${PREROOTPATH:+:}/usr/local/sbin:/sbin:/usr/sbin:/usr/local/bin:/bin:/usr/bin${ROOTPATH:+:}$ROOTPATH
export PATH

source "${PORTAGE_BIN_PATH}/isolated-functions.sh"  &>/dev/null

# Set IMAGE for minimal backward compatibility with
# overlays or user's bashrc, but don't export it.
[ "${EBUILD_PHASE}" == "preinst" ] && IMAGE=${D}

[[ $PORTAGE_QUIET != "" ]] && export PORTAGE_QUIET

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex)
_sb_append_var() {
	local _v=$1 ; shift
	local var="SANDBOX_${_v}"
	[[ -z $1 || -n $2 ]] && die "Usage: add$(echo ${_v} | \
		LC_ALL=C tr [:upper:] [:lower:]) <colon-delimited list of paths>"
	export ${var}="${!var:+${!var}:}$1"
}
# bash-4 version:
# local var="SANDBOX_${1^^}"
# addread() { _sb_append_var ${0#add} "$@" ; }
addread()    { _sb_append_var READ    "$@" ; }
addwrite()   { _sb_append_var WRITE   "$@" ; }
adddeny()    { _sb_append_var DENY    "$@" ; }
addpredict() { _sb_append_var PREDICT "$@" ; }

lchown() {
	chown -h "$@"
}

lchgrp() {
	chgrp -h "$@"
}

esyslog() {
	# Custom version of esyslog() to take care of the "Red Star" bug.
	# MUST follow functions.sh to override the "" parameter problem.
	return 0
}

use() {
	useq ${1}
}

usev() {
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

useq() {
	local u=$1
	local found=0

	# if we got something like '!flag', then invert the return value
	if [[ ${u:0:1} == "!" ]] ; then
		u=${u:1}
		found=1
	fi

	# Make sure we have this USE flag in IUSE
	if [[ -n $PORTAGE_IUSE && -n $EBUILD_PHASE ]] ; then
		[[ $u =~ $PORTAGE_IUSE ]] || \
			eqawarn "QA Notice: USE Flag '${u}' not" \
				"in IUSE for ${CATEGORY}/${PF}"
	fi

	if hasq ${u} ${USE} ; then
		return ${found}
	else
		return $((!found))
	fi
}

has_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (has_version calls portageq) are not allowed in the global scope"
	fi
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
	"${PORTAGE_BIN_PATH}"/portageq has_version "${ROOT}" "$1"
	local retval=$?
	case "${retval}" in
		0)
			return 0
			;;
		1)
			return 1
			;;
		*)
			die "unexpected portageq exit code: ${retval}"
			;;
	esac
}

portageq() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls are not allowed in the global scope"
	fi
	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
	"${PORTAGE_BIN_PATH}/portageq" "$@"
}


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------


best_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (best_version calls portageq) are not allowed in the global scope"
	fi
	# returns the best/most-current match.
	# Takes single depend-type atoms.
	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
	"${PORTAGE_BIN_PATH}/portageq" 'best_version' "${ROOT}" "$1"
	local retval=$?
	case "${retval}" in
		0)
			return 0
			;;
		1)
			return 1
			;;
		*)
			die "unexpected portageq exit code: ${retval}"
			;;
	esac
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

register_die_hook() {
	export EBUILD_DEATH_HOOKS="${EBUILD_DEATH_HOOKS} $*"
}

# Ensure that $PWD is sane whenever possible, to protect against
# exploitation of insecure search path for python -c in ebuilds.
# See bug #239560.
if ! hasq "$EBUILD_PHASE" clean cleanrm depend help ; then
	cd "$PORTAGE_BUILDDIR" || \
		die "PORTAGE_BUILDDIR does not exist: '$PORTAGE_BUILDDIR'"
else
	# Don't try to create this when it's parent
	# directory doesn't necessarily exist.
	unset EBUILD_EXIT_STATUS_FILE
fi

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022
export DESTTREE=/usr
export INSDESTTREE=""
export _E_EXEDESTTREE_=""
export _E_DOCDESTTREE_=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}

check_KV() {
	if [ -z "${KV}" ]; then
		eerror ""
		eerror "Could not determine your kernel version."
		eerror "Make sure that you have a /usr/src/linux symlink,"
		eerror "and that the indicated kernel has been configured."
		eerror "You can also simply run the following command"
		eerror "in the directory referenced by /usr/src/linux:"
		eerror " make include/linux/version.h"
		eerror ""
		die
	fi
}

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir() {
	dodir "$@"
	local x
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${D}%p/.keep_${CATEGORY}_${PN}-${SLOT}\n" \
			| tr "\n" "\0" | ${XARGS} -0 -n100 touch || \
			die "Failed to recursively create .keep files"
	else
		for x in "$@"; do
			touch "${D}${x}/.keep_${CATEGORY}_${PN}-${SLOT}" || \
				die "Failed to create .keep in ${D}${x}"
		done
	fi
}

unpack() {
	local srcdir
	local x
	local y
	local myfail
	local eapi=${EAPI:-0}
	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		vecho ">>> Unpacking ${x} to ${PWD}"
		y=${x%.*}
		y=${y##*.}

		if [[ ${x} == "./"* ]] ; then
			srcdir=""
		elif [[ ${x} == ${DISTDIR%/}/* ]] ; then
			die "Arguments to unpack() cannot begin with \${DISTDIR}."
		elif [[ ${x} == "/"* ]] ; then
			die "Arguments to unpack() cannot be absolute"
		else
			srcdir="${DISTDIR}/"
		fi
		[[ ! -s ${srcdir}${x} ]] && die "${x} does not exist"

		_unpack_tar() {
			if [ "${y}" == "tar" ]; then
				$1 -dc "$srcdir$x" | tar xof -
				assert "$myfail"
			else
				$1 -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
			fi
		}

		myfail="failure unpacking ${x}"
		case "${x##*.}" in
			tar)
				tar xof "$srcdir$x" || die "$myfail"
				;;
			tgz)
				tar xozf "$srcdir$x" || die "$myfail"
				;;
			tbz|tbz2)
				bzip2 -dc "$srcdir$x" | tar xof -
				assert "$myfail"
				;;
			ZIP|zip|jar)
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|Z|z)
				_unpack_tar gzip
				;;
			bz2|bz)
				_unpack_tar bzip2
				;;
			7Z|7z)
				local my_output
				my_output="$(7z x -y "${srcdir}${x}")"
				if [ $? -ne 0 ]; then
					echo "${my_output}" >&2
					die "$myfail"
				fi
				;;
			RAR|rar)
				unrar x -idq -o+ "${srcdir}${x}" || die "$myfail"
				;;
			LHa|LHA|lha|lzh)
				lha xfq "${srcdir}${x}" || die "$myfail"
				;;
			a)
				ar x "${srcdir}${x}" || die "$myfail"
				;;
			deb)
				# Unpacking .deb archives can not always be done with
				# `ar`.  For instance on AIX this doesn't work out.  If
				# we have `deb2targz` installed, prefer it over `ar` for
				# that reason.  We just make sure on AIX `deb2targz` is
				# installed.
				if type -P deb2targz > /dev/null; then
					y=${x##*/}
					local created_symlink=0
					if [ ! "$srcdir$x" -ef "$y" ] ; then
						# deb2targz always extracts into the same directory as
						# the source file, so create a symlink in the current
						# working directory if necessary.
						ln -sf "$srcdir$x" "$y" || die "$myfail"
						created_symlink=1
					fi
					deb2targz "$y" || die "$myfail"
					if [ $created_symlink = 1 ] ; then
						# Clean up the symlink so the ebuild
						# doesn't inadvertently install it.
						rm -f "$y"
					fi
					mv -f "${y%.deb}".tar.gz data.tar.gz || die "$myfail"
				else
					ar x "$srcdir$x" || die "$myfail"
				fi
				;;
			lzma)
				_unpack_tar lzma
				;;
			xz)
				if hasq $eapi 0 1 2 ; then
					vecho "unpack ${x}: file format not recognized. Ignoring."
				else
					_unpack_tar xz
				fi
				;;
			*)
				vecho "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
	# Do not chmod '.' since it's probably ${WORKDIR} and PORTAGE_WORKDIR_MODE
	# should be preserved.
	find . -mindepth 1 -maxdepth 1 ! -type l -print0 | \
		${XARGS} -0 chmod -fR a+rX,u+w,g-w,o-w
}

strip_duplicate_slashes() {
	if [[ -n $1 ]] ; then
		local removed=$1
		while [[ ${removed} == *//* ]] ; do
			removed=${removed//\/\///}
		done
		echo ${removed}
	fi
}

hasg() {
    local x s=$1
    shift
    for x ; do [[ ${x} == ${s} ]] && echo "${x}" && return 0 ; done
    return 1
}
hasgq() { hasg "$@" >/dev/null ; }
econf() {
	local x

	local phase_func=$(_ebuild_arg_to_phase "$EAPI" "$EBUILD_PHASE")
	if [[ -n $phase_func ]] ; then
		if hasq "$EAPI" 0 1 ; then
			[[ $phase_func != src_compile ]] && \
				eqawarn "QA Notice: econf called in" \
					"$phase_func instead of src_compile"
		else
			[[ $phase_func != src_configure ]] && \
				eqawarn "QA Notice: econf called in" \
					"$phase_func instead of src_configure"
		fi
	fi

	: ${ECONF_SOURCE:=.}
	if [ -x "${ECONF_SOURCE}/configure" ]; then
		if [ -e /usr/share/gnuconfig/ ]; then
			find "${WORKDIR}" -type f '(' \
			-name config.guess -o -name config.sub ')' -print0 | \
			while read -d $'\0' x ; do
				vecho " * econf: updating ${x/${WORKDIR}\/} with /usr/share/gnuconfig/${x##*/}"
				cp -f /usr/share/gnuconfig/"${x##*/}" "${x}"
			done
		fi

		# if the profile defines a location to install libs to aside from default, pass it on.
		# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
		local CONF_LIBDIR LIBDIR_VAR="LIBDIR_${ABI}"
		if [[ -n ${ABI} && -n ${!LIBDIR_VAR} ]] ; then
			CONF_LIBDIR=${!LIBDIR_VAR}
		fi
		if [[ -n ${CONF_LIBDIR} ]] && ! hasgq --libdir=\* "$@" ; then
			export CONF_PREFIX=$(hasg --exec-prefix=\* "$@")
			[[ -z ${CONF_PREFIX} ]] && CONF_PREFIX=$(hasg --prefix=\* "$@")
			: ${CONF_PREFIX:=/usr}
			CONF_PREFIX=${CONF_PREFIX#*=}
			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX="/${CONF_PREFIX}"
			[[ ${CONF_LIBDIR} != /* ]] && CONF_LIBDIR="/${CONF_LIBDIR}"
			set -- --libdir="$(strip_duplicate_slashes ${CONF_PREFIX}${CONF_LIBDIR})" "$@"
		fi

		set -- \
			--prefix=/usr \
			${CBUILD:+--build=${CBUILD}} \
			--host=${CHOST} \
			${CTARGET:+--target=${CTARGET}} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			"$@" \
			${EXTRA_ECONF}
		vecho "${ECONF_SOURCE}/configure" "$@"

		if ! "${ECONF_SOURCE}/configure" "$@" ; then

			if [ -s config.log ]; then
				echo
				echo "!!! Please attach the following file when seeking support:"
				echo "!!! ${PWD}/config.log"
			fi
			die "econf failed"
		fi
	elif [ -f "${ECONF_SOURCE}/configure" ]; then
		die "configure is not executable"
	else
		die "no configure script found"
	fi
}

einstall() {
	# CONF_PREFIX is only set if they didn't pass in libdir above.
	local LOCAL_EXTRA_EINSTALL="${EXTRA_EINSTALL}"
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:-unset}" != "unset" ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(strip_duplicate_slashes ${EI_DESTLIBDIR})"
		LOCAL_EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${LOCAL_EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ "${PORTAGE_DEBUG}" == "1" ]; then
			${MAKE:-make} -n prefix="${D}usr" \
				datadir="${D}usr/share" \
				infodir="${D}usr/share/info" \
				localstatedir="${D}var/lib" \
				mandir="${D}usr/share/man" \
				sysconfdir="${D}etc" \
				${LOCAL_EXTRA_EINSTALL} \
				"$@" install
		fi
		${MAKE:-make} prefix="${D}usr" \
			datadir="${D}usr/share" \
			infodir="${D}usr/share/info" \
			localstatedir="${D}var/lib" \
			mandir="${D}usr/share/man" \
			sysconfdir="${D}etc" \
			${LOCAL_EXTRA_EINSTALL} \
			"$@" install || die "einstall failed"
	else
		die "no Makefile found"
	fi
}

_eapi0_pkg_nofetch() {
	[ -z "${SRC_URI}" ] && return

	echo "!!! The following are listed in SRC_URI for ${PN}:"
	local x
	for x in $(echo ${SRC_URI}); do
		echo "!!!   ${x}"
	done
}

_eapi0_src_unpack() {
	[[ -n ${A} ]] && unpack ${A}
}

_eapi0_src_compile() {
	if [ -x ./configure ] ; then
		econf
	fi
	_eapi2_src_compile
}

_eapi0_src_test() {
	if emake -j1 check -n &> /dev/null; then
		vecho ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! emake -j1 check; then
			hasq test $FEATURES && die "Make check failed. See above for details."
			hasq test $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif emake -j1 test -n &> /dev/null; then
		vecho ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! emake -j1 test; then
			hasq test $FEATURES && die "Make test failed. See above for details."
			hasq test $FEATURES || eerror "Make test failed. See above for details."
		fi
	else
		vecho ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
}

_eapi1_src_compile() {
	_eapi2_src_configure
	_eapi2_src_compile
}

_eapi2_src_configure() {
	if [[ -x ${ECONF_SOURCE:-.}/configure ]] ; then
		econf
	fi
}

_eapi2_src_compile() {
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

ebuild_phase() {
	declare -F "$1" >/dev/null && qa_call $1
}

ebuild_phase_with_hooks() {
	local x phase_name=${1}
	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	for x in {pre_,,post_}${phase_name} ; do
		ebuild_phase ${x}
	done
}

dyn_setup() {
	ebuild_phase_with_hooks pkg_setup
}

dyn_unpack() {
	local newstuff="no"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in ${AA}; do
			vecho ">>> Checking ${x}'s mtime..."
			if [ "${PORTAGE_ACTUAL_DISTDIR:-${DISTDIR}}/${x}" -nt "${WORKDIR}" ]; then
				vecho ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				break
			fi
		done
		if [ ! -f "${PORTAGE_BUILDDIR}/.unpacked" ] ; then
			vecho ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
		fi
	fi
	if [ "${newstuff}" == "yes" ]; then
		# We don't necessarily have privileges to do a full dyn_clean here.
		rm -rf "${PORTAGE_BUILDDIR}"/{.unpacked,.prepared,.configured,.compiled,.tested,.installed,.packaged,build-info}
		rm -rf "${WORKDIR}"
		if [ -d "${T}" ] && \
			! hasq keeptemp $FEATURES && ! hasq keepwork $FEATURES ; then
			rm -rf "${T}" && mkdir "${T}"
		fi
	fi
	if [ -e "${WORKDIR}" ]; then
		if [ "$newstuff" == "no" ]; then
			vecho ">>> WORKDIR is up-to-date, keeping..."
			return 0
		fi
	fi

	if [ ! -d "${WORKDIR}" ]; then
		install -m${PORTAGE_WORKDIR_MODE:-0700} -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	fi
	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	cd "${WORKDIR}" || die "Directory change failed: \`cd '${WORKDIR}'\`"
	ebuild_phase pre_src_unpack
	vecho ">>> Unpacking source..."
	ebuild_phase src_unpack
	touch "${PORTAGE_BUILDDIR}/.unpacked" || die "IO Failure -- Failed 'touch .unpacked' in ${PORTAGE_BUILDDIR}"
	vecho ">>> Source unpacked in ${WORKDIR}"
	ebuild_phase post_src_unpack
}

dyn_clean() {
	if [ -z "${PORTAGE_BUILDDIR}" ]; then
		echo "Aborting clean phase because PORTAGE_BUILDDIR is unset!"
		return 1
	elif [ ! -d "${PORTAGE_BUILDDIR}" ] ; then
		return 0
	fi
	if hasq chflags $FEATURES ; then
		chflags -R noschg,nouchg,nosappnd,nouappnd "${PORTAGE_BUILDDIR}"
		chflags -R nosunlnk,nouunlnk "${PORTAGE_BUILDDIR}" 2>/dev/null
	fi

	rm -rf "${PORTAGE_BUILDDIR}/image" "${PORTAGE_BUILDDIR}/homedir"
	rm -f "${PORTAGE_BUILDDIR}/.installed"

	if [[ $EMERGE_FROM = binary ]] || \
		! hasq keeptemp $FEATURES && ! hasq keepwork $FEATURES ; then
		rm -rf "${T}"
	fi

	if [[ $EMERGE_FROM = binary ]] || ! hasq keepwork $FEATURES; then
		rm -f "$PORTAGE_BUILDDIR"/.{ebuild_changed,exit_status,logid,unpacked,prepared} \
			"$PORTAGE_BUILDDIR"/.{configured,compiled,tested,packaged}

		rm -rf "${PORTAGE_BUILDDIR}/build-info"
		rm -rf "${WORKDIR}"
	fi

	if [ -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
		find "${PORTAGE_BUILDDIR}" -type d ! -regex "^${WORKDIR}" | sort -r | tr "\n" "\0" | $XARGS -0 rmdir &>/dev/null
	fi

	# do not bind this to doebuild defined DISTDIR; don't trust doebuild, and if mistakes are made it'll
	# result in it wiping the users distfiles directory (bad).
	rm -rf "${PORTAGE_BUILDDIR}/distdir"

	# Some kernels, such as Solaris, return EINVAL when an attempt
	# is made to remove the current working directory.
	cd "$PORTAGE_BUILDDIR"/../..
	rmdir "$PORTAGE_BUILDDIR" "${PORTAGE_BUILDDIR%/*}" 2>/dev/null

	true
}

into() {
	if [ "$1" == "/" ]; then
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
		export _E_EXEDESTTREE_=""
	else
		export _E_EXEDESTTREE_="$1"
		if [ ! -d "${D}${_E_EXEDESTTREE_}" ]; then
			install -d "${D}${_E_EXEDESTTREE_}"
		fi
	fi
}

docinto() {
	if [ "$1" == "/" ]; then
		export _E_DOCDESTTREE_=""
	else
		export _E_DOCDESTTREE_="$1"
		if [ ! -d "${D}usr/share/doc/${PF}/${_E_DOCDESTTREE_}" ]; then
			install -d "${D}usr/share/doc/${PF}/${_E_DOCDESTTREE_}"
		fi
	fi
}

insopts() {
	export INSOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${INSOPTIONS} && die "Never call insopts() with -s"
}

diropts() {
	export DIROPTIONS="$@"
}

exeopts() {
	export EXEOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${EXEOPTIONS} && die "Never call exeopts() with -s"
}

libopts() {
	export LIBOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${LIBOPTIONS} && die "Never call libopts() with -s"
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
	trap - SIGINT SIGQUIT
}

abort_prepare() {
	abort_handler src_prepare $1
	rm -f "$PORTAGE_BUILDDIR/.prepared"
	exit 1
}

abort_configure() {
	abort_handler src_configure $1
	rm -f "$PORTAGE_BUILDDIR/.configured"
	exit 1
}

abort_compile() {
	abort_handler "src_compile" $1
	rm -f "${PORTAGE_BUILDDIR}/.compiled"
	exit 1
}

abort_test() {
	abort_handler "dyn_test" $1
	rm -f "${PORTAGE_BUILDDIR}/.tested"
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf "${PORTAGE_BUILDDIR}/image"
	exit 1
}

dyn_prepare() {

	if [[ -e $PORTAGE_BUILDDIR/.prepared ]] ; then
		vecho ">>> It appears that '$PF' is already prepared; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.prepared' to force prepare."
		return 0
	fi

	local srcdir
	if [[ -d $S ]] ; then
		srcdir=$S
	else
		srcdir=$WORKDIR
	fi
	cd "$srcdir"

	trap abort_prepare SIGINT SIGQUIT

	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	ebuild_phase pre_src_prepare
	vecho ">>> Preparing source in $srcdir ..."
	ebuild_phase src_prepare
	touch "$PORTAGE_BUILDDIR"/.prepared
	vecho ">>> Source prepared."
	ebuild_phase post_src_prepare

	trap - SIGINT SIGQUIT
}

dyn_configure() {

	if [[ -e $PORTAGE_BUILDDIR/.configured ]] ; then
		vecho ">>> It appears that '$PF' is already configured; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.configured' to force configuration."
		return 0
	fi

	trap abort_configure SIGINT SIGQUIT

	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	ebuild_phase pre_src_configure

	vecho ">>> Configuring source in $srcdir ..."
	ebuild_phase src_configure
	touch "$PORTAGE_BUILDDIR"/.configured
	vecho ">>> Source configured."

	ebuild_phase post_src_configure

	trap - SIGINT SIGQUIT
}

dyn_compile() {

	if [[ -e $PORTAGE_BUILDDIR/.compiled ]] ; then
		vecho ">>> It appears that '${PF}' is already compiled; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.compiled' to force compilation."
		return 0
	fi

	trap abort_compile SIGINT SIGQUIT

	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	ebuild_phase pre_src_compile

	vecho ">>> Compiling source in ${srcdir} ..."
	ebuild_phase src_compile
	touch "$PORTAGE_BUILDDIR"/.compiled
	vecho ">>> Source compiled."

	ebuild_phase post_src_compile

	trap - SIGINT SIGQUIT
}

dyn_test() {
	if [ "${EBUILD_FORCE_TEST}" == "1" ] ; then
		rm -f "${PORTAGE_BUILDDIR}/.tested"
		# If USE came from ${T}/environment then it might not have USE=test
		# like it's supposed to here.
		! hasq test ${USE} && export USE="${USE} test"
	fi
	if [[ -e $PORTAGE_BUILDDIR/.tested ]] ; then
		vecho ">>> It appears that ${PN} has already been tested; skipping."
		return
	fi
	trap "abort_test" SIGINT SIGQUIT
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "${WORKDIR}"
	fi
	if ! hasq test $FEATURES && [ "${EBUILD_FORCE_TEST}" != "1" ]; then
		vecho ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	elif hasq test $RESTRICT; then
		ewarn "Skipping make test/check due to ebuild restriction."
		vecho ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	else
		local save_sp=${SANDBOX_PREDICT}
		addpredict /
		[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
		ebuild_phase pre_src_test
		ebuild_phase src_test
		touch "$PORTAGE_BUILDDIR/.tested" || \
			die "Failed to 'touch .tested' in $PORTAGE_BUILDDIR"
		ebuild_phase post_src_test
		SANDBOX_PREDICT=${save_sp}
	fi

	trap - SIGINT SIGQUIT
}

dyn_install() {
	[ -z "$PORTAGE_BUILDDIR" ] && die "${FUNCNAME}: PORTAGE_BUILDDIR is unset"
	if hasq noauto $FEATURES ; then
		rm -f "${PORTAGE_BUILDDIR}/.installed"
	elif [[ -e $PORTAGE_BUILDDIR/.installed ]] ; then
		vecho ">>> It appears that '${PF}' is already installed; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.installed' to force install."
		return 0
	fi
	trap "abort_install" SIGINT SIGQUIT
	[ -n "$EBUILD_PHASE" ] && rm -f "$T/logging/$EBUILD_PHASE"
	ebuild_phase pre_src_install
	rm -rf "${PORTAGE_BUILDDIR}/image"
	mkdir "${PORTAGE_BUILDDIR}/image"
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "${WORKDIR}"
	fi
	vecho
	vecho ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"

	# Reset exeinto(), docinto(), insinto(), and into() state variables
	# in case the user is running the install phase multiple times
	# consecutively via the ebuild command.
	export DESTTREE=/usr
	export INSDESTTREE=""
	export _E_EXEDESTTREE_=""
	export _E_DOCDESTTREE_=""

	ebuild_phase src_install
	touch "${PORTAGE_BUILDDIR}/.installed"
	vecho ">>> Completed installing ${PF} into ${D}"
	vecho
	ebuild_phase post_src_install

	cd "${PORTAGE_BUILDDIR}"/build-info
	set -f
	local f x
	IFS=$' \t\n\r'
	for f in ASFLAGS CATEGORY CBUILD CC CFLAGS CHOST CTARGET CXX \
		CXXFLAGS DEFINED_PHASES DEPEND EXTRA_ECONF EXTRA_EINSTALL EXTRA_MAKE \
		FEATURES INHERITED IUSE LDFLAGS LIBCFLAGS LIBCXXFLAGS \
		LICENSE PDEPEND PF PKGUSE PROPERTIES PROVIDE RDEPEND RESTRICT SLOT \
		KEYWORDS HOMEPAGE SRC_URI DESCRIPTION; do
		x=$(echo -n ${!f})
		[[ -n $x ]] && echo "$x" > $f
	done
	echo "${USE}"       > USE
	echo "${EAPI:-0}"   > EAPI
	set +f

	# local variables can leak into the saved environment.
	unset f

	save_ebuild_env --exclude-init-phases | filter_readonly_variables \
		--filter-sandbox --allow-extra-vars > environment

	bzip2 -f9 environment

	cp "${EBUILD}" "${PF}.ebuild"
	[ -n "${PORTAGE_REPO_NAME}" ]  && echo "${PORTAGE_REPO_NAME}" > repository
	if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
	then
		touch DEBUGBUILD
	fi
	trap - SIGINT SIGQUIT
}

dyn_preinst() {
	if [ -z "${D}" ]; then
		eerror "${FUNCNAME}: D is unset"
		return 1
	fi
	ebuild_phase_with_hooks pkg_preinst
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2008 Gentoo Foundation"
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
	echo "  digest      : create a manifest file for the package"
	echo "  manifest    : create a manifest file for the package"
	echo "  unpack      : unpack sources (auto-dependencies if needed)"
	echo "  prepare     : prepare sources (auto-dependencies if needed)"
	echo "  configure   : configure sources (auto-fetch/unpack if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack/configure if needed)"
	echo "  test        : test package (auto-fetch/unpack/configure/compile if needed)"
	echo "  preinst     : execute pre-install instructions"
	echo "  postinst    : execute post-install instructions"
	echo "  install     : install the package to the temporary install directory"
	echo "  qmerge      : merge image into live filesystem, recording files in db"
	echo "  merge       : do fetch, unpack, compile, install and qmerge"
	echo "  prerm       : execute pre-removal instructions"
	echo "  postrm      : execute post-removal instructions"
	echo "  unmerge     : remove package from live filesystem"
	echo "  config      : execute package specific configuration actions"
	echo "  package     : create a tarball package in ${PKGDIR}/All"
	echo "  rpm         : build a RedHat RPM package"
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
	if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT} ;
	then
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
	[ ! -d "$T" ] && return 0

	while [ "$1" ]; do

		# extra user-configurable targets
		if [ "$ECLASS_DEBUG_OUTPUT" == "on" ]; then
			echo "debug: $1" >&2
		elif [ -n "$ECLASS_DEBUG_OUTPUT" ]; then
			echo "debug: $1" >> $ECLASS_DEBUG_OUTPUT
		fi

		# default target
		echo "$1" 2>/dev/null >> "${T}/eclass-debug.log"
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
	if [[ ${ECLASS_DEPTH} > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	if [[ -n $ECLASS && -n ${!__export_funcs_var} ]] ; then
		echo "QA Notice: EXPORT_FUNCTIONS is called before inherit in" \
			"$ECLASS.eclass. For compatibility with <=portage-2.1.6.7," \
			"only call EXPORT_FUNCTIONS after inherit(s)." \
			| fmt -w 75 | while read ; do eqawarn "$REPLY" ; done
	fi

	local location
	local olocation
	local x

	# These variables must be restored before returning.
	local PECLASS=$ECLASS
	local prev_export_funcs_var=$__export_funcs_var

	local B_IUSE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"
		olocation=""

		export ECLASS="$1"
		__export_funcs_var=__export_functions_$ECLASS_DEPTH
		unset $__export_funcs_var

		if [ "${EBUILD_PHASE}" != "depend" ] && \
			[[ ${EBUILD_PHASE} != *rm ]] && \
			[[ ${EMERGE_FROM} != "binary" ]] ; then
			# This is disabled in the *rm phases because they frequently give
			# false alarms due to INHERITED in /var/db/pkg being outdated
			# in comparison the the eclasses from the portage tree.
			if ! hasq $ECLASS $INHERITED; then
				eqawarn "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF $EBUILD_PHASE"
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
		[ ! -e "$location" ] && die "${1}.eclass could not be found by inherit()"

		if [ "${location}" == "${olocation}" ] && \
			! hasq "${location}" ${EBUILD_OVERLAY_ECLASSES} ; then
				EBUILD_OVERLAY_ECLASSES="${EBUILD_OVERLAY_ECLASSES} ${location}"
		fi

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.

		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_IUSE B_DEPEND B_RDEPEND B_PDEPEND
		[ "${IUSE-unset}"    != "unset" ] && B_IUSE="${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset IUSE DEPEND RDEPEND PDEPEND
		#turn on glob expansion
		set +f

		qa_source "$location" || die "died sourcing $location in inherit()"
		
		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${IUSE-unset}"    != "unset" ] && export E_IUSE="${E_IUSE} ${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_IUSE-unset}"    != "unset" ] && IUSE="${B_IUSE}"
		[ "${B_IUSE-unset}"    != "unset" ] || unset IUSE

		[ "${B_DEPEND-unset}"  != "unset" ] && DEPEND="${B_DEPEND}"
		[ "${B_DEPEND-unset}"  != "unset" ] || unset DEPEND

		[ "${B_RDEPEND-unset}" != "unset" ] && RDEPEND="${B_RDEPEND}"
		[ "${B_RDEPEND-unset}" != "unset" ] || unset RDEPEND

		[ "${B_PDEPEND-unset}" != "unset" ] && PDEPEND="${B_PDEPEND}"
		[ "${B_PDEPEND-unset}" != "unset" ] || unset PDEPEND

		#turn on glob expansion
		set +f

		if [[ -n ${!__export_funcs_var} ]] ; then
			for x in ${!__export_funcs_var} ; do
				debug-print "EXPORT_FUNCTIONS: $x -> ${ECLASS}_$x"
				declare -F "${ECLASS}_$x" >/dev/null || \
					die "EXPORT_FUNCTIONS: ${ECLASS}_$x is not defined"
				eval "$x() { ${ECLASS}_$x \"\$@\" ; }" > /dev/null
			done
		fi
		unset $__export_funcs_var

		hasq $1 $INHERITED || export INHERITED="$INHERITED $1"

		shift
	done
	((--ECLASS_DEPTH)) # Returns 1 when ECLASS_DEPTH reaches 0.
	if (( ECLASS_DEPTH > 0 )) ; then
		export ECLASS=$PECLASS
		__export_funcs_var=$prev_export_funcs_var
	else
		unset ECLASS __export_funcs_var
	fi
	return 0
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -z "$ECLASS" ]; then
		die "EXPORT_FUNCTIONS without a defined ECLASS"
	fi
	eval $__export_funcs_var+=\" $*\"
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

# @FUNCTION: _ebuild_arg_to_phase
# @DESCRIPTION:
# Translate a known ebuild(1) argument into the precise
# name of it's corresponding ebuild phase.
_ebuild_arg_to_phase() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local arg=$2
	local phase_func=""

	case "$arg" in
		setup)
			phase_func=pkg_setup
			;;
		nofetch)
			phase_func=pkg_nofetch
			;;
		unpack)
			phase_func=src_unpack
			;;
		prepare)
			! hasq $eapi 0 1 && \
				phase_func=src_prepare
			;;
		configure)
			! hasq $eapi 0 1 && \
				phase_func=src_configure
			;;
		compile)
			phase_func=src_compile
			;;
		test)
			phase_func=src_test
			;;
		install)
			phase_func=src_install
			;;
		preinst)
			phase_func=pkg_preinst
			;;
		postinst)
			phase_func=pkg_postinst
			;;
		prerm)
			phase_func=pkg_prerm
			;;
		postrm)
			phase_func=pkg_postrm
			;;
	esac

	[[ -z $phase_func ]] && return 1
	echo "$phase_func"
	return 0
}

_ebuild_phase_funcs() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local phase_func=$2
	local default_phases="pkg_nofetch src_unpack src_prepare src_configure
		src_compile src_install src_test"
	local x y default_func=""

	for x in pkg_nofetch src_unpack src_test ; do
		declare -F $x >/dev/null || \
			eval "$x() { _eapi0_$x \"\$@\" ; }"
	done

	case $eapi in

		0|1)

			if ! declare -F src_compile >/dev/null ; then
				case $eapi in
					0)
						src_compile() { _eapi0_src_compile "$@" ; }
						;;
					*)
						src_compile() { _eapi1_src_compile "$@" ; }
						;;
				esac
			fi

			for x in $default_phases ; do
				eval "default_$x() {
					die \"default_$x() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"
			done

			eval "default() {
				die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
			}"

			;;

		*)

			declare -F src_configure >/dev/null || \
				src_configure() { _eapi2_src_configure "$@" ; }

			declare -F src_compile >/dev/null || \
				src_compile() { _eapi2_src_compile "$@" ; }

			if hasq $phase_func $default_phases ; then

				_eapi2_pkg_nofetch   () { _eapi0_pkg_nofetch          "$@" ; }
				_eapi2_src_unpack    () { _eapi0_src_unpack           "$@" ; }
				_eapi2_src_prepare   () { true                             ; }
				_eapi2_src_test      () { _eapi0_src_test             "$@" ; }
				_eapi2_src_install   () { die "$FUNCNAME is not supported" ; }

				for x in $default_phases ; do
					eval "default_$x() { _eapi2_$x \"\$@\" ; }"
				done

				eval "default() { _eapi2_$phase_func \"\$@\" ; }"

			else

				for x in $default_phases ; do
					eval "default_$x() {
						die \"default_$x() is not supported in phase $default_func\"
					}"
				done

				eval "default() {
					die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"

			fi

			;;
	esac
}

PORTAGE_BASHRCS_SOURCED=0

# @FUNCTION: source_all_bashrcs
# @DESCRIPTION:
# Source a relevant bashrc files and perform other miscellaneous
# environment initialization when appropriate.
#
# If EAPI is set then define functions provided by the current EAPI:
#
#  * default_* aliases for the current EAPI phase functions
#  * A "default" function which is an alias for the default phase
#    function for the current phase.
#
source_all_bashrcs() {
	[[ $PORTAGE_BASHRCS_SOURCED = 1 ]] && return 0
	PORTAGE_BASHRCS_SOURCED=1
	local x

	local OCC="${CC}" OCXX="${CXX}"

	if [[ $EBUILD_PHASE != depend ]] ; then
		# source the existing profile.bashrcs.
		save_IFS
		IFS=$'\n'
		local path_array=($PROFILE_PATHS)
		restore_IFS
		for x in "${path_array[@]}" ; do
			[ -f "$x/profile.bashrc" ] && qa_source "$x/profile.bashrc"
		done
	fi

	# We assume if people are changing shopts in their bashrc they do so at their
	# own peril.  This is the ONLY non-portage bit of code that can change shopts
	# without a QA violation.
	if [ -f "${PORTAGE_BASHRC}" ]; then
		# If $- contains x, then tracing has already enabled elsewhere for some
		# reason.  We preserve it's state so as not to interfere.
		if [ "$PORTAGE_DEBUG" != "1" ] || [ "${-/x/}" != "$-" ]; then
			source "${PORTAGE_BASHRC}"
		else
			set -x
			source "${PORTAGE_BASHRC}"
			set +x
		fi
	fi
	[ ! -z "${OCC}" ] && export CC="${OCC}"
	[ ! -z "${OCXX}" ] && export CXX="${OCXX}"
}

# Hardcoded bash lists are needed for backward compatibility with
# <portage-2.1.4 since they assume that a newly installed version
# of ebuild.sh will work for pkg_postinst, pkg_prerm, and pkg_postrm
# when portage is upgrading itself.

READONLY_EBUILD_METADATA="DEFINED_PHASES DEPEND DESCRIPTION
	EAPI HOMEPAGE INHERITED IUSE KEYWORDS LICENSE
	PDEPEND PROVIDE RDEPEND RESTRICT SLOT SRC_URI"

READONLY_PORTAGE_VARS="D EBUILD EBUILD_PHASE \
	EBUILD_SH_ARGS EMERGE_FROM FILESDIR PORTAGE_BINPKG_FILE \
	PORTAGE_BIN_PATH PORTAGE_IUSE \
	PORTAGE_PYM_PATH PORTAGE_MUTABLE_FILTERED_VARS \
	PORTAGE_SAVED_READONLY_VARS PORTAGE_TMPDIR T WORKDIR"

PORTAGE_SAVED_READONLY_VARS="A CATEGORY P PF PN PR PV PVR"

# Variables that portage sets but doesn't mark readonly.
# In order to prevent changed values from causing unexpected
# interference, they are filtered out of the environment when
# it is saved or loaded (any mutations do not persist).
PORTAGE_MUTABLE_FILTERED_VARS="AA HOSTNAME"

# @FUNCTION: filter_readonly_variables
# @DESCRIPTION: [--filter-sandbox] [--allow-extra-vars]
# Read an environment from stdin and echo to stdout while filtering variables
# with names that are known to cause interference:
#
#   * some specific variables for which bash does not allow assignment
#   * some specific variables that affect portage or sandbox behavior
#   * variable names that begin with a digit or that contain any
#     non-alphanumeric characters that are not be supported by bash
#
# --filter-sandbox causes all SANDBOX_* variables to be filtered, which
# is only desired in certain cases, such as during preprocessing or when
# saving environment.bz2 for a binary or installed package.
#
# --filter-features causes the special FEATURES variable to be filtered.
# Generally, we want it to persist between phases since the user might
# want to modify it via bashrc to enable things like splitdebug and
# installsources for specific packages. They should be able to modify it
# in pre_pkg_setup() and have it persist all the way through the install
# phase. However, if FEATURES exist inside environment.bz2 then they
# should be overridden by current settings.
#
# ---allow-extra-vars causes some extra vars to be allowd through, such
# as ${PORTAGE_SAVED_READONLY_VARS} and ${PORTAGE_MUTABLE_FILTERED_VARS}.
#
# In bash-3.2_p20+ an attempt to assign BASH_*, FUNCNAME, GROUPS or any
# readonly variable cause the shell to exit while executing the "source"
# builtin command. To avoid this problem, this function filters those
# variables out and discards them. See bug #190128.
filter_readonly_variables() {
	local x filtered_vars
	local readonly_bash_vars="DIRSTACK EUID FUNCNAME GROUPS
		PIPESTATUS PPID SHELLOPTS UID"
	local filtered_sandbox_vars="SANDBOX_ACTIVE SANDBOX_BASHRC
		SANDBOX_DEBUG_LOG SANDBOX_DISABLED SANDBOX_LIB
		SANDBOX_LOG SANDBOX_ON"
	filtered_vars="${readonly_bash_vars} ${READONLY_PORTAGE_VARS}
		BASH_.* HISTFILE PATH POSIXLY_CORRECT"
	if hasq --filter-sandbox $* ; then
		filtered_vars="${filtered_vars} SANDBOX_.*"
	else
		filtered_vars="${filtered_vars} ${filtered_sandbox_vars}"
	fi
	if hasq --filter-features $* ; then
		filtered_vars="${filtered_vars} FEATURES"
	fi
	if ! hasq --allow-extra-vars $* ; then
		filtered_vars="
			${filtered_vars}
			${PORTAGE_SAVED_READONLY_VARS}
			${PORTAGE_MUTABLE_FILTERED_VARS}
		"
	fi

	"${PORTAGE_BIN_PATH}"/filter-bash-environment.py "${filtered_vars}"
}

# @FUNCTION: preprocess_ebuild_env
# @DESCRIPTION:
# Filter any readonly variables from ${T}/environment, source it, and then
# save it via save_ebuild_env(). This process should be sufficient to prevent
# any stale variables or functions from an arbitrary environment from
# interfering with the current environment. This is useful when an existing
# environment needs to be loaded from a binary or installed package.
preprocess_ebuild_env() {
	local filter_opts=""
	if [ -f "${T}/environment.raw" ] ; then
		# This is a signal from the python side, indicating that the
		# environment may contain stale SANDBOX_{DENY,PREDICT,READ,WRITE}
		# and FEATURES variables that should be filtered out. Between
		# phases, these variables are normally preserved.
		filter_opts="--filter-sandbox --filter-features ${filter_opts}"
	fi
	filter_readonly_variables ${filter_opts} < "${T}"/environment \
		> "${T}"/environment.filtered || return $?
	unset filter_opts
	mv "${T}"/environment.filtered "${T}"/environment || return $?
	rm -f "${T}/environment.success" || return $?
	# WARNING: Code inside this subshell should avoid making assumptions
	# about variables or functions after source "${T}"/environment has been
	# called. Any variables that need to be relied upon should already be
	# filtered out above.
	(
		export SANDBOX_ON=1
		source "${T}/environment" || exit $?
		# We have to temporarily disable sandbox since the
		# SANDBOX_{DENY,READ,PREDICT,WRITE} values we've just loaded
		# may be unusable (triggering in spurious sandbox violations)
		# until we've merged them with our current values.
		export SANDBOX_ON=0

		# It's remotely possible that save_ebuild_env() has been overridden
		# by the above source command. To protect ourselves, we override it
		# here with our own version. ${PORTAGE_BIN_PATH} is safe to use here
		# because it's already filtered above.
		source "${PORTAGE_BIN_PATH}/isolated-functions.sh" || exit $?

		# Rely on save_ebuild_env() to filter out any remaining variables
		# and functions that could interfere with the current environment.
		save_ebuild_env || exit $?
		touch "${T}/environment.success" || exit $?
	) > "${T}/environment.filtered"
	local retval
	if [ -e "${T}/environment.success" ] ; then
		filter_readonly_variables < \
			"${T}/environment.filtered" > "${T}/environment"
		retval=$?
	else
		retval=1
	fi
	rm -f "${T}"/environment.{filtered,raw,success}
	return ${retval}
}

# === === === === === === === === === === === === === === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === === === === === === === === === === === === === ===

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND

# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
shopt -u extglob

if [[ ${EBUILD_PHASE} == depend ]] ; then
	QA_INTERCEPTORS="awk bash cc egrep fgrep g++
		gawk gcc grep javac java-config nawk perl
		pkg-config python python-config sed"
elif [[ ${EBUILD_PHASE} == clean* ]] ; then
	unset QA_INTERCEPTORS
else
	QA_INTERCEPTORS="autoconf automake aclocal libtoolize"
fi
# level the QA interceptors if we're in depend
if [[ -n ${QA_INTERCEPTORS} ]] ; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -Pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		if [[ ${EBUILD_PHASE} == depend ]] ; then
			FUNC_SRC="${BIN}() {
				if [ \$ECLASS_DEPTH -gt 0 ]; then
					eqawarn \"QA Notice: '${BIN}' called in global scope: eclass \${ECLASS}\"
				else
					eqawarn \"QA Notice: '${BIN}' called in global scope: \${CATEGORY}/\${PF}\"
				fi
			${BODY}
			}"
		elif hasq ${BIN} autoconf automake aclocal libtoolize ; then
			FUNC_SRC="${BIN}() {
				if ! hasq \${FUNCNAME[1]} eautoreconf eaclocal _elibtoolize \\
					eautoheader eautoconf eautomake autotools_run_tool \\
					autotools_check_macro autotools_get_subdirs \\
					autotools_get_auxdir ; then
					eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
					eqawarn \"Use autotools.eclass instead of calling '${BIN}' directly.\"
				fi
			${BODY}
			}"
		else
			FUNC_SRC="${BIN}() {
				eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
			${BODY}
			}"
		fi
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset BIN_PATH BIN BODY FUNC_SRC
fi

if ! hasq "$EBUILD_PHASE" clean cleanrm depend && \
	[ -f "${T}"/environment ] ; then
	# The environment may have been extracted from environment.bz2 or
	# may have come from another version of ebuild.sh or something.
	# In any case, preprocess it to prevent any potential interference.
	preprocess_ebuild_env || \
		die "error processing environment"
	# Colon separated SANDBOX_* variables need to be cumulative.
	for x in SANDBOX_DENY SANDBOX_READ SANDBOX_PREDICT SANDBOX_WRITE ; do
		export PORTAGE_${x}=${!x}
	done
	PORTAGE_SANDBOX_ON=${SANDBOX_ON}
	export SANDBOX_ON=1
	source "${T}"/environment || \
		die "error sourcing environment"
	# We have to temporarily disable sandbox since the
	# SANDBOX_{DENY,READ,PREDICT,WRITE} values we've just loaded
	# may be unusable (triggering in spurious sandbox violations)
	# until we've merged them with our current values.
	export SANDBOX_ON=0
	for x in SANDBOX_DENY SANDBOX_PREDICT SANDBOX_READ SANDBOX_WRITE ; do
		y="PORTAGE_${x}"
		if [ -z "${!x}" ] ; then
			export ${x}=${!y}
		elif [ -n "${!y}" ] && [ "${!y}" != "${!x}" ] ; then
			# filter out dupes
			export ${x}=$(printf "${!y}:${!x}" | tr ":" "\0" | \
				sort -z -u | tr "\0" ":")
		fi
		export ${x}=${!x%:}
		unset PORTAGE_${x}
	done
	unset x y
	export SANDBOX_ON=${PORTAGE_SANDBOX_ON}
	unset PORTAGE_SANDBOX_ON
	[[ -n $EAPI ]] || EAPI=0
fi

_source_ebuild() {
	# The bashrcs get an opportunity here to set aliases that will be expanded
	# during sourcing of ebuilds and eclasses.
	source_all_bashrcs

	# *DEPEND and IUSE will be set during the sourcing of the ebuild.
	# In order to ensure correct interaction between ebuilds and
	# eclasses, they need to be unset before this process of
	# interaction begins.
	unset DEPEND RDEPEND PDEPEND IUSE
	source "${EBUILD}" || die "error sourcing ebuild"

	if [ "${EBUILD_PHASE}" != "depend" ] ; then
		RESTRICT=${PORTAGE_RESTRICT}
		[[ -e $PORTAGE_BUILDDIR/.ebuild_changed ]] && \
			rm "$PORTAGE_BUILDDIR/.ebuild_changed"
	fi

	# This next line is not the same as export RDEPEND=${RDEPEND:-${DEPEND}}
	# That will test for unset *or* NULL (""). We want just to set for unset...
	# turn off glob expansion from here on in to prevent *'s and ? in the
	# DEPEND syntax from getting expanded :)
	set -f
	if [ "${RDEPEND-unset}" == "unset" ] ; then
		export RDEPEND=${DEPEND}
		debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
	fi

	# add in dependency info from eclasses
	IUSE="${IUSE} ${E_IUSE}"
	DEPEND="${DEPEND} ${E_DEPEND}"
	RDEPEND="${RDEPEND} ${E_RDEPEND}"
	PDEPEND="${PDEPEND} ${E_PDEPEND}"

	unset ECLASS E_IUSE E_DEPEND E_RDEPEND E_PDEPEND
	set +f

	[[ -n $EAPI ]] || EAPI=0

	# alphabetically ordered by $EBUILD_PHASE value
	local f valid_phases
	case "$EAPI" in
		0|1)
			valid_phases="src_compile pkg_config pkg_info src_install
				pkg_nofetch pkg_postinst pkg_postrm pkg_preinst pkg_prerm
				pkg_setup src_test src_unpack"
			;;
		*)
			valid_phases="src_compile pkg_config src_configure pkg_info
				src_install pkg_nofetch pkg_postinst pkg_postrm pkg_preinst
				src_prepare pkg_prerm pkg_setup src_test src_unpack"
			;;
	esac

	DEFINED_PHASES=
	for f in $valid_phases ; do
		if declare -F $f >/dev/null ; then
			f=${f#pkg_}
			DEFINED_PHASES+=" ${f#src_}"
		fi
	done
	[[ -n $DEFINED_PHASES ]] || DEFINED_PHASES=-

	# This needs to be exported since prepstrip is a separate shell script.
	[[ -n $QA_PRESTRIPPED ]] && export QA_PRESTRIPPED
}

if ! hasq "$EBUILD_PHASE" clean cleanrm ; then
	if [[ $EBUILD_PHASE = depend || ! -f $T/environment || \
		-f $PORTAGE_BUILDDIR/.ebuild_changed ]] || \
		hasq noauto $FEATURES ; then
		_source_ebuild
	fi
fi

# unset USE_EXPAND variables that contain only the special "*" token
for x in ${USE_EXPAND} ; do
	[ "${!x}" == "*" ] && unset ${x}
done
unset x

if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
then
	export DEBUGBUILD=1
fi

#a reasonable default for $S
[[ -z ${S} ]] && export S=${WORKDIR}/${P}

#some users have $TMP/$TMPDIR to a custom dir in their home ...
#this will cause sandbox errors with some ./configure
#scripts, so set it to $T.
export TMP="${T}"
export TMPDIR="${T}"

# Note: readonly variables interfere with preprocess_ebuild_env(), so
# declare them only after it has already run.
if [ "${EBUILD_PHASE}" != "depend" ] ; then
	declare -r ${READONLY_EBUILD_METADATA} ${READONLY_PORTAGE_VARS}
fi

ebuild_main() {
	local f x

	# we may want to make this configurable somewhere else
	local ebuild_helpers_path
	case ${EAPI} in
		3|3_pre1)
			ebuild_helpers_path="${PORTAGE_BIN_PATH}/ebuild-helpers/3:${PORTAGE_BIN_PATH}/ebuild-helpers"
			;;
		*)
			ebuild_helpers_path="${PORTAGE_BIN_PATH}/ebuild-helpers"
			;;
	esac

	PATH=$ebuild_helpers_path:$PREROOTPATH${PREROOTPATH:+:}/usr/local/sbin:/sbin:/usr/sbin:/usr/local/bin:/bin:/usr/bin${ROOTPATH:+:}$ROOTPATH
	unset ebuild_helpers_path

	if ! hasq $EBUILD_SH_ARGS clean depend help info nofetch ; then

		if hasq distcc $FEATURES ; then
			export PATH="/usr/lib/distcc/bin:$PATH"
			[[ -n $DISTCC_LOG ]] && addwrite "${DISTCC_LOG%/*}"
		fi

		if hasq ccache $FEATURES ; then
			export PATH="/usr/lib/ccache/bin:$PATH"

			addread "$CCACHE_DIR"
			addwrite "$CCACHE_DIR"

			[[ -n $CCACHE_SIZE ]] && ccache -M $CCACHE_SIZE &> /dev/null
		else
			# Force configure scripts that automatically detect ccache to
			# respect FEATURES="-ccache".
			export CCACHE_DISABLE=1
		fi
	fi

	if [[ $EBUILD_PHASE != depend ]] ; then
		local phase_func=$(_ebuild_arg_to_phase "$EAPI" "$EBUILD_PHASE")
		[[ -n $phase_func ]] && _ebuild_phase_funcs "$EAPI" "$phase_func"
		unset phase_func
	fi

	source_all_bashrcs

	case ${EBUILD_SH_ARGS} in
	nofetch)
		ebuild_phase_with_hooks pkg_nofetch
		exit 1
		;;
	prerm|postrm|postinst|config|info)
		if hasq "$EBUILD_SH_ARGS" config info && \
			! declare -F "pkg_$EBUILD_SH_ARGS" >/dev/null ; then
			ewarn  "pkg_${EBUILD_SH_ARGS}() is not defined: '${EBUILD##*/}'"
		fi
		export SANDBOX_ON="0"
		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			ebuild_phase_with_hooks pkg_${EBUILD_SH_ARGS}
		else
			set -x
			ebuild_phase_with_hooks pkg_${EBUILD_SH_ARGS}
			set +x
		fi
		if [[ $EBUILD_PHASE == postinst ]] && [[ -n $PORTAGE_UPDATE_ENV ]]; then
			# Update environment.bz2 in case installation phases
			# need to pass some variables to uninstallation phases.
			save_ebuild_env --exclude-init-phases | \
				filter_readonly_variables --filter-sandbox --allow-extra-vars \
				| bzip2 -c -f9 > "$PORTAGE_UPDATE_ENV"
		fi
		;;
	unpack|prepare|configure|compile|test|clean|install)
		if [[ ${SANDBOX_DISABLED:-0} = 0 ]] ; then
			export SANDBOX_ON="1"
		else
			export SANDBOX_ON="0"
		fi

		case "$EBUILD_SH_ARGS" in
		configure|compile)

			for x in ASFLAGS CCACHE_DIR CCACHE_SIZE \
				CFLAGS CXXFLAGS LDFLAGS LIBCFLAGS LIBCXXFLAGS ; do
				[[ ${!x-unset} != unset ]] && export $x
			done

			hasq distcc $FEATURES && [[ -n $DISTCC_DIR ]] && \
				[[ ${SANDBOX_WRITE/$DISTCC_DIR} = $SANDBOX_WRITE ]] && \
				addwrite "$DISTCC_DIR"

			x=LIBDIR_$ABI
			[ -z "$PKG_CONFIG_PATH" -a -n "$ABI" -a -n "${!x}" ] && \
				export PKG_CONFIG_PATH=/usr/${!x}/pkgconfig

			if hasq noauto $FEATURES && \
				[[ ! -f $PORTAGE_BUILDDIR/.unpacked ]] ; then
				echo
				echo "!!! We apparently haven't unpacked..." \
					"This is probably not what you"
				echo "!!! want to be doing... You are using" \
					"FEATURES=noauto so I'll assume"
				echo "!!! that you know what you are doing..." \
					"You have 5 seconds to abort..."
				echo

				local x
				for x in 1 2 3 4 5 6 7 8; do
					echo -ne "\a"
					LC_ALL=C sleep 0.25
				done

				sleep 3
			fi

			cd "$PORTAGE_BUILDDIR"
			if [ ! -d build-info ] ; then
				mkdir build-info
				cp "$EBUILD" "build-info/$PF.ebuild"
			fi

			local srcdir
			if [[ -d $S ]] ; then
				srcdir=$S
			else
				srcdir=$WORKDIR
			fi
			cd "$srcdir"
			#our custom version of libtool uses $S and $D to fix
			#invalid paths in .la files
			export S D
			#some packages use an alternative to $S to build in, cause
			#our libtool to create problematic .la files
			export PWORKDIR=$WORKDIR

			;;
		esac

		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			dyn_${EBUILD_SH_ARGS}
		else
			set -x
			dyn_${EBUILD_SH_ARGS}
			set +x
		fi
		export SANDBOX_ON="0"
		;;
	help|setup|preinst)
		#pkg_setup needs to be out of the sandbox for tmp file creation;
		#for example, awking and piping a file in /tmp requires a temp file to be created
		#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.
		export SANDBOX_ON="0"
		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			dyn_${EBUILD_SH_ARGS}
		else
			set -x
			dyn_${EBUILD_SH_ARGS}
			set +x
		fi
		;;
	depend)
		export SANDBOX_ON="0"
		set -f

		if [ -n "${dbkey}" ] ; then
			if [ ! -d "${dbkey%/*}" ]; then
				install -d -g ${PORTAGE_GID} -m2775 "${dbkey%/*}"
			fi
			# Make it group writable. 666&~002==664
			umask 002
		fi

		auxdbkeys="DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE
			DESCRIPTION KEYWORDS INHERITED IUSE CDEPEND PDEPEND PROVIDE EAPI
			PROPERTIES DEFINED_PHASES UNUSED_05 UNUSED_04
			UNUSED_03 UNUSED_02 UNUSED_01"

		#the extra $(echo) commands remove newlines
		unset CDEPEND
		[ -n "${EAPI}" ] || EAPI=0
		local eapi=$EAPI

		if [ -n "${dbkey}" ] ; then
			> "${dbkey}"
			for f in ${auxdbkeys} ; do
				echo $(echo ${!f}) >> "${dbkey}" || exit $?
			done
		else
			for f in ${auxdbkeys} ; do
				echo $(echo ${!f}) 1>&9 || exit $?
			done
			exec 9>&-
		fi
		set +f
		;;
	*)
		export SANDBOX_ON="1"
		echo "Unrecognized EBUILD_SH_ARGS: '${EBUILD_SH_ARGS}'"
		echo
		dyn_help
		exit 1
		;;
	esac
	if [ -n "$EBUILD_EXIT_STATUS_FILE" ] ; then
		> "$EBUILD_EXIT_STATUS_FILE" || \
			die "failed to create '$EBUILD_EXIT_STATUS_FILE'"
	fi
}

if [[ $EBUILD_PHASE = depend ]] ; then
	ebuild_main
elif [[ -n $EBUILD_SH_ARGS ]] ; then
	(
		# Don't allow subprocesses to inherit the pipe which
		# emerge uses to monitor ebuild.sh.
		exec 9>&-

		ebuild_main

		# Save the env only for relevant phases.
		if ! hasq "$EBUILD_SH_ARGS" clean help info nofetch ; then
			umask 002
			save_ebuild_env | filter_readonly_variables > "$T/environment"
			chown portage:portage "$T/environment" &>/dev/null
			chmod g+w "$T/environment" &>/dev/null
		fi
		exit 0
	)
	exit $?
fi

# Do not exit when ebuild.sh is sourced by other scripts.
true
