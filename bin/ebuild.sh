#!/bin/bash 
# Copyright 1999-2002 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

cd ${PORT_TMPDIR}

if [ "$*" != "depend" ]; then
	if [ -f ${T}/successful ]; then
		rm -f ${T}/successful
	fi

	# Hurray for per-ebuild logging.
	if [ ! -z "${PORT_LOGDIR}" ]; then
		if [ -z "${PORT_LOGGING}" ]; then
			export PORT_LOGGING=1
			export SANDBOX_WRITE="$SANDBOX_WRITE:${PORT_LOGDIR}"
			install -d ${PORT_LOGDIR} &>/dev/null
			chown root:portage ${PORT_LOGDIR} &>/dev/null
			chmod g+rwxs ${PORT_LOGDIR} &> /dev/null
			touch "${PORT_LOGDIR}/$(date +%y%m%d)-${PF}.log" &> /dev/null
			chmod g+w "${PORT_LOGDIR}/$(date +%y%m%d)-${PF}.log" &> /dev/null
			$0 $* 2>&1 | tee -a "${PORT_LOGDIR}/$(date +%y%m%d)-${PF}.log"
			if [ "$?" != "0" ]; then
				echo "Problem creating logfile in ${PORT_LOGDIR}"
				exit 1
			fi
			if [ -f ${T}/successful ]; then
				exit 0
			else
				exit 1
			fi
		fi
	fi

	# Fix the temp dirs so we don't have booboos.
	for DIR in $(find ${BUILD_PREFIX} -type d -name temp -maxdepth 2 -mindepth 2 -print); do
		chown -R portage $DIR &>/dev/null
	done

	if [ -f "${WORKDIR}/environment" ]; then
		source "${WORKDIR}/environment"
	fi

	if [ `id -nu` == "portage" ] ; then
		export CCACHE_DIR=${HOME}/.ccache
		export USER=portage
	fi
fi # $*!=depend

# Prevent aliases from causing portage to act inappropriately.
unalias -a

if [ -n "$#" ]
then
	ARGS="${*}"
fi

use() {
	local x
	for x in ${USE}
	do
		if [ "${x}" = "${1}" ]
		then
			echo "${x}"
			return 0
		fi
	done
	return 1
}

has() {
	local x

	local me
	me=$1
	shift
	
	for x in $@
	do
		if [ "${x}" = "${me}" ]
		then
			echo "${x}"
			return 0
		fi
	done
	return 1
}

has_version() {
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	# XXX DO NOT ALIGN THIS -- PYTHON WILL NOT BE HAPPY XXX #
	if python -c "import portage,sys
mylist=portage.db[\"${ROOT}\"][\"vartree\"].dbapi.match(\"$1\")
if mylist:
	sys.exit(0)
else:
	sys.exit(1)
"; then
		return 0
	else
		return 1
	fi
}

best_version() {
	# returns the best/most-current match.
	# Takes single depend-type atoms.
	# XXX DO NOT ALIGN THIS -- PYTHON WILL NOT BE HAPPY XXX #
	echo $(python -c "import portage
mylist=portage.db[\"${ROOT}\"][\"vartree\"].dbapi.match(\"$1\")
print portage.best(mylist)
")
}

use_with() {
	if [ -z "$1" ]; then
		die "use_with() called without parameter."
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if use $1 &>/dev/null; then
		echo "--with-${UWORD}"
		return 0
	else
		echo "--without-${UWORD}"
		return 1
	fi
}

use_enable() {
	if [ -z "$1" ]; then
		die "use_with() called without parameter."
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if use $1 &>/dev/null; then
		echo "--enable-${UWORD}"
		return 0
	else
		echo "--disable-${UWORD}"
		return 1
	fi
}

#we need this next line for "die" and "assert"
shopt -s expand_aliases
source /etc/profile.env > /dev/null 2>&1
export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin:${ROOTPATH}"
if [ -e /etc/init.d/functions.sh ]
then
	source /etc/init.d/functions.sh > /dev/null 2>&1
elif [ -e /etc/rc.d/config/functions ]
then
	source /etc/rc.d/config/functions > /dev/null 2>&1
fi

# Custom version of esyslog() to take care of the "Red Star" bug
# if no logger is running (tipically during bootstrap)
esyslog() {
	return 0
}

#The following diefunc() and aliases come from Aron Griffis -- an excellent bash coder -- thanks! 

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

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_retval=$?; [ $_retval = 0 ] || diefunc "$FUNCNAME" "$LINENO" "$_retval"'

# don't need to handle the maintainer fine grained settings here
# anymore since it's initialized by ebuild through the python
# portage module
	
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
#Moved to portage
#export KVERS=`uname -r`

check_KV()
{
	if [ x"${KV}" = x ]
	then
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
	dodir $*
	local x
	for x in $*
	do
		[ ! -e ${D}/${x}/.keep -o -w ${D}/${x}/.keep ] && touch ${D}/${x}/.keep
	done
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

if [ "${FEATURES/-ccache/}" = "${FEATURES}" -a "${FEATURES/ccache/}" != "${FEATURES}" -a -d /usr/bin/ccache ]
then
	#We can enable compiler cache support
	export PATH="/usr/bin/ccache:${PATH}"
	if [ -z "${CCACHE_DIR}" ]
	then
		CCACHE_DIR=/root/.ccache
	fi
	addread ${CCACHE_DIR}
	addwrite ${CCACHE_DIR}
fi

unpack() {
	local x
	local y
	local myfail
	
	for x in $@
	do
		myfail="failure unpacking ${x}"
		echo ">>> Unpacking ${x}"
		y="$(echo $x | sed 's:.*\.\(tar\)\.[a-zA-Z0-9]*:\1:')"
		case "${x##*.}" in
		tar) 
			tar x --no-same-owner -f ${DISTDIR}/${x} || die "$myfail"
			;;
		tgz) 
			tar xz --no-same-owner -f ${DISTDIR}/${x} || die "$myfail"
			;;
		tbz2) 
			tar xj --no-same-owner -f ${DISTDIR}/${x} || die "$myfail"
			;;
		ZIP|zip) 
			unzip -qo ${DISTDIR}/${x} || die "$myfail"
			;;
		gz|Z|z) 
			if [ "${y}" == "tar" ]; then
				tar xz --no-same-owner -f ${DISTDIR}/${x} || die "$myfail"
			else
				gzip -dc ${DISTDIR}/${x} > ${x%.*} || die "$myfail"
			fi
			;;
		bz2) 
			if [ "${y}" == "tar" ]; then
				tar xj --no-same-owner -f ${DISTDIR}/${x} || die "$myfail"
			else
				bzip2 -dc ${DISTDIR}/${x} > ${x%.*} || die "$myfail"
			fi
			;;
		*)
			echo "unpack ${x}: file format not recognized. Ignoring."
			;;
		esac
	done
}

econf() {
	if [ -x ./configure ] ; then
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
		make prefix=${D}/usr \
		    mandir=${D}/usr/share/man \
		    infodir=${D}/usr/share/info \
		    datadir=${D}/usr/share \
		    sysconfdir=${D}/etc \
		    localstatedir=${D}/var/lib \
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
	return 
}

src_unpack() { 
	if [ "${A}" != "" ]
	then
		unpack ${A}
	fi	
}

src_compile() { 
	if [ -x ./configure ] ; then
		econf 
		emake || die "emake failed"
	fi
	return 
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

try() {
	env "$@"
	if [ $? -ne 0 ]
	then
		echo 
		echo '!!! '"ERROR: the $1 command did not complete successfully."
		echo '!!! '"(\"$*\")"
		echo '!!! '"Since this is a critical task, ebuild will be stopped."
		echo
		exit 1
	fi
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
	# The next bit is to easy the broken pkg_postrm()'s
	# some of the gcc ebuilds have that nuke the new
	# /lib/cpp and /usr/bin/cc wrappers ...
	
	# Make sure we can have it disabled somehow ....
	if [ "${DISABLE_GEN_GCC_WRAPPERS}" != "yes" ]
	then
		# Create /lib/cpp if missing or a symlink
		if [ -L /lib/cpp -o ! -e /lib/cpp ]
		then
			[ -L /lib/cpp ] && rm -f /lib/cpp
			gen_wrapper /lib/cpp cpp
		fi
		# Create /usr/bin/cc if missing for a symlink
		if [ -L /usr/bin/cc -o ! -e /usr/bin/cc ]
		then
			[ -L /usr/bin/cc ] && rm -f /usr/bin/cc
			gen_wrapper /usr/bin/cc gcc
		fi
	fi

	pkg_setup || die "pkg_setup function failed; exiting."
}

dyn_unpack() {
	trap "abort_unpack" SIGINT SIGQUIT
	local newstuff="no"
	if [ -e ${WORKDIR} ]
	then
		local x
		local checkme
		for x in ${AA}
		do
			echo ">>> Checking ${x}'s mtime..."
			if [ ${DISTDIR}/${x} -nt ${WORKDIR} ]
			then
				echo ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				rm -rf ${WORKDIR}
				break
			fi
		done
		if [ ${EBUILD} -nt ${WORKDIR} ]
		then
			echo ">>> ${EBUILD} has been updated; recreating WORKDIR..."
			newstuff="yes"
			rm -rf ${WORKDIR}
		fi
	fi
	if [ -e ${WORKDIR} ]
	then
		if [ "$newstuff" = "no" ]
		then
			echo ">>> WORKDIR is up-to-date, keeping..."
			return 0
		fi
	fi
	install -m0700 -d ${WORKDIR}
	[ -d "$WORKDIR" ] && cd ${WORKDIR}
	echo ">>> Unpacking source..."
	src_unpack
	#|| abort_unpack "fail"
	echo ">>> Source unpacked."
	cd $BUILDDIR
	trap SIGINT SIGQUIT
}

dyn_clean() {
	rm -rf ${WORKDIR} 
	rm -rf ${BUILDDIR}/image
	rm -rf ${BUILDDIR}/build-info
	rm -rf ${BUILDDIR}/.compiled
}

into() {
	if [ $1 = "/" ]
	then
		export DESTTREE=""
	else
		export DESTTREE=$1
		if [ ! -d ${D}${DESTTREE} ]
		then
			install -d ${D}${DESTTREE}
		fi
	fi
}

insinto() {
	if [ $1 = "/" ]
	then
		export INSDESTTREE=""
	else
		export INSDESTTREE=$1
		if [ ! -d ${D}${INSDESTTREE} ]
		then
			install -d ${D}${INSDESTTREE}
		fi
	fi
}

exeinto() {
	if [ $1 = "/" ]
	then
		export EXEDESTTREE=""
	else
		export EXEDESTTREE=$1
		if [ ! -d ${D}${EXEDESTTREE} ]
		then
			install -d ${D}${EXEDESTTREE}
		fi
	fi
}

docinto() {
	if [ $1 = "/" ]
	then
		export DOCDESTTREE=""
	else
		export DOCDESTTREE=$1
		if [ ! -d ${D}usr/share/doc/${PF}/${DOCDESTTREE} ]
		then
			install -d ${D}usr/share/doc/${PF}/${DOCDESTTREE} 
		fi
	fi
}

insopts() {
	INSOPTIONS=""
	for x in $*
	do
		#if we have a debug build, let's not strip anything
		if [ -n "$DEBUGBUILD" ] && [ "$x" = "-s" ]
		then
			continue
 		else
			INSOPTIONS="$INSOPTIONS $x"
	fi
	done
	export INSOPTIONS
}

diropts() {
	DIROPTIONS=""
	for x in $*
	do
		DIROPTIONS="${DIROPTIONS} $x"
	done
	export DIROPTIONS
}

exeopts() {
	EXEOPTIONS=""
	for x in $*
	do
		#if we have a debug build, let's not strip anything
		if [ -n "$DEBUGBUILD" ] && [ "$x" = "-s" ]
		then
			continue
		else
			EXEOPTIONS="$EXEOPTIONS $x"
		fi
	done
	export EXEOPTIONS
}

libopts() {
	LIBOPTIONS=""
	for x in $*
	do
		#if we have a debug build, let's not strip anything
		if [ -n "$DEBUGBUILD" ] && [ "$x" = "-s" ]
		then
			continue
		else
			LIBOPTIONS="$LIBOPTIONS $x"
		fi
	done
	export LIBOPTIONS
}

abort_handler() {
	local msg
	if [ "$2" != "fail" ]
	then
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
	rm -f ${BUILDDIR}/compiled
	exit 1
}

abort_unpack() {
	abort_handler "src_unpack" $1
	rm -f ${BUILDDIR}/.unpacked
	rm -rf ${BUILDDIR}/work
	exit 1
}

abort_package() {
	abort_handler "dyn_package" $1
	rm -f ${BUILDDIR}/.packaged
	rm -f ${PKGDIR}/All/${PF}.t*
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf ${BUILDDIR}/image
	exit 1
}

dyn_compile() {
	trap "abort_compile" SIGINT SIGQUIT
	export CFLAGS CXXFLAGS LIBCFLAGS LIBCXXFLAGS
	if [ ${BUILDDIR}/.compiled -nt ${WORKDIR} ]
	then
		echo ">>> It appears that ${PN} is already compiled; skipping."
		echo ">>> (clean to force compilation)"
		trap SIGINT SIGQUIT
		return
	fi
	if [ -d ${S} ]
		then
		cd ${S}
	fi
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages use an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	#some users have $TMP/$TMPDIR to a custom dir in their home ...
	#this will cause sandbox errors with some ./configure
	#scripts, so set it to $T.
	export TMP="${T}"
	export TMPDIR="${T}"
	src_compile 
	#|| abort_compile "fail" 
	cd ${BUILDDIR}
	touch .compiled
	if [ ! -e "build-info" ]
	then
		mkdir build-info
	fi
	cd build-info
	echo "$CFLAGS" > CFLAGS
	echo "$CXXFLAGS" > CXXFLAGS
	echo "$CHOST" > CHOST
	echo "$USE" > USE
	echo "$LICENSE" > LICENSE
	echo "$CATEGORY" > CATEGORY
	echo "$PF" > PF
	echo "$SLOT" > SLOT
	echo "$RDEPEND" > RDEPEND
	echo "$CDEPEND" > CDEPEND
	echo "$PDEPEND" > PDEPEND
	echo "$PROVIDE" > PROVIDE
	cp ${EBUILD} ${PF}.ebuild
	if [ -n "$DEBUGBUILD" ]
	then
		touch DEBUGBUILD
	fi
	trap SIGINT SIGQUIT
}

dyn_package() {
	trap "abort_package" SIGINT SIGQUIT
	cd ${BUILDDIR}/image
	tar cvf ../bin.tar *
	cd ..
	bzip2 -f bin.tar
	xpak build-info inf.xpak
	tbz2tool join bin.tar.bz2 inf.xpak ${PF}.tbz2
	mv ${PF}.tbz2 ${PKGDIR}/All
	rm -f inf.xpak bin.tar.bz2
	if [ ! -d ${PKGDIR}/${CATEGORY} ]
	then
		install -d ${PKGDIR}/${CATEGORY}
	fi
	ln -sf ../All/${PF}.tbz2 ${PKGDIR}/${CATEGORY}/${PF}.tbz2
	echo ">>> Done."
	cd ${BUILDDIR}
	touch .packaged
	trap SIGINT SIGQUIT
}

dyn_install() {
	local ROOT
	trap "abort_install" SIGINT SIGQUIT
	rm -rf ${BUILDDIR}/image
	mkdir ${BUILDDIR}/image
	if [ -d ${S} ]
	then
		cd ${S}
	fi
	echo
	echo ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	#some users have $TMP/$TMPDIR to a custom dir in thier home ...
	#this will cause sandbox errors with some ./configure
	#scripts, so set it to $T.
	export TMP="${T}"
	export TMPDIR="${T}"
	src_install 
	#|| abort_install "fail"
	prepall
	cd ${D}
	echo ">>> Completed installing into ${D}"
	echo
	cd ${BUILDDIR}
	trap SIGINT SIGQUIT
}

dyn_spec() {
	tar czf /usr/src/redhat/SOURCES/${PF}.tar.gz ${O}/${PF}.ebuild ${O}/files

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
	rpm -bb ${PF}.spec
	install -D /usr/src/redhat/RPMS/i386/${PN}-${PV}-${PR}.i386.rpm ${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm
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
	if [ -n "${DEBUGBUILD}" ]
	then
		echo "debug (large)"
	else
		echo "production (stripped)"
	fi
	echo "  merge to    : ${ROOT}" 
	echo
	if [ -n "$USE" ]
	then
		echo "Additionally, support for the following optional features will be enabled:"
		echo 
		echo "  ${USE}"
	fi
	echo
}

# --- Former eclass code ---

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
		[ -n "$T" ] && echo $1 >> ${T}/eclass-debug.log
		# let the portage user own/write to this file
		[ -n "$T" ] && chown portage.portage ${T}/eclass-debug.log
		
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
inherit() {
	unset INHERITED
	local location
	while [ "$1" ]
	do
		export INHERITED="$INHERITED $1"

		# any future resolution code goes here
		if [ -n "$PORTDIR_OVERLAY" ]
		then
			location="${PORTDIR_OVERLAY}/eclass/${1}.eclass"
			if [ -e "$location" ]
			then
				debug-print "inherit: $1 -> $location"
				source "$location" || die "died sourcing $location in inherit()"
				#continue processing, skip sourcing of one in $ECLASSDIR
				shift
				continue
			fi
		fi
			
		location="${ECLASSDIR}/${1}.eclass"
		debug-print "inherit: $1 -> $location"
		PECLASS="$ECLASS"
		export ECLASS="$1"
		source "$location" || die "died sourcing $location in inherit()"
		ECLASS="$PECLASS"
		unset PECLASS

		shift
	done
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -n "$ECLASS" ]; then
		echo "EXPORT_FUNCTIONS without a defined ECLASS" >&2
		exit 1
	fi
	while [ "$1" ]; do
		debug-print "EXPORT_FUNCTIONS: ${1} -> ${ECLASS}_${1}" 
		eval "$1() { ${ECLASS}_$1 ; }" > /dev/null
		shift
	done
}

# adds all parameters to DEPEND and RDEPEND
newdepend() {
	debug-print-function newdepend $*
	debug-print "newdepend: DEPEND=$DEPEND RDEPEND=$RDEPEND"

	while [ -n "$1" ]; do
		case $1 in
		"/autotools")
			DEPEND="${DEPEND} sys-devel/autoconf sys-devel/automake sys-devel/make"
			;;
		"/c")
			DEPEND="${DEPEND} sys-devel/gcc virtual/glibc"
			RDEPEND="${RDEPEND} virtual/glibc"
			;;
		*)
			DEPEND="$DEPEND $1"
			if [ -z "$RDEPEND" ] && [ "${RDEPEND-unset}" == "unset" ]; then
				export RDEPEND="$DEPEND"
			fi
			RDEPEND="$RDEPEND $1"
			;;
		esac
		shift
	done
}

# --- functions end, main part begins ---
export SANDBOX_ON="1"
source ${EBUILD} || die "error sourcing ebuild"
#a reasonable default for $S
if [ "$S" = "" ]
then
	S=${WORKDIR}/${P}
fi
if [ "${RESTRICT/nostrip/}" != "${RESTRICT}" ]
then
	export DEBUGBUILD="yes"
fi

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
set +f

for myarg in $*
do
	case $myarg in
	nofetch)
		pkg_nofetch
		;;
	prerm|postrm|preinst|postinst|config)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" = "0" ]
		then
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
		if [ ${SANDBOX_DISABLED="0"} = "0" ]
		then
			export SANDBOX_ON="1"
		else
			export SANDBOX_ON="0"
		fi
		if [ "$PORTAGE_DEBUG" = "0" ]
		then
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
	help|clean|setup)
		#pkg_setup needs to be out of the sandbox for tmp file creation;
		#for example, awking and piping a file in /tmp requires a temp file to be created
		#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" = "0" ]; then
			dyn_${myarg}
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		;;
	package|rpm)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" = "0" ]
		then
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
		if [ ! -d ${PORTAGE_CACHEDIR}/${CATEGORY} ]
		then
			install -d -g wheel -m2775 ${PORTAGE_CACHEDIR}/${CATEGORY}
		fi
		# Make it group writable. 666&~002==664
		umask 002
		echo `echo "$DEPEND"` > $dbkey
		echo `echo "$RDEPEND"` >> $dbkey
		echo `echo "$SLOT"` >> $dbkey
		echo `echo "$SRC_URI"` >> $dbkey
		echo `echo "$RESTRICT"` >> $dbkey
		echo `echo "$HOMEPAGE"` >> $dbkey
		echo `echo "$LICENSE"` >> $dbkey
		echo `echo "$DESCRIPTION"` >> $dbkey
		echo `echo "$KEYWORDS"` >> $dbkey
		echo `echo "$INHERITED"` >> $dbkey
		echo `echo "$IUSE"` >> $dbkey
		echo `echo "$CDEPEND"` >> $dbkey
		echo `echo "$PDEPEND"` >> $dbkey
		set +f
		#make sure it is writable by our group:
		#chmod g+ws $dbkey
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
	if [ $? -ne 0 ]
	then
		exit 1
	fi
done

# Save current environment and touch a success file. (echo for success)
umask 002
set > ${T}/environment 2>/dev/null
touch ${T}/successful 2>/dev/null
#chmod g+w ${T}/environment ${T}/successful &>/dev/null
echo -n ""
