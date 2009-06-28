# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$


# @FUNCTION: _debug
# @USAGE: <name_of_variable> <content_of_variable>
# @DESCRIPTION: print debug output if MULTILIB_DEBUG is set
_debug() {
	[[ -n ${MULTILIB_DEBUG} ]] && einfo "MULTILIB_DEBUG: ${1}=\"${2}\""
}

# Internal function
# @FUNCTION: _abi_to_index_key
# @USAGE: <ABI>
# @RETURN: <index key>
_abi_to_index_key() {
	# Until we can count on bash version > 4, we can't use associative
	# arrays.
	local index=0 element=""
	if [[ -z "${EMULTILIB_ARRAY_INDEX}" ]]; then
		local abilist=""
		abilist=$(get_abi_order)
		EMULTILIB_ARRAY_INDEX=(INIT ${abilist})
	fi
	for element in ${EMULTILIB_ARRAY_INDEX[@]}; do
		[[ "${element}" == "${1}" ]] && echo "${index}"
		let index++
	done
}

# @VARIABLE: EMULTILIB_SAVE_VARS
# @DESCRIPTION: Environment variables to save
# EMULTILIB_SAVE_VARS="${EMULTILIB_SAVE_VARS}
#		AS CC CXX FC LD ASFLAGS CFLAGS CXXFLAGS FCFLAGS FFLAGS LDFLAGS
#		CHOST CBUILD CDEFINE LIBDIR S CCACHE_DIR myconf PYTHON PERLBIN
#		QMAKE QMAKESPEC QTBINDIR CMAKE_BUILD_DIR mycmakeargs KDE_S
#		ECONF_SOURCE MY_LIBDIR"
EMULTILIB_SAVE_VARS="${EMULTILIB_SAVE_VARS}
		AS CC CXX FC LD ASFLAGS CFLAGS CXXFLAGS FCFLAGS FFLAGS LDFLAGS
		CHOST CBUILD CDEFINE LIBDIR S CCACHE_DIR myconf PYTHON PERLBIN
		QMAKE QMAKESPEC QTBINDIR CMAKE_BUILD_DIR mycmakeargs KDE_S
		ECONF_SOURCE MY_LIBDIR"

# @VARIABLE: EMULTILIB_SOURCE_TOP_DIRNAME
# @DESCRIPTION: On initialisation of multilib environment this gets incremented by 1
# EMULTILIB_INITIALISED=""
EMULTILIB_INITIALISED="0"

# Internal function
# @FUNCTION: _save_abi_env
# @USAGE: <ABI>
# @DESCRIPTION: Save environment for ABI
_save_abi_env() {
	[[ -n ${MULTILIB_DEBUG} ]] && \
		einfo "MULTILIB_DEBUG: Saving Environment:" "${1}"
	local _var _array
	for _var in ${EMULTILIB_SAVE_VARS}; do
		_array="EMULTILIB_${_var}"
		_debug ${_array}[$(_abi_to_index_key ${1})] "${!_var}"
		eval "${_array}[$(_abi_to_index_key ${1})]"=\"${!_var}\"
	done
}

# Internal function
# @FUNCTION: _restore_abi_env
# @USAGE: <ABI>
# @DESCRIPTION: Restore environment for ABI
_restore_abi_env() {
	[[ -n ${MULTILIB_DEBUG} ]] && \
		einfo "MULTILIB_DEBUG: Restoring Environment:" "${1}"
	local _var _array
	for _var in ${EMULTILIB_SAVE_VARS}; do
		_array="EMULTILIB_${_var}[$(_abi_to_index_key ${1})]"
		_debug "${_var}" "${!_array}"
		export ${_var}="${!_array}"
	done
}

# @FUNCTION: get_abi_var
# @USAGE: <VAR> [ABI]
# @RETURN: returns the value of ${<VAR>_<ABI>} which should be set in make.defaults
# @DESCRIPTION:
# ex:
# CFLAGS=$(get_abi_var CFLAGS sparc32) # CFLAGS=-m32
#
# Note that the prefered method is to set CC="$(tc-getCC) $(get_abi_CFLAGS)"
# This will hopefully be added to portage soon...
#
# If <ABI> is not specified, ${ABI} is used.
# If <ABI> is not specified and ${ABI} is not defined, ${DEFAULT_ABI} is used.
# If <ABI> is not specified and ${ABI} and ${DEFAULT_ABI} are not defined, we return an empty string.
get_abi_var() {
	local flag=$1
	local abi
	if [ $# -gt 1 ]; then
		abi=${2}
	elif [ -n "${ABI}" ]; then
		abi=${ABI}
	elif [ -n "${DEFAULT_ABI}" ]; then
		abi=${DEFAULT_ABI}
	else
		abi="default"
	fi

	local var="${flag}_${abi}"
	echo ${!var}
}

# @FUNCTION prep_ml_binaries
# @USAGE:
# @DESCRIPTION: Use wrapper to support non-default binaries
prep_ml_binaries() {
	for binary in "$@"; do
		mv ${binary} ${binary}-${ABI} || die
		_debug ${binary} ${binary}-${ABI}
		if [[ ${ABI} == ${DEFAULT_ABI} ]]; then
			ln -s /usr/bin/abi-wrapper ${binary} || die
			_debug /usr/bin/abi-wrapper ${binary}
		fi
	done
}

tc-getPROG() {
        local var=$1
        local prog=$2

        if [[ -n ${!var} ]] ; then
                echo "${!var}"
                return 0
        fi

        local search=
        [[ -n $3 ]] && search=$(type -p "$3-${prog}")
        [[ -z ${search} && -n ${CHOST} ]] && search=$(type -p "${CHOST}-${prog}")
        [[ -n ${search} ]] && prog=${search##*/}

        export ${var}=${prog}
        echo "${!var}"
}

has_multilib_profile() {
	[ -n "${MULTILIB_ABIS}" -a "${MULTILIB_ABIS}" != "${MULTILIB_ABIS/ /}" ]
}

is_auto-multilib() {
	if ( [[ "${ARCH}" == "amd64" ]] || [[ "${ARCH}" == "ppc64" ]] ) && has_multilib_profile && use lib32 && ! hasq multilib-native ${INHERITED}; then
		return 0
	fi
	return 1
}

get_abi_order() {
	local order= dodefault=

	if is_auto-multilib; then
		for x in ${MULTILIB_ABIS}; do
			if [ "${x}" != "${DEFAULT_ABI}" ]; then
				order="${order} ${x}"
			else
				dodefault=1
			fi
		done
		[ "$dodefault" ] && order="${order} ${DEFAULT_ABI}"
	else
		order="${DEFAULT_ABI}"
	fi

	if [ -z "${order}" ]; then
		die "Could not determine your profile ABI(s).  Perhaps your USE flags or MULTILIB_ABIS are too restrictive for this package or your profile does not set DEFAULT_ABI."
	fi

	echo ${order}
}

set_abi() {
	is_auto-multilib || return 0;

	if [ "$#" != "1" ]; then
		die "set_abi needs to be given the ABI to use."
	fi

	local abi=${1}

	# Save ABI if it is already set
	if [[ -n "${ABI}" ]]; then
		ABI_SAVE=${ABI}
	fi

	if [ -d "${WORKDIR}" ]; then
		_unset_abi_dir
	fi

	if [ -d "${WORKDIR}.${abi}" ]; then
		# If it doesn't exist, then we're making it soon in dyn_unpack
		mv ${WORKDIR}.${abi} ${WORKDIR} || die "IO Failure -- Failed to 'mv work.${abi} work'"
	fi

	echo "${abi}" > ${PORTAGE_BUILDDIR}/.abi || die "IO Failure -- Failed to create .abi."

	# Export variables we need for toolchain
	export ABI="${abi}"
	echo ">>> ABI=${ABI}"
	if [[ "${EMULTILIB_INITIALISED}" == "1" ]]; then
		_save_abi_env "${ABI_SAVE}"
		_restore_abi_env "${ABI}"
	else
		_save_abi_env "INIT"
		for i in ${MULTILIB_ABIS}; do
			export ABI="${i}"
			_restore_abi_env "INIT"
			_setup_abi_env "${i}"
			_save_abi_env "${i}"
		done
		export ABI="${abi}"
		_restore_abi_env "${ABI}"
		EMULTILIB_INITIALISED="1"
	fi
}

_unset_abi_dir() {
	if [ -f "${PORTAGE_BUILDDIR}/.abi" ]; then
		local abi=$(cat ${PORTAGE_BUILDDIR}/.abi)
		[ ! -d "${WORKDIR}" ] && die "unset_abi: .abi present (${abi}) but workdir not present."

		mv ${WORKDIR} ${WORKDIR}.${abi} || die "IO Failure -- Failed to 'mv work work.${abi}'."
		rm -rf ${PORTAGE_BUILDDIR}/.abi || die "IO Failure -- Failed to 'rm -rf .abi'."
	fi
}

unset_abi() {
	is_auto-multilib || return 0;

        _unset_abi_dir
		_save_abi_env "${ABI}"
		export ABI=${DEFAULT_ABI}
		_restore_abi_env "${ABI}"
}

_get_abi_string() {
	if is_auto-multilib && [ -n "${ABI}" ]; then
		echo " (for ABI=${ABI})"
	fi
}

_setup_abi_env() {
	# Set the CHOST native first so that we pick up the native
	# toolchain and not a cross-compiler by accident #202811.
	export CHOST=$(get_abi_var CHOST ${DEFAULT_ABI})
	export AS="$(tc-getPROG AS as)"
	export CC="$(tc-getPROG CC gcc)"
	export CXX="$(tc-getPROG CXX g++)"
	export FC="$(tc-getPROG FC gfortran)"
	export LD="$(tc-getPROG LD ld)"
	export CHOST=$(get_abi_var CHOST $1)
	export CBUILD=$(get_abi_var CHOST $1)
	export CDEFINE="${CDEFINE} $(get_abi_var CDEFINE $1)"
	export LD="${LD} $(get_abi_var LDFLAGS)"
	export CFLAGS="${CFLAGS} $(get_abi_var CFLAGS)"
	export CXXFLAGS="${CXXFLAGS} $(get_abi_var CFLAGS)"
	export FCFLAGS="${FCFLAGS} ${CFLAGS}"
	export FFLAGS="${FFLAGS} ${CFLAGS}"
	export ASFLAGS="${ASFLAGS} $(get_abi_var ASFLAGS)"
	export LIBDIR=$(get_abi_var LIBDIR $1)
	export LDFLAGS="${LDFLAGS} -L/${LIBDIR} -L/usr/${LIBDIR} $(get_abi_var CFLAGS)"
	if ! [[ "${ABI}" == "${DEFAULT_ABI}" ]]; then
		pyver=$(python --version 2>&1)
		pyver=${pyver/Python /python}
		pyver=${pyver%.*}
		export PYTHON="/usr/bin/${pyver}-${ABI}"
		export PERLBIN="/usr/bin/perl-${ABI}"
	fi
}

# Remove symlinks for alternate ABIs so that packages that use
# symlink without using the force option to ln ("-f").
#
# Also, create multilib header redirects if any of the headers
# differ between ABIs.
#
# ABI_HEADER_DIRS defaults to /usr/include but the ebuild can override
#
_finalize_abi_install() {
	local ALL_ABIS=$(get_abi_order)
	local ALTERNATE_ABIS=${ALL_ABIS% *}
	local dirs=${ABI_HEADER_DIRS-/usr/include}
	local base=

	# Sanity check  ABI variables
	[ "${ALL_ABIS}" != "${ALL_ABIS/ /}" ] || return 0;
	[ -n "${ABI}" ] && [ -n "${DEFAULT_ABI}" ] || return 0;

	# Save header files for each ABI
	for dir in ${dirs}; do
		[ -d "${D}/${dir}" ] || continue
		vecho ">>> Saving headers $(_get_abi_string)"
		base=${T}/gentoo-multilib/${dir}/gentoo-multilib
		mkdir -p ${base}
		[ -d ${base}/${ABI} ] && rm -rf ${base}/${ABI}
		mv ${D}/${dir} ${base}/${ABI} || die "ABI header save failed"
	done

	# Symlinks are not overwritten without the "-f" option, so
	# remove them in non-default ABI
	if [ "${ABI}" != "${DEFAULT_ABI}" ]; then
		vecho ">>> Removing installed symlinks $(_get_abi_string)"
		find ${D} -type l ! -regex '.*/lib[0-9]*/.*' -exec rm -f {} \;
	fi

	# After final ABI is installed, if headers differ
	# then create multilib header redirects
	if [ "${ABI}" = "${DEFAULT_ABI}" ]; then
		local diffabi= abis_differ=
		for dir in ${dirs}; do
			base=${T}/gentoo-multilib/${dir}/gentoo-multilib
			[ -d "${base}" ] || continue
			for diffabi in ${ALTERNATE_ABIS}; do
				diff -rNq ${base}/${ABI} ${base}/${diffabi} || abis_differ=1
			done
		done

		if [ -z "${abis_differ}" ]; then
			# No differences, restore original header files for default ABI
			for dir in ${dirs}; do
				base=${T}/gentoo-multilib/${dir}/gentoo-multilib
				[ -d "${base}" ] || continue
				mv ${base}/${ABI} ${D}/${dir} \
					|| die "ABI header restore failed"
			done
		else # ABIS differ
			vecho ">>> Creating multilib headers"
			base=${T}/gentoo-multilib
			pushd "${base}"
			find . | tar -c -T - -f - | tar -x --no-same-owner -f - -C ${D}
			popd

			# This 'set' stuff is required by mips profiles to properly pass
			# CDEFINE's (which have spaces) to sub-functions
			set --
			for dir in ${dirs} ; do
				set -- "$@" "${dir}"
				for diffabi in ${ALL_ABIS}; do
					local define_var=CDEFINE_${diffabi}
					set -- "$@" "${!define_var}:${dir}/gentoo-multilib/${diffabi}"
				done
				_create_abi_includes "$@"
			done
		fi
	fi

	# Create wrapper symlink for *-config files
	local i= files=( $(find "${D}" -name *-config) )
	_debug files ${files}
	for i in ${files}; do
		prep_ml_binaries "${i}"
	done
}

#
# These _create_abi_includes* routines were ripped pretty wholesale from multilib.eclass
#

# The first argument is the common dir.  The remaining args are of the
# form <symbol>:<dir> where <symbol> is what is put in the #ifdef for
# choosing that dir.
#
# Ideas for this code came from debian's sparc-linux headers package.
#
# Example:
# _create_abi_includes /usr/include/asm __sparc__:/usr/include/asm-sparc __sparc64__:/usr/include/asm-sparc64
# _create_abi_includes /usr/include/asm __i386__:/usr/include/asm-i386 __x86_64__:/usr/include/asm-x86_64
#
# Warning: Be careful with the ordering here. The default ABI has to be the
# last, because it is always defined (by GCC)
_create_abi_includes() {
	local dest=$1
	shift
	local basedirs=$(_create_abi_includes-listdirs "$@")

	_create_abi_includes-makedestdirs ${dest} ${basedirs}

	local file
	for file in $(_create_abi_includes-allfiles ${basedirs}) ; do
		#local name=$(echo ${file} | tr '[:lower:]' '[:upper:]' | sed 's:[^[:upper:]]:_:g')
		(
			echo "/* Autogenerated by by portage FEATURE auto-multilib */"

			local dir
			for dir in ${basedirs}; do
				if [[ -f ${D}/${dir}/${file} ]] ; then
					echo ""
					local sym=$(_create_abi_includes-sym_for_dir ${dir} "$@")
					if [[ ${sym/=} != "${sym}" ]] ; then
						echo "#if ${sym}"
					elif [[ ${sym::1} == "!" ]] ; then
						echo "#ifndef ${sym:1}"
					else
						echo "#ifdef ${sym}"
					fi
					echo "# include <$(_create_abi_includes-absolute ${dir}/${file})>"
					echo "#endif /* ${sym} */"
				fi
			done

			#echo "#endif /* __CREATE_ABI_INCLUDES_STUB_${name}__ */"
		) > "${D}/${dest}/${file}"
	done
}

# Helper function for _create_abi_includes
_create_abi_includes-absolute() {
	local dst="$(_create_abi_includes-tidy_path $1)"

	dst=(${dst//\// })

	local i
	for ((i=0; i<${#dst[*]}; i++)); do
		[ "${dst[i]}" == "include" ] && break
	done

	local strip_upto=$i

	for ((i=strip_upto+1; i<${#dst[*]}-1; i++)); do
		echo -n ${dst[i]}/
	done

	echo -n ${dst[i]}
}

# Helper function for _create_abi_includes
_create_abi_includes-tidy_path() {
	local removed=$1

	if [ -n "${removed}" ]; then
		# Remove multiple slashes
		while [ "${removed}" != "${removed/\/\//\/}" ]; do
			removed=${removed/\/\//\/}
		done

		# Remove . directories
		while [ "${removed}" != "${removed//\/.\//\/}" ]; do
			removed=${removed//\/.\//\/}
		done
		[ "${removed##*/}" = "." ] && removed=${removed%/*}

		# Removed .. directories
		while [ "${removed}" != "${removed//\/..\/}" ]; do
			local p1="${removed%%\/..\/*}"
			local p2="${removed#*\/..\/}"

			removed="${p1%\/*}/${p2}"
		done

		# Remove trailing ..
		[ "${removed##*/}" = ".." ] && removed=${removed%/*/*}

		# Remove trailing /
		[ "${removed##*/}" = "" ] && removed=${removed%/*}

		echo ${removed}
	fi
}

# Helper function for create_abi_includes
_create_abi_includes-listdirs() {
	local dirs
	local data
	for data in "$@"; do
		dirs="${dirs} ${data/*:/}"
	done
	echo ${dirs:1}
}

# Helper function for _create_abi_includes
_create_abi_includes-makedestdirs() {
	local dest=$1
	shift
	local basedirs=$@

	dodir ${dest}

	local basedir
	for basedir in ${basedirs}; do
		local dir
		for dir in $(find ${D}/${basedir} -type d); do
			dodir ${dest}/${dir/${D}\/${basedir}/}
		done
	done
}

# Helper function for _create_abi_includes
_create_abi_includes-allfiles() {
	local basedir file
	for basedir in "$@" ; do
		for file in $(find "${D}"/${basedir} -type f); do
			echo ${file/${D}\/${basedir}\//}
		done
	done | sort | uniq
}

# Helper function for _create_abi_includes
_create_abi_includes-sym_for_dir() {
	local dir=$1
	shift
	local data
	for data in "$@"; do
		if [[ ${data} == *:${dir} ]] ; then
			echo ${data/:*/}
			return 0
		fi
	done
	echo "Shouldn't be here -- _create_abi_includes-sym_for_dir $1 $@"
	# exit because we'll likely be called from a subshell
	exit 1
}
