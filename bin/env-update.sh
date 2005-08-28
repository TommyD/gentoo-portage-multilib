#!/bin/bash
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/bin/env-update.sh,v 1.2 2004/10/04 13:56:50 vapier Exp $

############################################
############################################
# ENVIRONMENT SETUP
############################################

if [[ ${EUID} -ne 0 ]] ; then
	echo "$0: must be root."
	exit 1
fi

# Make sure our environment is sane
if [[ ! -z "${MAKELINKS}" ]] ; then
	export MAKELINKS=0
else
	export MAKELINKS=1
fi
export ROOT="${ROOT:=/}"
[[ ${ROOT} == */ ]] || export ROOT="${ROOT}/"

export ENVDIR="${ROOT}etc/env.d"
mkdir -p ${ENVDIR}
chmod 755 ${ENVDIR}
specials="
	KDEDIRS PATH CLASSPATH LDPATH MANPATH INFODIR INFOPATH ROOTPATH
	CONFIG_PROTECT CONFIG_PROTECT_MASK PRELINK_PATH PYTHONPATH
	PRELINK_PATH_MASK ADA_INCLUDE_PATH ADA_OBJECTS_PATH"
colon_separated="
	ADA_INCLUDE_PATH ADA_OBJECTS_PATH LDPATH PATH MANPATH ROOTPATH
	PRELINK_PATH PRELINK_PATH_MASK PYTHON_PATH"

export LDSOCONF="${ROOT}etc/ld.so.conf"

export PRELINKCONF="${ROOT}etc/prelink.conf"
defaultprelinkpaths=":/bin:/sbin:/usr/bin:/usr/sbin:/lib:/usr/lib"

export PROFILEENV="${ROOT}etc/profile.env"
export CSHENV="${ROOT}etc/csh.env"

# make sure we aren't tricked with previous 'my_envd_' variables
unset $(set | grep '^my_envd_' | cut -d= -f1)

############################################
############################################
# ENV.D PARSING
############################################

do_has() {
	local x
	local me="$1"
	shift

	for x in "$@" ; do
		[[ ${x} == ${me} ]] && return 0
	done
	return 1
}
has() {
	local ret
	local ifs="${IFS}"
	unset IFS
	do_has $1 ${!2}
	ret=$?
	export IFS="${ifs}"
	return ${ret}
}
is_special() {
	has $1 specials
}
is_colon_separated() {
	has $1 colon_separated
}

for envd in $(ls ${ENVDIR} | sort) ; do
	# make sure file is a vaild env'd entry and not a backup file
	num="${envd:0:2}"
	if [[ ! -z ${num//[0-9]} ]] ; then
		continue
	elif [[ ${envd} == *~ || ${envd} == *.bak ]] ; then
		continue
	fi

	# use bash to make sure the file is valid
	envd="${ENVDIR}/${envd}"
	if ! (source "${envd}") ; then
		echo "!!! Error parsing ${envd}!"
		exit 1
	fi

	# parse env.d entries
	cnfvars="$(grep '^[[:alpha:]_][[:alnum:]_]*=' "${envd}")"
	export IFS=$'\n'
	for cnfv in ${cnfvars} ; do
		var="${cnfv/=*}"
		val="${cnfv:${#var}+1}"
		if [ "${val:0:1}" == "\"" ] ; then
			val="${val:1:${#val}-2}"
		fi
		myvar="my_envd_${var}"
		if is_special ${var} ; then
			if [[ ! -z "${!myvar}" ]] ; then
				if is_colon_separated ${var} ; then
					sep=":"
				else
					sep=" "
				fi
			else
				sep=""
			fi
			export ${myvar}="${!myvar}${sep}${val}"
		else
			export ${myvar}="${val}"
		fi
	done
	unset IFS
done

############################################
############################################
# LD.SO.CONF HANDLING
############################################

# create a : sep list from ld.so.conf
export OLD_LDPATH=""
if [ -s "${LDSOCONF}" ] ; then
	while read line ; do
		if [[ "${line:0:1}" == "#" ]] ; then
			continue
		fi
		export OLD_LDPATH="${OLD_LDPATH}:${line}"
	done < ${LDSOCONF}
	export OLD_LDPATH="${OLD_LDPATH:1}"
fi

# has the ldpath changed ?  if so, recreate
if [[ "${OLD_LDPATH}" != "${my_envd_LDPATH}" ]] ; then
	cat << EOF > ${LDSOCONF}
# ld.so.conf autogenerated by env-update; make all changes to
# contents of /etc/env.d directory
${my_envd_LDPATH//:/
}
EOF
fi

############################################
############################################
# HANDLE PRELINK PATHS
############################################

if prelink --version >& /dev/null ; then
	# we assume LDPATH and PATH aren't empty ... if they were, we got other problems
	envdprelinkcheckpaths="${my_envd_LDPATH}:${my_envd_PATH}"
	if [[ ! -z "${my_envd_PRELINK_PATH}" ]] ; then
		envdprelinkcheckpaths="${envdprelinkcheckpaths}:${my_envd_PRELINK_PATH}"
	fi

	if [[ ! -z "${my_envd_PRELINK_PATH_MASK}" ]] ; then
		export prelink_mask=":${PRELINK_PATH_MASK}:"
		envdprelinkpaths=""
		export IFS=":"
		for dir in ${envdprelinkcheckpaths} ; do
			if [[ ${dir:0-1} == / ]] ; then
				noslashdir="${dir:0:${#dir}-1}"
			else
				dir="${dir}/"
				noslashdir="${dir}"
			fi
			if [[ ${prelink_mask/:${dir}:/} == ${prelink_mask} \
				&& ${prelink_mask/:${noslashdir}:/} == ${prelink_mask} ]] ; then
				envdprelinkpaths="${envdprelinkpaths}:${dir}"
			fi
		done
		unset IFS
	else
		envdprelinkpaths=":${envdprelinkcheckpaths}"
	fi

	cat << EOF > ${PRELINKCONF}
# prelink.conf autogenerated by env-update; make all changes to
# contents of /etc/env.d directory
${defaultprelinkpaths//:/
-l }
${envdprelinkpaths//:/
-h }
EOF
fi
unset my_envd_LDPATH

############################################
############################################
# RUN EXTERNAL PROGRAMS NOW
############################################

echo ">>> Regenerating ${ROOT}etc/ld.so.cache..."
if [[ ${MAKELINKS} -eq 0 ]] ; then
	(cd / ; /sbin/ldconfig -X -r ${ROOT} >& /dev/null)
else
	(cd / ; /sbin/ldconfig -r ${ROOT} >& /dev/null)
fi

cat << EOF > ${PROFILEENV}
# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.
# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES
# GO INTO /etc/profile NOT /etc/profile.env

$(set | grep '^my_envd_' | sed -e 's:^my_envd_:export :')
EOF

cat << EOF > ${CSHENV}
# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.
# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES
# GO INTO /etc/csh.cshrc NOT /etc/csh.env

$(set | grep '^my_envd_' | sed -e 's:^my_envd_\([[:alpha:]_][[:alnum:]_]*\)=:setenv \1 :')
EOF

[[ ${ROOT} == / ]] && /sbin/depscan.sh
