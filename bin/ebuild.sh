#!/bin/bash

if [ -n "$#" ]
then
	ARGS="${*}"	
fi

use() {
	local x xopts flag opts
	
	# Splice off the use flag and space-separate its options
	flag="${1%%:*}"
	if [ "$flag" != "$1" ]
	then
		opts="${1#*:}"
		opts="${opts//,/ }"
	else
		opts=
	fi
	
	for x in $USE
	do
		# If there are options specified, make sure all of them are on.
		if [ "${x%%:*}" == "$flag" ]
		then
			xopts="${x#*:}"
			xopts=" ${xopts//,/ } "
			for i in $opts
			do
				if [ "${xopts/ $i /}" == "${xopts}" ]
				then
					return 1
				fi
			done
			echo "$1"
			return 0
		fi
	done
	return 1
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
export KVERS=`uname -r`

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

#Add compiler cache support
if [ -d /usr/bin/ccache ]
then
	export PATH="/usr/bin/ccache:${PATH}"
	addread /root/.ccache
	addwrite /root/.ccache
fi

unpack() {
	local x
	for x in "$@"
	do
		echo ">>> Unpacking ${x}"
		case "${x##*.}" in
		tar)
			tar x --no-same-owner -f ${DISTDIR}/${x} || die
			;;
		gz|tgz|Z|z) 
			tar xz --no-same-owner -f ${DISTDIR}/${x} || die
			;;
		bz2|tbz2)
			cat ${DISTDIR}/${x} | bzip2 -d | tar x --no-same-owner -f - || die
			;;
		ZIP|zip)
			unzip ${DISTDIR}/${x} || die
			;;
		*)
			echo '!!!'" Error: couldn't unpack ${x}: file format not recognized"
			exit 1
			;;
		esac
	done
}

econf() {
    if [ -x ./configure ] ; then
	./configure \
	    --prefix=/usr \
	    --mandir=/usr/share/man \
	    --infodir=/usr/share/info \
	    --datadir=/usr/share \
	    --sysconfdir=/etc \
	    --localstatedir=/var/lib \
	    "$@" || return 1
    else
	return 1
    fi

    return
}

einstall() {
    if [ -f ./[mM]akefile ] ; then
	make prefix=${D}/usr \
	    mandir=${D}/usr/share/man \
	    infodir=${D}/usr/share/info \
	    datadir=${D}/usr/share \
	    sysconfdir=${D}/etc \
	    localstatedir=${D}/var/lib \
	    "$@" install || exit 1
    else
	exit 1
    fi

    return
}

pkg_setup()
{
    return 
}

src_unpack() { 
	unpack ${A} 
}

src_compile() { 
        if [ -x ./configure ] ; then
	        econf || return 1
		emake || return 1
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

dyn_touch() {
	local x
	for x in $AA 
	do
		if [ -e ${DISTDIR}/${x} ]
		then	
			touch ${DISTDIR}/${x}
		fi
	done
}

dyn_setup()
{
    pkg_setup 
}

dyn_unpack() {
	trap "abort_unpack" SIGINT SIGQUIT
	local newstuff="no"
	if [ -e ${WORKDIR} ]
	then
		local x
		local checkme
		for x in $AA
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
	cd ${WORKDIR}
	echo ">>> Unpacking source..."
	src_unpack
	echo ">>> Source unpacked."
	cd ..
    trap SIGINT SIGQUIT
}

dyn_clean() {
	if [ -d ${WORKDIR} ]
	then
		rm -rf ${WORKDIR} 
	fi
	if [ -d ${BUILDDIR}/image ]
	then
		rm -rf ${BUILDDIR}/image
	fi
	if [ -d ${BUILDDIR}/build-info ]
	then
		rm -rf ${BUILDDIR}/build-info
	fi
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
	if [ -n "$DEBUGBUILD" ] &&  [ "$x" = "-s" ]
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
	if [ -n "$DEBUGBUILD" ] &&  [ "$x" = "-s" ]
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
	if [ -n "$DEBUGBUILD" ] &&  [ "$x" = "-s" ]
	then
	    continue
        else
             LIBOPTIONS="$LIBOPTIONS $x"
        fi
    done
    export LIBOPTIONS
}

abort_compile() {
    echo 
    echo '*** Compilation Aborted ***'
    echo
    cd ${BUILDDIR} #original dir
    rm -f .compiled
    trap SIGINT SIGQUIT
    exit 1
}

abort_unpack() {
    echo 
    echo '*** Unpack Aborted ***'
    echo
    cd ${BUILDDIR} #original dir
    rm -f .unpacked
    rm -rf work
    trap SIGINT SIGQUIT
    exit 1
}

abort_package() {
    echo 
    echo '*** Packaging Aborted ***'
    echo
    cd ${BUILDDIR} #original dir
    rm -f .packaged
    rm -f ${PKGDIR}/All/${PF}.t*
    trap SIGINT SIGQUIT
    exit 1
}

abort_image() {
    echo 
    echo '*** Imaging Aborted ***'
    echo
    cd ${BUILDDIR} #original dir
    rm -rf image
    trap SIGINT SIGQUIT
    exit 1
}

dyn_compile() {
    trap "abort_compile" SIGINT SIGQUIT
    export CFLAGS CXXFLAGS LIBCFLAGS LIBCXXFLAGS
    if [ ${BUILDDIR}/.compiled -nt ${WORKDIR} ]
    then
		echo ">>> It appears that ${PN} is already compiled.  skipping."
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
    src_compile 
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
	ln -sf ${PKGDIR}/All/${PF}.tbz2 ${PKGDIR}/${CATEGORY}/${PF}.tbz2
    echo ">>> Done."
    cd ${BUILDDIR}
    touch .packaged
    trap SIGINT SIGQUIT
}

dyn_install() {
    local ROOT
    trap "abort_image" SIGINT SIGQUIT
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
	#some users have $TMPDIR to a custom dir in thier home ...            
	#this will cause sandbox errors with some ./configure            
	#scripts, so set it to $T.
	export TMPDIR="${T}"
	src_install
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

dyn_rpm () {
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
	echo "  check       : test if all dependencies get resolved"
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
	    echo "Additionally, support for the following toolkits will be enabled if necessary:"
	    echo 
	    echo "  ${USE}"
	fi    
	echo
}

#The following diefunc() and aliases come from Aron Griffis -- an excellent bash coder -- thanks! 

diefunc() {
	local funcname="$1" lineno="$2" exitcode="$3"
	shift 3
	echo >&2
	echo "!!! ERROR: The ebuild did not complete successfully." >&2
	echo "!!! Function $funcname, Line $lineno, Exitcode $exitcode" >&2
	echo "!!! ${*:-(no error message)}" >&2
	echo >&2
	exit 1
}

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_retval=$?; [ $_retval = 0 ] || diefunc "$FUNCNAME" "$LINENO" "$_retval"'

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

	while [ "$1" ]; do
	
		# extra user-configurable targets
		if [ "$ECLASS_DEBUG_OUTPUT" == "on" ]; then
			echo "debug: $1"
		elif [ -n "$ECLASS_DEBUG_OUTPUT" ]; then
	    	        echo "debug: $1" >> $ECLASS_DEBUG_OUTPUT
		fi
		
		# default target
		[ -d "$BUILD_PREFIX/$P/temp" ] && echo $1 >> ${T}/eclass-debug.log
		
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
    
    while [ "$1" ]; do
    
	# any future resolution code goes here
	local location
	location="${ECLASSDIR}/${1}.eclass"
	
	debug-print "inherit: $1 -> $location"
	
	source "$location" || die "died sourcing $location in inherit()"
	
	shift
	
    done

}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {

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
			    DEPEND="${DEPEND} sys-devel/gcc virtual/glibc sys-devel/ld.so"
			    RDEPEND="${RDEPEND} virtual/glibc sys-devel/ld.so"
			    ;;
		    *)
			    DEPEND="$DEPEND $1"
			    RDEPEND="$RDEPEND $1"
			    ;;
		esac
		shift
	done

}

# --- functions end, main part begins ---

source ${EBUILD} 
if [ $? -ne 0 ]
then
	#abort if there was a parse problem
	exit 1
fi
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
if [ -z "`set | grep ^RDEPEND=`" ]
then
	export RDEPEND=${DEPEND}
fi
set +f

for myarg in $ARGS
do
	case $myarg in
	prerm|postrm|preinst|postinst|config)
		if [ "$PORTAGE_DEBUG" = "0" ]
		then
		  pkg_${myarg}
		else
		  set -x
		  pkg_${myarg}
		  set +x
		fi
	    ;;
	# Only enable the SandBox for these functions
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
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		export SANDBOX_ON="0"
		;;
	help|touch|setup|pkginfo|pkgloc|unmerge|package|rpm)
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
		set -f
		#the extra `echo` commands remove newlines
		local dbkey
		dbkey=/var/cache/edb/dep/${CATEGORY}/${PF}
		if [ ! -d /var/cache/edb/dep/${CATEGORY} ]
		then
			install -d -g wheel -m2775 /var/cache/edb/dep/${CATEGORY}
		fi
		echo `echo "$DEPEND"` > $dbkey
		echo `echo "$RDEPEND"` >> $dbkey
		echo `echo "$SLOT"` >> $dbkey
		echo `echo "$SRC_URI"` >> $dbkey
		echo `echo "$RESTRICT"` >> $dbkey
		echo `echo "$HOMEPAGE"` >> $dbkey
		echo `echo "$LICENSE"` >> $dbkey
		echo `echo "$DESCRIPTION"` >> $dbkey
		echo `echo "$KEYWORDS"` >> $dbkey
		set +f
		#make sure it is writable by our group:
		chmod g+ws $dbkey
		exit 0
		;;
	*)
	    echo "Please specify a valid command."
		echo
		dyn_help
		;;
	esac
	if [ $? -ne 0 ]
	then
		exit 1
	fi
done

