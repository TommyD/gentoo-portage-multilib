#!/usr/bin/env python2.2
# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

import os,sys
from output import *

def shorthelp():
	print
	print
	print bold("Usage:")
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] [ "+turquoise("ebuildfile")+" | "+turquoise("tbz2file")+" | "+turquoise("dependency")+" ] [ ... ]"
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] < "+turquoise("system")+" | "+turquoise("world")+" >"
	print "   "+turquoise("emerge")+" < "+turquoise("sync")+" | "+turquoise("info")+" >"
	print "   "+turquoise("emerge")+" "+turquoise("--resume")+" ["+green("--pretend")+"]"
	print "   "+turquoise("emerge")+" "+turquoise("help")+" [ "+green("system")+" | "+green("config")+" | "+green("sync")+" ] "
	print bold("Options:")+" "+green("-")+"["+green("bcCdDefhikKlnoOpPsSuUvV")+"] ["+green("--oneshot")+"] ["+green("--noconfmem")+"]"
	print bold("Actions:")+" [ "+green("clean")+" | "+green("depclean")+" | "+green("inject")+" | "+green("prune")+" | "+green("regen")+" | "+green("search")+" | "+green("unmerge")+" ]"
	print

def help(myaction,myopts,havecolor=1):
	if not havecolor:
		nocolor()
	if not myaction and ("--help" not in myopts):
		shorthelp()
		print
		print "   For more help try 'emerge --help' or consult the man page."
		print
	elif not myaction:
		shorthelp()
		print
		print turquoise("Help (this screen):")
		print "       "+green("--help")+" ("+green("-h")+" short option)"
		print "              Displays this help; an additional argument (see above) will tell"
		print "              emerge to display detailed help."
		print
		print turquoise("Actions:")
		print "       "+green("clean")+" ("+green("-c")+" short option)"
		print "              Cleans the system by removing outdated packages which will not"
		print "              remove functionalities or prevent your system from working."
		print "              The arguments can be in several different formats :"
		print "              * world "
		print "              * system "
		print "              * /var/db/pkg/category/package-version, or"
		print "              * 'dependency specification' (in single quotes is best.)"
		print "              Here are a few examples of the dependency specification format:"
		print "              "+bold("binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.92.0.12.3-r1"
		print "              "+bold("sys-devel/binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.90.0.7"
		print "              "+bold(">sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">=sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("<sys-devel/binutils-2.11.92.0.12.3-r1")+" matches"
		print "                  binutils-2.11.90.0.7"
		print "              "+bold("<=sys-devel/binutils-2.11.92.0.12.3-r1")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print
		print "       "+green("depclean")
		print "              Cleans the system by removing packages that are not associated"
		print "              with explicitly merged packages. Depclean works by creating the"
		print "              full dependency tree from the system list and the world file,"
		print "              then comparing it to installed packages. Packages installed, but"
		print "              not associated with an explicit merge are listed as candidates"
		print "              for unmerging."+turquoise(" WARNING: This can seriously affect your system by")
		print "              "+turquoise("removing packages that may have been linked against, but due to")
		print "              "+turquoise("changes in USE flags may no longer be part of the dep tree. Use")
		print "              "+turquoise("caution when employing this feature.")
		print
		print "       "+green("info")
		print "              Displays important portage variables that will be exported to"
		print "              ebuild.sh when performing merges. This information is useful"
		print "              for bug reports and verification of settings. All settings in"
		print "              make.{conf,globals,defaults} and the environment show up if"
		print "              run with the '--verbose' flag."
		print
		print "       "+green("inject")+" ("+green("-i")+" short option)"
		print "              Add a stub entry for a package so that Portage thinks that it's"
		print "              installed when it really isn't.  Handy if you roll your own"
		print "              packages.  Example: "
		#NOTE: this next line *needs* the "sys-kernel/"; *please* don't remove it!
		print "              "+bold("emerge inject sys-kernel/gentoo-sources-2.4.19")
		print
		print "       "+green("prune")+" ("+green("-P")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all older versions of a package from your system."
		print "              This action doesn't always verify the possible binary"
		print "              incompatibility between versions and can thus remove essential"
		print "              dependencies from your system."
		print "              The argument format is the same as for the "+bold("clean")+" action."
		print
		print "       "+green("regen")
		print "              Causes portage to check and update the dependency cache of all"
		print "              ebuilds in the portage tree. This is not recommended for rsync"
		print "              users as rsync updates the cache using server-side caches."
		print "              Rsync users should simply 'emerge sync' to regenerate."
		print
		print "       "+green("search")+" ("+green("-s")+" short option)"
		print "              searches for matches of the supplied string in the current local"
		print "              portage tree. The search string is a regular expression."
		print "              A few examples: "
		print "              "+bold("emerge search '^kde'")
		print "                  list all packages starting with kde"
		print "              "+bold("emerge search 'gcc$'")
		print "                  list all packages ending with gcc"
		print "              "+bold("emerge search ''")+" or"
		print "              "+bold("emerge search '.*'")
		print "                  list all available packages "
		print
		print "       "+green("unmerge")+" ("+green("-C")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all matching packages without checking for outdated"
		print "              versions, effectively removing a package "+bold("completely")+" from"
		print "              your system. Specify arguments using the dependency specification"
		print "              format described in the "+bold("clean")+" action above."
		print
		print turquoise("Options:")
		print "       "+green("--buildpkg")+" ("+green("-b")+" short option)"
		print "              tell emerge to build binary packages for all ebuilds processed"
		print "              (in addition to actually merging the packages.  Useful for"
		print "              maintainers or if you administrate multiple Gentoo Linux"
		print "              systems (build once, emerge tbz2s everywhere)."
		print
		print "       "+green("--buildpkgonly")+" ("+green("-B")+" short option)"
		print "              Creates binary a binary package, but does not merge it to the"
		print "              system. This has the restriction that unsatisfied dependencies"
		print "              must not exist for the desired package as they cannot be used if"
		print "              they do not exist on the system."
		print
		print "       "+green("--changelog")+" ("+green("-l")+" short option)"
		print "              When pretending, also display the ChangeLog entries for packages"
		print "              that will be upgraded."
		print
		print "       "+green("--debug")+" ("+green("-d")+" short option)"
		print "              Tell emerge to run the ebuild command in --debug mode. In this"
		print "              mode, the bash build environment will run with the -x option,"
		print "              causing it to output verbose debug information print to stdout."
		print "              --debug is great for finding bash syntax errors."
		print
		print "       "+green("--deep")+" ("+green("-D")+" short option)"
		print "              When used in conjunction with --update, this flag forces emerge"
		print "              to consider the entire dependency tree of packages, instead of"
		print "              checking only the immediate dependencies of the packages.  As an"
		print "              example, this catches updates in libraries that are not directly"
		print "              listed in the dependencies of a package."
		print 
		print "       "+green("--emptytree")+" ("+green("-e")+" short option)"
		print "              Virtually tweaks the tree of installed packages to only contain"
		print "              glibc, this is great to use together with --pretend. This makes"
		print "              it possible for developers to get a complete overview of the"
		print "              complete dependency tree of a certain package."
		print
		print "       "+green("--fetchonly")+" ("+green("-f")+" short option)"
		print "              Instead of doing any package building, just perform fetches for"
		print "              all packages (main package as well as all dependencies.) When"
		print "              used in combination with --pretend all the SRC_URIs will be"
		print "              displayed multiple mirrors per line, one line per file."
		print
		print "       "+green("--noconfmem")
		print "              Portage keeps track of files that have been placed into"
		print "              CONFIG_PROTECT directories, and normally it will not merge the"
		print "              same file more than once, as that would become annoying. This"
		print "              can lead to problems when the user wants the file in the case"
		print "              of accidental deletion. With this option, files will always be"
		print "              merged to the live fs instead of silently dropped."
		print
		print "       "+green("--nodeps")+" ("+green("-O")+" short option)"
		print "              Merge specified packages, but don't merge any dependencies."
		print "              Note that the build may fail if deps aren't satisfied."
		print 
		print "       "+green("--noreplace")+" ("+green("-n")+" short option)"
		print "              Skip the packages specified on the command-line that have"
		print "              already been installed.  Without this option, any packages,"
		print "              ebuilds, or deps you specify on on the command-line *will* cause"
		print "              Portage to remerge the package, even if it is already installed."
		print "              Note that Portage won't remerge dependencies by default."
		print
		print "       "+green("--oneshot")
		print "              Emerge as normal, but don't add packages to the world profile for"
		print "              later updating. This prevents consideration of this package"
		print "              unless this package is depended upon by another package."
		print
		print "       "+green("--onlydeps")+" ("+green("-o")+" short option)"
		print "              Only merge (or pretend to merge) the dependencies of the"
		print "              specified packages, not the packages themselves."
		print
		print "       "+green("--pretend")+" ("+green("-p")+" short option)"
		print "              instead of actually performing the merge, simply display what"
		print "              ebuilds and tbz2s *would* have been installed if --pretend"
		print "              weren't used.  Using --pretend is strongly recommended before"
		print "              installing an unfamiliar package.  In the printout, N = new,"
		print "              U = updating, R = replacing, B = blocked by an already installed"
		print "              package, D = possible downgrading. --verbose causes affecting"
		print "              use flags to be printed out accompanied by a '+' for enabled"
		print "              and a '-' for disabled flags."
		print
		print "       "+green("--resume")
		print "              Resumes the last merge operation. Can be treated just like a"
		print "              regular merge as --pretend and other options work along side."
		print "              'emerge --resume' only returns an error on failure. Nothing to"
		print "              do exits with a message and a success condition."
		print
		print "       "+green("--searchdesc")+" ("+green("-S")+" short option)"
		print "              Matches the search string against the description field as well"
		print "              the package's name. Take caution as the descriptions are also"
		print "              matched as regular expressions."
		print "                emerge -S html"
		print "                emerge -S applet"
		print "                emerge -S 'perl.*module'"
		print
		print "       "+green("--update")+" ("+green("-u")+" short option)"
		print "              Updates packages to the best version available, which may not"
		print "              always be the highest version number due to masking for testing"
		print "              and development."
		print
		print "       "+green("--upgradeonly")+" ("+green("-U")+" short option)"
		print "              Updates packages, but excludes updates that would result in a"
		print "              lower version of the package being installed. SLOTs are"
		print "              considered at a basic level."
		print
		print "       "+green("--usepkg")+" ("+green("-k")+" short option)"
		print "              Tell emerge to use binary packages (from $PKGDIR) if they are"
		print "              available, thus possibly avoiding some time-consuming compiles."
		print "              This option is useful for CD installs; you can export"
		print "              PKGDIR=/mnt/cdrom/packages and then use this option to have"
		print "              emerge \"pull\" binary packages from the CD in order to satisfy" 
		print "              dependencies."
		print
		print "       "+green("--usepkgonly")+" ("+green("-K")+" short option)"
		print "              Like --usepkg above, except this only allows the use of binary"
		print "              packages, and it will abort the emerge if the package is not"
		print "              available at the time of dependency calculation."
		print
		print "       "+green("--verbose")+" ("+green("-v")+" short option)"
		print "              Tell emerge to run in verbose mode."
	elif myaction in ["rsync","sync"]:
		print
		print bold("Usage: ")+turquoise("emerge")+" "+turquoise("sync")
		print
		print "       'emerge sync' tells emerge to update the Portage tree as specified in"
		print "       The SYNC variable found in /etc/make.conf.  By default, SYNC instructs"
		print "       emerge to perform an rsync-style update with rsync.gentoo.org."
		#              Available"
		#print "       sync methods are rsync and anoncvs.  To use anoncvs rather than rsync,"
		#print "       put 'SYNC=\"cvs://:pserver:cvs.gentoo.org:/home/cvsroot\" in your"
		#print "       /etc/make.conf.  If you haven't used anoncvs before, you'll be prompted"
		#print "       for a password, which for cvs.gentoo.org is empty (just hit enter.)"
		print
		print "       'emerge-webrsync' exists as a helper app to emerge sync, providing a"
		print "       method to receive the entire portage tree as a tarball that can be"
		print "       extracted and used. First time syncs would benefit greatly from this."
		print
		print "       "+turquoise("WARNING:")
		print "       If using our rsync server, emerge will clean out all files that do not"
		print "       exist on it, including ones that you may have created."
		print
	elif myaction=="system":
		print
		print bold("Usage: ")+turquoise("emerge")+" [ "+green("options")+" ] "+turquoise("system")
		print
		print "       \"emerge system\" is the Portage system update command.  When run, it"
		print "       will scan the etc/make.profile/packages file and determine what"
		print "       packages need to be installed so that your system meets the minimum"
		print "       requirements of your current system profile.  Note that this doesn't"
		print "       necessarily bring your system up-to-date at all; instead, it just"
		print "       ensures that you have no missing parts.  For example, if your system"
		print "       profile specifies that you should have sys-apps/iptables installed"
		print "       and you don't, then \"emerge system\" will install it (the most"
		print "       recent version that matches the profile spec) for you.  It's always a"
		print "       good idea to do an \"emerge --pretend system\" before an \"emerge"
		print "       system\", just so you know what emerge is planning to do."
		print
	elif myaction=="config":
		outstuff=green("Config file management support (preliminary)")+"""

Portage has a special feature called "config file protection".  The purpose of
this feature is to prevent new package installs from clobbering existing
configuration files.  By default, config file protection is turned on for /etc
and the KDE configuration dirs; more may be added in the future.

When Portage installs a file into a protected directory tree like /etc, any
existing files will not be overwritten.  If a file of the same name already
exists, Portage will change the name of the to-be- installed file from 'foo' to
'._cfg0000_foo'.  If '._cfg0000_foo' already exists, this name becomes
'._cfg0001_foo', etc.  In this way, existing files are not overwritten,
allowing the administrator to manually merge the new config files and avoid any
unexpected changes.

In addition to protecting overwritten files, Portage will not delete any files
from a protected directory when a package is unmerged.  While this may be a
little bit untidy, it does prevent potentially valuable config files from being
deleted, which is of paramount importance.

Protected directories are set using the CONFIG_PROTECT variable, normally
defined in /etc/make.globals.  Directory exceptions to the CONFIG_PROTECTed
directories can be specified using the CONFIG_PROTECT_MASK variable.  To find
files that need to be updated in /etc, type:

# find /etc -iname '._cfg????_*'

You can disable this feature by setting CONFIG_PROTECT="-*" in /etc/make.conf.
Then, Portage will mercilessly auto-update your config files.  Alternatively,
you can leave Config File Protection on but tell Portage that it can overwrite
files in certain specific /etc subdirectories.  For example, if you wanted
Portage to automatically update your rc scripts and your wget configuration,
but didn't want any other changes made without your explicit approval, you'd
add this to /etc/make.conf:

CONFIG_PROTECT_MASK="/etc/wget /etc/rc.d"

etc-update is also available to aid in the merging of these files. It provides
a vimdiff interactive merging setup and can auto-merge trivial changes.

"""
		print outstuff

