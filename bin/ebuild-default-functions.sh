#!/bin/bash
# ebuild-default-functions.sh; default functions for ebuild env that aren't saved- specific to the portage instance.
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
$Header$

has_version() {
	# if there is a predefined portageq call, use it.
	# why?  Because if we're being called from an ebuild daemon/processor, it can hijack the call, and access the
	# running portage instance already, saving at least .5s in load up of portageq.
	# time emerge -s mod_php w/out the hijack == 23s
	# time emerge -s mod_php w/ the hijack == < 6s
	local -i e
	[ "${EBUILD_PHASE}" == "depend" ] && echo "QA Notice: has_version() in global scope: ${CATEGORY}/$PF" >&2
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.

	if declare -F portageq &> /dev/null; then
		portageq 'has_version' "${ROOT}" "$1"
		e=$?
	else
		/usr/lib/portage/bin/portageq 'has_version' "${ROOT}" "$1"
		e=$?
	fi
	return $e
}

best_version() {
	local -i e
	if declare -F portageq &> /dev/null; then
		portageq 'best_version' "${ROOT}" "$1"
		e=$?
	else
		/usr/lib/portage/bin/portageq 'best_version' "${ROOT}" "$1"
		e=$?
	fi
	return $e
}

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

dyn_setup()
{
	if hasq setup ${COMPLETED_EBUILD_PHASES:-unset}; then
		echo ">>> looks like ${PF} has already been setup, bypassing."
		MUST_EXPORT_ENV="no"
		return
	fi
	MUST_EXPORT_ENV="yes"
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
	if hasq unpack ${COMPLETED_EBUILD_PHASES:-unset}; then
		echo ">>> ${PF} has alreay been unpacked, bypassing."
		MUST_EXPORT_ENV="no"
		return
	fi

	trap "abort_unpack" SIGINT SIGQUIT
	local newstuff="no"
	MUST_EXPORT_ENV="yes"
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
		elif ! hasq unpack ${COMPLETED_EBUILD_PHASES}; then
			echo ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		fi
	fi
	
	install -m0700 -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	[ -d "$WORKDIR" ] && cd "${WORKDIR}"
	echo ">>> Unpacking source..."
	src_unpack
	echo ">>> Source unpacked."
	cd "$BUILDDIR"
	trap SIGINT SIGQUIT
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
	exit 1
}

abort_unpack() {
	abort_handler "src_unpack" $1
	rm -rf "${BUILDDIR}/work"
	exit 1
}

abort_package() {
	abort_handler "dyn_package" $1
	rm -f "${PKGDIR}"/All/${PF}.t*
	exit 1
}

abort_test() {
	abort_handler "dyn_test" $1
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf "${BUILDDIR}/image"
	exit 1
}

dyn_compile() {
	if hasq compile ${COMPLETED_EBUILD_PHASES:-unset}; then
		echo ">>> It appears that ${PN} is already compiled; skipping."
		echo ">>> (clean to force compilation)"
		MUST_EXPORT_ENV="no"
		return
	fi

	MUST_EXPORT_ENV="yes"

	trap "abort_compile" SIGINT SIGQUIT
	[ "${CFLAGS-unset}"      != "unset" ] && export CFLAGS
	[ "${CXXFLAGS-unset}"    != "unset" ] && export CXXFLAGS
	[ "${LIBCFLAGS-unset}"   != "unset" ] && export LIBCFLAGS
	[ "${LIBCXXFLAGS-unset}" != "unset" ] && export LIBCXXFLAGS
	[ "${LDFLAGS-unset}"     != "unset" ] && export LDFLAGS
	[ "${ASFLAGS-unset}"     != "unset" ] && export ASFLAGS

	[ "${CCACHE_DIR-unset}"  != "unset" ] && export CCACHE_DIR
	[ "${CCACHE_SIZE-unset}" != "unset" ] && export CCACHE_SIZE

	[ "${DISTCC_DIR-unset}"  == "unset" ] && export DISTCC_DIR="${PORTAGE_TMPDIR}/.distcc"
	[ ! -z "${DISTCC_DIR}" ] && addwrite "${DISTCC_DIR}"

	if hasq noauto $FEATURES &>/dev/null && ! hasq unpack ${COMPLETED_EBUILD_PHASES:-unpack}; then
		echo
		echo "!!! We apparently haven't unpacked... This is probably not what you"
		echo "!!! want to be doing... You are using FEATURES=noauto so I'll assume"
		echo "!!! that you know what you are doing... You have 5 seconds to abort..."
		echo

		sleepbeep 16
		sleep 3
	fi

	cd "${BUILDDIR}"
	if [ ! -e "build-info" ];	then
		mkdir build-info
	fi
	cp "${EBUILD}" "build-info/${PF}.ebuild"
	
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
	cd build-info

	echo "$ASFLAGS"		> ASFLAGS
	echo "$CATEGORY"	> CATEGORY
	echo "$CBUILD"		> CBUILD
	echo "$CC"		> CC
	echo "$CDEPEND"		> CDEPEND
	echo "$CFLAGS"		> CFLAGS
	echo "$CHOST"		> CHOST
	echo "$CXX"		> CXX
	echo "$CXXFLAGS"	> CXXFLAGS
	echo "$DEPEND"		> DEPEND
	echo "$EXTRA_ECONF"	> EXTRA_ECONF
	echo "$FEATURES"	> FEATURES
	echo "$INHERITED"	> INHERITED
	echo "$IUSE"		> IUSE
	echo "$PKGUSE"		> PKGUSE
	echo "$LDFLAGS"		> LDFLAGS
	echo "$LIBCFLAGS"	> LIBCFLAGS
	echo "$LIBCXXFLAGS"	> LIBCXXFLAGS
	echo "$LICENSE"		> LICENSE
	echo "$PDEPEND"		> PDEPEND
	echo "$PF"		> PF
	echo "$PROVIDE"		> PROVIDE
	echo "$RDEPEND"		> RDEPEND
	echo "$RESTRICT"	> RESTRICT
	echo "$SLOT"		> SLOT
	echo "$USE"		> USE
	export_environ "${BUILDDIR}/build-info/environment.bz2" 'bzip2 -c9'
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
	echo ">>> Done."
	cd "${BUILDDIR}"
	MUST_EXPORT_ENV="yes"
	trap SIGINT SIGQUIT
}

dyn_test() {
	if hasq test ${COMPLETED_EBUILD_PHASES}; then
		echo ">>> TEST has already been run, skipping..." >&2
		MUST_EXPORT_ENV="no"
		return
	fi

	trap "abort_test" SIGINT SIGQUIT

	if hasq maketest $RESTRICT; then
		ewarn "Skipping make test/check due to ebiuld restriction."
		echo ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	elif ! hasq maketest $FEATURES; then
		echo ">>> Test phase [not enabled]; ${CATEGORY}/${PF}"
	else
		MUST_EXPORT_ENV="yes"
		if [ -d "${S}" ]; then
			cd "${S}"
		fi
		src_test
		cd "${BUILDDIR}"
	fi
	trap SIGINT SIGQUIT
}

function stat_perms() {
	local f
	f=$(stat -c '%f' "$1")
	f=$(printf %o ox$f)
	f="${f:${#f}-4}"
	echo $f
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
	
	if [ -x /usr/bin/readelf -a -x /usr/bin/file ]; then
		for x in $(find "${D}/" -type f \( -perm -04000 -o -perm -02000 \) ); do
			f=$(file "${x}")
			if [ -z "${f/*SB executable*/}" -o -z "${f/*SB shared object*/}" ]; then
				/usr/bin/readelf -d "${x}" | egrep '\(FLAGS(.*)NOW' > /dev/null
				if [ "$?" != "0" ]; then
					if [ ! -z "${f/*statically linked*/}" ]; then
						#uncomment this line out after developers have had ample time to fix pkgs.
						#UNSAFE=$(($UNSAFE + 1))
						echo -ne '\a'
						echo "QA Notice: ${x:${#D}:${#x}} is setXid, dynamically linked and using lazy bindings."
						echo "This combination is generally discouraged. Try: LDFLAGS='-Wl,-z,now' emerge ${PN}"
						echo -ne '\a'
						sleep 1
					fi
				fi
			fi
		done
	fi


	if [[ $UNSAFE > 0 ]]; then
		die "There are ${UNSAFE} unsafe files. Portage will not install them."
	fi

	local file s

	find "${D}/" -user  portage -print | while read file; do
		ewarn "file $file was installed with user portage!"
		s=$(stat_perms $file)
		chown root "$file"
		chmod "$s" "$file"
	done

	if [ "$USERLAND" == "BSD" ]; then
		find "${D}/" -group portage -print | while read file; do
			ewarn "file $file was installed with group portage!"
			s=$(stat_perms "$file")
			chgrp wheel "$file"
			chmod "%s" "$file"
		done
	else
		find "${D}/" -group portage -print | while read file; do
			ewarn "file $file was installed with group portage!"
			s=$(stat_perms "$file")
			chgrp root "$file"
			chmod "%s" "$file"
		done
	fi

	echo ">>> Completed installing into ${D}"
	echo
	cd ${BUILDDIR}
	MUST_EXPORT_ENV="yes"
	trap SIGINT SIGQUIT
}

dyn_postinst() {
	pkg_postinst
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

	# hopefully this will someday allow us to get rid of the no* feature flags
	# we don't want globbing for initial expansion, but afterwards, we do
	#rewrite this to use a while loop instead.
	local shopts=$-
	set -o noglob
	for no_inst in `echo "${INSTALL_MASK}"` ; do
		set +o noglob
		einfo "Removing ${no_inst}"
		# normal stuff
		rm -Rf ${IMAGE}/${no_inst} >&/dev/null
		# we also need to handle globs (*.a, *.h, etc)
		find "${IMAGE}" -name ${no_inst} -exec rm -fR {} \; >&/dev/null
	done
	# set everything back the way we found it
	set +o noglob
	set -${shopts}

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
					sleepbeep 6
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
	if hasq selinux $FEATURES || use selinux; then
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
	MUST_EXPORT_ENV="yes"
	trap SIGINT SIGQUIT
}

dyn_spec() {
#	tar czf "/usr/src/redhat/SOURCES/${PF}.tar.gz" "${O}/${PF}.ebuild" "${O}/files" || die "Failed to create base rpm tarball."
	tar czf "${T}/${PF}.tar.gz" "${O}/${PF}.ebuild" "${O}/files" || die "Failed to create base rpm tarball."
	echo "pwd=$(pwd)" >&2
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
	MUST_EXPORT_ENV="yes"

}

dyn_rpm() {
	dyn_spec
	MUST_EXPORT_ENV="yes"
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
	if hasq nostrip $FEATURES $RESTRICT;	then
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
	if [ "$EBUILD_PHASE" == "depend" ] && [ -z "${PORTAGE_DEBUG}" ]; then
		return
	fi
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
	local SAVED_INHERIT_COUNT=0 INHERITED_ALREADY=0

	if [[ $ECLASS_DEPTH < 0 ]] && [ "${EBUILD_PHASE}" == "depend" ]; then
		echo "QA Notice: ${CATEGORY}/${PF} makes multiple inherit calls: $1" >&2
		SAVED_INHERIT_COUNT=$ECLASS_DEPTH
		ECLASS_DEPTH=0
	fi
	if hasq $1 $INHERITED && [ "${EBUILD_PHASE}" == "depend" ]; then
		echo "QA notice: $1 is inherited multiple times: ${CATEGORY}/${PF}" >&2
		INHERITED_ALREADY=1
	fi
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ $ECLASS_DEPTH > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	local location olocation
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
				echo "QA Notice: ECLASS '$ECLASS' illegal conditional inherit in $CATEGORY/$PF" >&2
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
		if type -p eclass_${1}_inherit; then
			eclass_${1}_inherit
		else
			source "$location" || export ERRORMSG="died sourcing $location in inherit()"
		fi
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
		
		if hasq $1 $INHERITED && [ $INHERITED_ALREADY == 0 ]; then
#
# enable this one eclasses no longer full with eclass and inherited.
#			if [ "${EBUILD_PHASE}" == "depend" ]; then
#				echo "QA Notice: ${CATEGORY}/${PF}: eclass $1 is incorrectly setting \$INHERITED." >&2
#			fi
			:
		else
			INHERITED="$INHERITED $ECLASS"
		fi
		export ECLASS="$PECLASS"

		shift
	done
	ECLASS_DEPTH=$(($ECLASS_DEPTH - 1))
	if [[ $ECLASS_DEPTH == 0 ]]; then
		ECLASS_DEPTH=$(($SAVED_INHERIT_COUNT - 1)) 
	fi
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

QA_INTERCEPTORS="javac java-config python python-config perl grep egrep fgrep sed gcc g++ cc bash awk nawk pkg-config"
enable_qa_interceptors() {
	# QA INTERCEPTORS
	local FUNC_SRC BIN BODY BIN_PATH
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		FUNC_SRC="function ${BIN}() {
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
}

disable_qa_interceptors() {
	for x in $QA_INTERCEPTORS; do
		unset -f $x
	done
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

usev() {
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

# Used to generate the /lib/cpp and /usr/bin/cc wrappers
gen_wrapper() {
	cat > $1 << END
#!/bin/sh

$2 "\$@"
END

	chmod 0755 $1
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

true
