#!/bin/bash
# ebuild-daemon.sh; core ebuild processor handling code
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
$Header$
 
source /usr/lib/portage/bin/ebuild.sh daemonize

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
#alias listen='read -u 3 -t 10'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'

# use listen/speak for talking to the running portage instance instead of echo'ing to the fd yourself.
# this allows us to move the open fd's w/out issues down the line.
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

# ensure the other side is still there.  Well, this moreso is for the python side to ensure
# loading up the intermediate funcs succeeded.
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

# portageq hijack- redirects all requests back through the pipes and has the python side execute it.
# much faster, also avoids the gpg/sandbox being active issues.
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
	
# ask the python side to display sandbox complaints.
request_sandbox_summary() {
	local line
	speak "request_sandbox_summary ${SANDBOX_LOG}"
	listen line
	while [ "$line" != "end_sandbox_summary" ]; do	
		echo "$line"
		listen line
	done
}		

# request the global confcache be transferred to $1 for usage.
# flips the sandbox vars as needed.
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
	return 1
}

# notify python side configure calls are finished.
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

# depend's speed up.  turn on qa interceptors by default, instead of flipping them on for each depends
# call.
export QA_CONTROLLED_EXTERNALLY="yes"
enable_qa_interceptors

source "/usr/lib/portage/bin/ebuild-functions.sh" || die "failed sourcing ebuild-functions.sh"

export PORTAGE_PRELOADED_ECLASSES=''
unset_colors


PATH='/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:/usr/lib/portage/bin'
while [ "$alive" == "1" ]; do
	com=''
	listen com
	case $com in
	process_ebuild*)
		# cleanse whitespace.
		phases="$(echo ${com#process_ebuild})"
		PORTAGE_SANDBOX_PID="$PPID"
		# note the (; forks. prevents the initialized ebd env from being polluted by ebuild calls.
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
			if [ -n "$SANDBOX_LOG" ]; then
				addwrite $SANDBOX_LOG
				if [ -n "$PORTAGE_LOGFILE" ]; then
					addwrite "$PORTAGE_LOGFILE"
				fi
			fi
			speak "starting ${phases}"
			if [ -z $RC_NOCOLOR ]; then
				set_colors
			fi
			DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} ${PORTAGE_PRELOADED_ECLASSES}"
			for e in $phases; do
				if [ -z $PORTAGE_LOGFILE ]; then
					execute_phases ${e}
					ret=$?
				else
					# why do it this way rather then the old '[ -f ${T}/.succesfull }'?
					# simple.  this allows the actual exit code to be used, rather then just stating no .success == 1 || 0
					# note this was
					# execute_phases ${e] &> >(umask 0002; tee -i -a $PORTAGE_LOGFILE)
					# less then bash v3 however hates it.  And I hate less then v3.
					# circle of hate you see.
					execute_phases ${e} 2>&1 | {
						umask 0002
						tee -i -a $PORTAGE_LOGFILE
					}
					ret=${PIPESTATUS[0]}
				fi
				# if sandbox log exists, then there were complaints from it.
				# tell python to display the errors, then dump relevant vars for debugging.
				if [ -n "$SANDBOX_LOG" ] && [ -e "$SANDBOX_LOG" ]; then
					ret=1
					echo "sandbox exists- $SANDBOX_LOG"
					request_sandbox_summary
					echo "SANDBOX_ON:=${SANDBOX_ON:-unset}" >&2
					echo "SANDBOX_DISABLED:=${SANDBOX_DISABLED:-unset}" >&2
					echo "SANDBOX_READ:=${SANDBOX_READ:-unset}" >&2
					echo "SANDBOX_WRITE:=${SANDBOX_WRITE:-unset}" >&2
					echo "SANDBOX_PREDICT:=${SANDBOX_PREDICT:-unset}" >&2
					echo "SANDBOX_DEBUG:=${SANDBOX_DEBUG:-unset}" >&2
					echo "SANDBOX_DEBUG_LOG:=${SANDBOX_DEBUG_LOG:-unset}" >&2
					echo "SANDBOX_LOG:=${SANDBOX_LOG:-unset}" >&2
					echo "SANDBOX_ARMED:=${SANDBOX_ARMED:-unset}" >&2
				fi
				if [ "$ret" != "0" ]; then
					exit $(($ret))
				fi
			done
		fi
		)
		# post fork.  tell python if it succeeded or not.
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
