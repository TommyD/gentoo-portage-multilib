#!/bin/bash
# ebuild-daemon.sh; core ebuild processor handling code
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
$Header$
 
source /usr/lib/portage/bin/ebuild.sh daemonize

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
#alias listen='read -u 3 -t 10'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'

listen() {
	if ! read -u 3 $1; then
		echo "coms error, read failed: backing out of daemon."
		exit 1
	fi
}

speak() {
	echo "$*" >&4
}
declare -rf speak

listen com
if [ "$com" != "dude?" ]; then
	echo "serv init coms failed, received $com when expecting 'dude?'"
	exit 1
fi
speak "dude!"

if [ ! -z "$SANDBOX_LOG" ]; then
	listen com
	if [ "$com" != "sandbox_log?" ]; then
		echo "unknown com '$com'"
		exit 1
	fi
	speak "$SANDBOX_LOG"
	declare -rx SANDBOX_LOG="$SANDBOX_LOG" #  #="/tmp/sandbox-${P}-${PORTAGE_SANDBOX_PID}.log"
	addwrite $SANDBOX_LOG
fi
#source_profiles

portageq() {
	local line e alive
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		echo "QA Notice: portageq() in global scope for ${CATEGORY}/${PF}" >&2
	fi
	speak "portageq $*"
	listen line
	declare -i e
	e=$(( ${line/return_code=} + 0 ))
	alive=1
	while [ $alive == 1 ]; do
		listen line
		if [ "$line" == "stop_text" ]; then
			alive=0
		else
			echo "portageq: $line"
		fi
	done
	return $e
}
declare -fr portageq

alive='1'
re="$(readonly | cut -s -d '=' -f 1 | cut -s -d ' ' -f 3)"
for x in $re; do
	if ! hasq $x "$DONT_EXPORT_VARS"; then
		DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $x"
	fi
done
speak $re
unset x re
	
request_sandbox_summary() {
	local line
	speak "request_sandbox_summary ${SANDBOX_LOG}"
	listen line
	while [ "$line" != "end_sandbox_summary" ]; do	
		echo "$line"
		listen line
	done
}		

request_confcache() {
	if ! hasq confcache $FEATURES || ! hasq sandbox $FEATURES || hasq confcache $RESTRICT; then
		return 1
	fi
	local line
	speak "request_confcache $1"
	listen line s
	while [ "${line#request}" != "${line}" ]; do
		# var requests for updating the cache's ac_cv_env
		# send set, then val
		line="$(echo ${line#request})"
		if [ "${!line:+set}" == "set" ]; then
			speak set
			speak "${!line}"
		else
			speak unset
		fi
		listen line
	done
	if [ "${line:0:9}" == "location:" ]; then
		cp -v "${line:10}" $1
	elif [ "${line}" == "empty" ]; then
		echo ">>> Confcache is empty, starting anew"
	fi
	if hasq "${line/: *}" location empty; then
		echo ">>> Temporary configure cache file is $1"
		export PORTAGE_CONFCACHE_STATE=1
		export SANDBOX_DEBUG_LOG="${T}/debug_log"
		export SANDBOX_DEBUG=1
		return 0
	fi
#	fi
#	if [ "$line" == "empty" ]; then
#		echo "confcache is empty, starting anew" >&2
#		return 0
#	elif [ "$line" == "transferred" ]; then
#		return 0
#	fi;

	return 1
}

update_confcache() {
	local line
	if [ "$PORTAGE_CONFCACHE_STATE" != "1" ]; then
		return 0
	fi
	unset SANDBOX_DEBUG
	unset PORTAGE_CONFCACHE_STATE
	if ! hasq sandbox $FEATURES; then
		echo "not updating confcache, sandbox isn't set in features" >&2
		return 1
	fi
	speak "update_confcache $SANDBOX_DEBUG_LOG $1"
	unset SANDBOX_DEBUG_LOG
	listen line
	if [ "$line" == "updated" ]; then
		return 0
	fi
	return 1
}

DONT_EXPORT_FUNCS="$(declare -F | cut -s -d ' ' -f 3)"

DONT_EXPORT_VARS="${DONT_EXPORT_VARS} alive com PORTAGE_LOGFILE cont"

#INIT_VARS=$(declare | egrep '^[^[:space:]{}()]+=' | cut -s -d '=' -f 1)
#INIT_FUNCS=$(declare -F | cut -s -d ' ' -f 3)
#readonly INIT_VARS
#readonly INIT_FUNCS cleanse_vars cleanse_funcs
# QA interceptors are on by default, disabled when not processing depend.
# why?  because enabling QA interceptors is expensive, and nukes regen performance.
export QA_CONTROLLED_EXTERNALLY="yes"
enable_qa_interceptors
source "/usr/lib/portage/bin/ebuild-functions.sh" || die "failed sourcing ebuild-functions.sh"

export PORTAGE_PRELOADED_ECLASSES=''
unset_colors


PATH='/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:/usr/lib/portage/bin'
while [ "$alive" == "1" ]; do
	#reset com.  we have a time out via listen, so don't let previous commands be rexecuted just cause the read timed out.
	com=''
	listen com
	case $com in
	process_ebuild*)
		# cleanse whitespace.
		phases="$(echo ${com#process_ebuild})"
		PORTAGE_SANDBOX_PID="$PPID"
		(
		if [ "${phases/depend/}" == "$phases" ]; then
			disable_qa_interceptors
		fi
		line=''
		cont=0
		while [ "$cont" == 0 ]; do
			line=''
			listen line
			if [ "$line" == "start_receiving_env" ]; then
				while listen line && [ "$line" != "end_receiving_env" ]; do #[ "$line" != "end_receiving_env" ]; do
					eval "$line"
					if [ $? != "0" ]; then
					 	echo "err, env receiving threw an error for '$line': $?" >&2
						echo "env_receiving_failed" >&2
						speak "env_receiving_failed"
						cont=1
						break
					fi
				done
				if [ "$cont" == "0" ]; then
					speak "env_received"
				fi
			elif [ "${line:0:7}" == "logging" ]; then
				PORTAGE_LOGFILE="$(echo ${line#logging})"
#				echo "logging to $logfile" >&2
				speak "logging_ack"
			elif [ "${line:0:17}" == "set_sandbox_state" ]; then
				if [ $((${line:18})) -eq 0 ]; then
					export SANDBOX_DISABLED=1
#					echo "disabling sandbox due to '$line'" >&2
				else
					export SANDBOX_DISABLED=0
#					echo "enabling sandbox" >&2
				fi
			elif [ "${line}" == "start_processing" ]; then
				cont=2
			else
				echo "received unknown com: $line" >&2
			fi
		done
		if [ "$cont" != 2 ]; then
			exit $cont
		else
			reset_sandbox
			if [ -n "$SANDBOX_LOG" ] && [ -n "$PORTAGE_LOGFILE" ]; then
				addwrite "$PORTAGE_LOGFILE"
			fi
			speak "starting ${phases}"
			if [ -z $RC_NOCOLOR ]; then
				set_colors
			fi
			DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} ${PORTAGE_PRELOADED_ECLASSES}"
			for e in $phases; do
				if [ -z $PORTAGE_LOGFILE ]; then
					execute_phases ${e}
				else
					# why do it this way rather then the old '[ -f ${T}/.succesfull }'?
					# simple.  this allows the actual exit code to be used, rather then just stating no .success == 1 || 0
					execute_phases ${e} &> >(umask 0002; tee -i -a $PORTAGE_LOGFILE)
				fi
				ret=$?
				if [ -n "$SANDBOX_LOG" ] && [ -e "$SANDBOX_LOG" ]; then
					ret=1
					echo "sandbox exists- $SANDBOX_LOG"
					request_sandbox_summary
					
				fi
				if [ "$ret" != "0" ]; then
					exit $(($ret))
				fi
			done
		fi
		)
		if [ $? != 0 ]; then
			echo "phases failed"
			speak "phases failed"
			speak "execute: $?"
		else
#			echo "phases succeeded"
			speak "phases succeeded"
		fi
		;;
	shutdown_daemon)
		alive="0"
		;;
	preload_eclass*)
		echo "preloading eclasses into funcs." >&2
		disable_qa_interceptors
		success="succeeded"
		com="${com#preload_eclass }"
		for e in ${com}; do
			x="${e##*/}"
			x="${x%.eclass}"
			echo "preloading eclass $x" >&2
			if ! bash -n "$e"; then
				echo "errors detected in '$e'" >&2
				success='failed'
				break
			fi
			y="$( < $e)"
			eval "eclass_${x}_inherit() {
				$y
			}"
		done
		speak "preload_eclass ${success}"
		unset e x y success
		enable_qa_interceptors
		export PORTAGE_PRELOADED_ECLASSES="$PORTAGE_PRELOADED_ECLASSES ${com}"
		;;
	esac
done
exit 0
