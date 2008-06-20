# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || die'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && old_IFS="${IFS}"'
alias restore_IFS='if [ "${old_IFS:-unset}" != "unset" ]; then IFS="${old_IFS}"; unset old_IFS; else unset IFS; fi'

shopt -s extdebug

# dump_trace([number of funcs on stack to skip],
#            [whitespacing for filenames],
#            [whitespacing for line numbers])
dump_trace() {
	local funcname="" sourcefile="" lineno="" s="yes" n p
	declare -i strip=${1:-1}
	local filespacing=$2 linespacing=$3

	# The qa_call() function and anything before it are portage internals
	# that the user will not be interested in. Therefore, the stack trace
	# should only show calls that come after qa_call().
	(( n = ${#FUNCNAME[@]} - 1 ))
	(( p = ${#BASH_ARGV[@]} ))
	while (( n > 0 )) ; do
		[ "${FUNCNAME[${n}]}" == "qa_call" ] && break
		(( p -= ${BASH_ARGC[${n}]} ))
		(( n-- ))
	done
	if (( n == 0 )) ; then
		(( n = ${#FUNCNAME[@]} - 1 ))
		(( p = ${#BASH_ARGV[@]} ))
	fi

	eerror "Call stack:"
	while (( n > ${strip} )) ; do
		funcname=${FUNCNAME[${n} - 1]}
		sourcefile=$(basename ${BASH_SOURCE[${n}]})
		lineno=${BASH_LINENO[${n} - 1]}
		# Display function arguments
		args=
		if [[ -n "${BASH_ARGV[@]}" ]]; then
			for (( j = 1 ; j <= ${BASH_ARGC[${n} - 1]} ; ++j )); do
				newarg=${BASH_ARGV[$(( p - j - 1 ))]}
				args="${args:+${args} }'${newarg}'"
			done
			(( p -= ${BASH_ARGC[${n} - 1]} ))
		fi
		eerror "  $(printf "%${filespacing}s" "${sourcefile}"), line $(printf "%${linespacing}s" "${lineno}"):  Called ${funcname}${args:+ ${args}}"
		(( n-- ))
	done
}

die() {
	if [ -n "${QA_INTERCEPTORS}" ] ; then
		# die was called from inside inherit. We need to clean up
		# QA_INTERCEPTORS since sed is called below.
		unset -f ${QA_INTERCEPTORS}
		unset QA_INTERCEPTORS
	fi
	local n filespacing=0 linespacing=0
	# setup spacing to make output easier to read
	for ((n = ${#FUNCNAME[@]} - 1; n >= 0; --n)); do
		sourcefile=${BASH_SOURCE[${n}]} sourcefile=${sourcefile##*/}
		lineno=${BASH_LINENO[${n}]}
		((filespacing < ${#sourcefile})) && filespacing=${#sourcefile}
		((linespacing < ${#lineno}))     && linespacing=${#lineno}
	done

	eerror
	eerror "ERROR: $CATEGORY/$PF failed."
	dump_trace 2 ${filespacing} ${linespacing}
	eerror "  $(printf "%${filespacing}s" "${BASH_SOURCE[1]##*/}"), line $(printf "%${linespacing}s" "${BASH_LINENO[0]}"):  Called die"
	eerror "The specific snippet of code:"
	# This scans the file that called die and prints out the logic that
	# ended in the call to die.  This really only handles lines that end
	# with '|| die' and any preceding lines with line continuations (\).
	# This tends to be the most common usage though, so let's do it.
	# Due to the usage of appending to the hold space (even when empty),
	# we always end up with the first line being a blank (thus the 2nd sed).
	sed -n \
		-e "# When we get to the line that failed, append it to the
		    # hold space, move the hold space to the pattern space,
		    # then print out the pattern space and quit immediately
		    ${BASH_LINENO[0]}{H;g;p;q}" \
		-e '# If this line ends with a line continuation, append it
		    # to the hold space
		    /\\$/H' \
		-e '# If this line does not end with a line continuation,
		    # erase the line and set the hold buffer to it (thus
		    # erasing the hold buffer in the process)
		    /[^\]$/{s:^.*$::;h}' \
		${BASH_SOURCE[1]} \
		| sed -e '1d' -e 's:^:RETAIN-LEADING-SPACE:' \
		| while read -r n ; do eerror "  ${n#RETAIN-LEADING-SPACE}" ; done
	eerror " The die message:"
	eerror "  ${*:-(no error message)}"
	eerror
	eerror "If you need support, post the topmost build error, and the call stack if relevant."
	[[ -n ${PORTAGE_LOG_FILE} ]] \
		&& eerror "A complete build log is located at '${PORTAGE_LOG_FILE}'."
	if [ -f "${T}/environment" ] ; then
		eerror "The ebuild environment file is located at '${T}/environment'."
	elif [ -d "${T}" ] ; then
		{
			set
			export
		} > "${T}/die.env"
		eerror "The ebuild environment file is located at '${T}/die.env'."
	fi
	if [[ -n ${EBUILD_OVERLAY_ECLASSES} ]] ; then
		eerror "This ebuild used the following eclasses from overlays:"
		local x
		for x in ${EBUILD_OVERLAY_ECLASSES} ; do
			eerror "  ${x}"
		done
	fi
	if [ "${EMERGE_FROM}" != "binary" ] && \
		! hasq ${EBUILD_PHASE} prerm postrm && \
		[ "${EBUILD#${PORTDIR}/}" == "${EBUILD}" ] ; then
		local overlay=${EBUILD%/*}
		overlay=${overlay%/*}
		overlay=${overlay%/*}
		eerror "This ebuild is from an overlay: '${overlay}/'"
	fi
	eerror

	if [[ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]] ; then
		local x
		for x in $EBUILD_DEATH_HOOKS; do
			${x} "$@" >&2 1>&2
		done
	fi

	[ -n "${EBUILD_EXIT_STATUS_FILE}" ] && \
		touch "${EBUILD_EXIT_STATUS_FILE}" &>/dev/null

	# subshell die support
	kill -s SIGTERM ${EBUILD_MASTER_PID}
	exit 1
}

# We need to implement diefunc() since environment.bz2 files contain
# calls to it (due to alias expansion).
diefunc() {
	die "${@}"
}

quiet_mode() {
	[[ ${PORTAGE_QUIET} -eq 1 ]]
}

vecho() {
	quiet_mode || echo "$@"
}

# Internal logging function, don't use this in ebuilds
elog_base() {
	local messagetype
	[ -z "${1}" -o -z "${T}" -o ! -d "${T}/logging" ] && return 1
	case "${1}" in
		BLANK|INFO|WARN|ERROR|LOG|QA)
			messagetype="${1}"
			shift
			;;
		*)
			vecho -e " ${BAD}*${NORMAL} Invalid use of internal function elog_base(), next message will not be logged"
			return 1
			;;
	esac
	echo -ne "${messagetype} $*\n\0" >> "${T}/logging/${EBUILD_PHASE:-other}"
	return 0
}

eblank() {
	[[ ${LAST_E_CMD} == "eblank" ]] && return 0
	elog_base BLANK
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${BLANK}*${NORMAL}"
	LAST_E_CMD="eblank"
	return 0
}

eqawarn() {
	elog_base QA "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	vecho -e " ${WARN}*${NORMAL} $*" >&2
	LAST_E_CMD="eqawarn"
	return 0
}

elog() {
	elog_base LOG "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${GOOD}*${NORMAL} $*"
	LAST_E_CMD="elog"
	return 0
}

esyslog() {
	local pri=
	local tag=

	if [ -x /usr/bin/logger ]
	then
		pri="$1"
		tag="$2"

		shift 2
		[ -z "$*" ] && return 0

		/usr/bin/logger -p "${pri}" -t "${tag}" -- "$*"
	fi

	return 0
}

einfo() {
	elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${GOOD}*${NORMAL} $*"
	LAST_E_CMD="einfo"
	return 0
}

einfon() {
	elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -ne " ${GOOD}*${NORMAL} $*"
	LAST_E_CMD="einfon"
	return 0
}

ewarn() {
	elog_base WARN "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${WARN}*${NORMAL} ${RC_INDENTATION}$*" >&2
	LAST_E_CMD="ewarn"
	return 0
}

eerror() {
	elog_base ERROR "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${BAD}*${NORMAL} ${RC_INDENTATION}$*" >&2
	LAST_E_CMD="eerror"
	return 0
}

ebegin() {
	local msg="$*" dots spaces=${RC_DOT_PATTERN//?/ }
	if [[ -n ${RC_DOT_PATTERN} ]] ; then
		dots=$(printf "%$(( COLS - 3 - ${#RC_INDENTATION} - ${#msg} - 7 ))s" '')
		dots=${dots//${spaces}/${RC_DOT_PATTERN}}
		msg="${msg}${dots}"
	else
		msg="${msg} ..."
	fi
	einfon "${msg}"
	[[ ${RC_ENDCOL} == "yes" ]] && echo
	LAST_E_LEN=$(( 3 + ${#RC_INDENTATION} + ${#msg} ))
	LAST_E_CMD="ebegin"
	return 0
}

_eend() {
	local retval=${1:-0} efunc=${2:-eerror} msg
	shift 2

	if [[ ${retval} == "0" ]] ; then
		msg="${BRACKET}[ ${GOOD}ok${BRACKET} ]${NORMAL}"
	else
		if [[ -n $* ]] ; then
			${efunc} "$*"
		fi
		msg="${BRACKET}[ ${BAD}!!${BRACKET} ]${NORMAL}"
	fi

	if [[ ${RC_ENDCOL} == "yes" ]] ; then
		echo -e "${ENDCOL}  ${msg}"
	else
		[[ ${LAST_E_CMD} == ebegin ]] || LAST_E_LEN=0
		printf "%$(( COLS - LAST_E_LEN - 6 ))s%b\n" '' "${msg}"
	fi

	return ${retval}
}

eend() {
	local retval=${1:-0}
	shift

	_eend ${retval} eerror "$*"

	LAST_E_CMD="eend"
	return ${retval}
}

KV_major() {
	[[ -z $1 ]] && return 1

	local KV=$@
	echo "${KV%%.*}"
}

KV_minor() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.}
	echo "${KV%%.*}"
}

KV_micro() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.*.}
	echo "${KV%%[^[:digit:]]*}"
}

KV_to_int() {
	[[ -z $1 ]] && return 1

	local KV_MAJOR=$(KV_major "$1")
	local KV_MINOR=$(KV_minor "$1")
	local KV_MICRO=$(KV_micro "$1")
	local KV_int=$(( KV_MAJOR * 65536 + KV_MINOR * 256 + KV_MICRO ))

	# We make version 2.2.0 the minimum version we will handle as
	# a sanity check ... if its less, we fail ...
	if [[ ${KV_int} -ge 131584 ]] ; then
		echo "${KV_int}"
		return 0
	fi

	return 1
}

_RC_GET_KV_CACHE=""
get_KV() {
	[[ -z ${_RC_GET_KV_CACHE} ]] \
		&& _RC_GET_KV_CACHE=$(uname -r)

	echo $(KV_to_int "${_RC_GET_KV_CACHE}")

	return $?
}

unset_colors() {
	COLS="25 80"
	ENDCOL=

	GOOD=
	WARN=
	BAD=
	NORMAL=
	HILITE=
	BRACKET=
}

set_colors() {
	COLS=${COLUMNS:-0}      # bash's internal COLUMNS variable
	(( COLS == 0 )) && COLS=$(set -- $(stty size 2>/dev/null) ; echo $2)
	(( COLS > 0 )) || (( COLS = 80 ))
	COLS=$((${COLS} - 8))	# width of [ ok ] == 7
	# Adjust COLS so that eend works properly on a standard BSD console.
	[ "${TERM}" = "cons25" ] && COLS=$((${COLS} - 1))

	# Now, ${ENDCOL} will move us to the end of the
	# column;  irregardless of character width
	ENDCOL=$'\e[A\e['${COLS}'C'
	if [ -n "${PORTAGE_COLORMAP}" ] ; then
		eval ${PORTAGE_COLORMAP}
	else
		GOOD=$'\e[32;01m'
		WARN=$'\e[33;01m'
		BAD=$'\e[31;01m'
		HILITE=$'\e[36;01m'
		BRACKET=$'\e[34;01m'
	fi
	NORMAL=$'\e[0m'
}

RC_ENDCOL="yes"
RC_INDENTATION=''
RC_DEFAULT_INDENT=2
RC_DOT_PATTERN=''

case "${NOCOLOR:-false}" in
	yes|true)
		unset_colors
		;;
	no|false)
		set_colors
		;;
esac

if [[ -z ${USERLAND} ]] ; then
	case $(uname -s) in
	*BSD|DragonFly)
		export USERLAND="BSD"
		;;
	*)
		export USERLAND="GNU"
		;;
	esac
fi

if [[ -z ${XARGS} ]] ; then
	case ${USERLAND} in
	BSD)
		export XARGS="xargs"
		;;
	*)
		export XARGS="xargs -r"
		;;
	esac
fi

has() {
	hasq "$@"
}

hasv() {
	if hasq "$@" ; then
		echo "$1"
		return 0
	fi
	return 1
}

hasq() {
	[[ " ${*:2} " == *" $1 "* ]]
}

# @FUNCTION: save_ebuild_env
# @DESCRIPTION:
# echo the current environment to stdout, filtering out redundant info.
save_ebuild_env() {
	(

		# misc variables set by bash
		unset BASH HOSTTYPE IFS MACHTYPE OLDPWD \
			OPTERR OPTIND OSTYPE PS4 PWD SHELL SHLVL

		# misc variables inherited from the calling environment
		unset COLORTERM DISPLAY EDITOR LESS LESSOPEN LOGNAME LS_COLORS PAGER \
			TERM TERMCAP USER

		# other variables inherited from the calling environment
		unset ECHANGELOG_USER GPG_AGENT_INFO \
		SSH_AGENT_PID SSH_AUTH_SOCK STY WINDOW XAUTHORITY

		# CCACHE and DISTCC config
		unset ${!CCACHE_*} ${!DISTCC_*}

		# There's no need to bloat environment.bz2 with internally defined
		# functions and variables, so filter them out if possible.

		unset -f dump_trace die diefunc quiet_mode vecho elog_base eqawarn elog \
			esyslog einfo einfon ewarn eerror ebegin _eend eend KV_major \
			KV_minor KV_micro KV_to_int get_KV unset_colors set_colors has \
			hasv hasq qa_source qa_call addread addwrite adddeny addpredict \
			lchown lchgrp esyslog use usev useq has_version portageq \
			best_version use_with use_enable register_die_hook check_KV \
			keepdir unpack strip_duplicate_slashes econf einstall \
			dyn_setup dyn_unpack dyn_clean into insinto exeinto docinto \
			insopts diropts exeopts libopts abort_handler abort_compile \
			abort_test abort_install dyn_compile dyn_test dyn_install \
			dyn_preinst dyn_help debug-print debug-print-function \
			debug-print-section inherit EXPORT_FUNCTIONS newdepend newrdepend \
			newpdepend do_newdepend remove_path_entry \
			save_ebuild_env filter_readonly_variables preprocess_ebuild_env \
			source_all_bashrcs ebuild_phase ebuild_phase_with_hooks \
			${QA_INTERCEPTORS}

		# portage config variables and variables set directly by portage
		unset BAD BRACKET BUILD_PREFIX COLS \
			DISTCC_DIR DISTDIR DOC_SYMLINKS_DIR \
			EBUILD_EXIT_STATUS_FILE EBUILD_FORCE_TEST EBUILD_MASTER_PID \
			ECLASSDIR ECLASS_DEPTH ENDCOL FAKEROOTKEY \
			GOOD HILITE HOME IMAGE \
			LAST_E_CMD LAST_E_LEN LD_PRELOAD MISC_FUNCTIONS_ARGS MOPREFIX \
			NORMAL PKGDIR PKGUSE PKG_LOGDIR PKG_TMPDIR \
			PORTAGE_ACTUAL_DISTDIR PORTAGE_ARCHLIST PORTAGE_BASHRC \
			PORTAGE_BINPKG_TAR_OPTS PORTAGE_BINPKG_TMPFILE PORTAGE_BUILDDIR \
			PORTAGE_COLORMAP PORTAGE_CONFIGROOT PORTAGE_DEBUG \
			PORTAGE_DEPCACHEDIR PORTAGE_GID PORTAGE_INST_GID \
			PORTAGE_INST_UID PORTAGE_LOG_FILE PORTAGE_MASTER_PID \
			PORTAGE_REPO_NAME PORTAGE_RESTRICT PORTAGE_UPDATE_ENV \
			PORTAGE_WORKDIR_MODE PORTDIR \
			PORTDIR_OVERLAY ${!PORTAGE_SANDBOX_*} PREROOTPATH \
			PROFILE_PATHS PWORKDIR QA_INTERCEPTORS \
			RC_DEFAULT_INDENT RC_DOT_PATTERN RC_ENDCOL \
			RC_INDENTATION READONLY_EBUILD_METADATA READONLY_PORTAGE_VARS \
			ROOT ROOTPATH RPMDIR STARTDIR TMP TMPDIR USE_EXPAND \
			WARN XARGS _RC_GET_KV_CACHE

		# user config variables
		unset DOC_SYMLINKS_DIR INSTALL_MASK PKG_INSTALL_MASK

		set
		export
	)
}

true
