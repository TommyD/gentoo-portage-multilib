# Copyright 1999-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


import os,sys
from portage.output import bold, turquoise, green

def shorthelp():
	print bold("emerge:")+" the other white meat (command-line interface to the Portage system)"
	print bold("Usage:")
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] [ "+turquoise("ebuild")+" | "+turquoise("tbz2")+" | "+turquoise("file")+" | "+turquoise("@set")+" | "+turquoise("atom")+" ] [ ... ]"
	print "   "+turquoise("emerge")+" [ "+green("options")+" ] [ "+green("action")+" ] < "+turquoise("system")+" | "+turquoise("world")+" >"
	print "   "+turquoise("emerge")+" < "+turquoise("--sync")+" | "+turquoise("--metadata")+" | "+turquoise("--info")+" >"
	print "   "+turquoise("emerge")+" "+turquoise("--resume")+" [ "+green("--pretend")+" | "+green("--ask")+" | "+green("--skipfirst")+" ]"
	print "   "+turquoise("emerge")+" "+turquoise("--help")+" [ "+green("system")+" | "+green("world")+" | "+green("--sync")+" ] "
	print bold("Options:")+" "+green("-")+"["+green("abBcCdDefgGhkKlnNoOpqPsStuvV")+"]"
	print "          [ " + green("--color")+" < " + turquoise("y") + " | "+ turquoise("n")+" >            ] [ "+green("--columns")+"    ]"
	print "          [ "+green("--complete-graph")+"             ] [ "+green("--deep")+"       ]"
	print "          [ "+green("--jobs") + " " + turquoise("JOBS")+" ] [ "+green("--keep-going")+" ] [ " + green("--load-average")+" " + turquoise("LOAD") + "            ]"
	print "          [ "+green("--newuse")+"    ] [ "+green("--noconfmem")+"  ] [ "+green("--nospinner")+"  ] [ "+green("--oneshot")+"     ]"
	print "          [ "+green("--reinstall ")+turquoise("changed-use")+"      ] [ " + green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >         ]"
	print bold("Actions:")+"  [ "+green("--clean")+" | "+green("--depclean")+" | "+green("--prune")+" | "+green("--regen")+" | "+green("--search")+" | "+green("--unmerge")+" ]"

def help(myaction,myopts,havecolor=1):
	# TODO: Implement a wrap() that accounts for console color escape codes.
	from textwrap import wrap
	desc_left_margin = 14
	desc_indent = desc_left_margin * " "
	desc_width = 80 - desc_left_margin - 5
	if not myaction and ("--verbose" not in myopts):
		shorthelp()
		print
		print "   For more help try 'emerge --help --verbose' or consult the man page."
	elif not myaction:
		shorthelp()
		print
		print turquoise("Help (this screen):")
		print "       "+green("--help")+" ("+green("-h")+" short option)"
		print "              Displays this help; an additional argument (see above) will tell"
		print "              emerge to display detailed help."
		print
		print turquoise("Actions:")
		print "       "+green("--clean")+" ("+green("-c")+" short option)"
		print "              Cleans the system by removing outdated packages which will not"
		print "              remove functionalities or prevent your system from working."
		print "              The arguments can be in several different formats :"
		print "              * world "
		print "              * system or"
		print "              * 'dependency specification' (in single quotes is best.)"
		print "              Here are a few examples of the dependency specification format:"
		print "              "+bold("binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("sys-devel/binutils")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.92.0.12.3-r1"
		print "              "+bold(">=sys-devel/binutils-2.11.90.0.7")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print "              "+bold("<=sys-devel/binutils-2.11.92.0.12.3-r1")+" matches"
		print "                  binutils-2.11.90.0.7 and binutils-2.11.92.0.12.3-r1"
		print
		print "       "+green("--config")
		print "              Runs package-specific operations that must be executed after an"
		print "              emerge process has completed.  This usually entails configuration"
		print "              file setup or other similar setups that the user may wish to run."
		print
		print "       "+green("--depclean")
		paragraph = "Cleans the system by removing packages that are not associated " + \
			"with explicitly merged packages. Depclean works by creating the " + \
			"full dependency tree from the system and world sets, " + \
			"then comparing it to installed packages. Packages installed, but " + \
			"not part of the dependency tree, will be uninstalled by depclean. " + \
			"Inexperienced users are advised to use --pretend " + \
			"with this option in order to see a preview of which packages " + \
			"will be uninstalled."
		for line in wrap(paragraph, desc_width):
			print desc_indent + line
		print

		paragraph =  "WARNING: Removing some " + \
			"packages may cause packages which link to the removed package  " + \
			"to stop working and complain about missing libraries. " + \
			"Rebuild the complaining package to fix this issue.  Also see " + \
			"--with-bdeps for behavior with respect to build time dependencies that " + \
			"are not strictly required. Note that packages listed in " + \
			"package.provided (see portage(5)) may be removed by " + \
			"depclean, even if they are part of the world set."
		for line in wrap(paragraph, desc_width):
			print desc_indent + line
		print

		paragraph = "Depclean serves as a dependency aware " + \
			"version of --unmerge. When given one or more atoms, it will " + \
			"unmerge matched packages that have no reverse dependencies. Use " + \
			"--depclean together with --verbose to show reverse " + \
			"dependencies."
		for line in wrap(paragraph, desc_width):
			print desc_indent + line
		print
		print "       "+green("--info")
		print "              Displays important portage variables that will be exported to"
		print "              ebuild.sh when performing merges. This information is useful"
		print "              for bug reports and verification of settings. All settings in"
		print "              make.{conf,globals,defaults} and the environment show up if"
		print "              run with the '--verbose' flag."
		print
		print "       "+green("--metadata")
		print "              Transfers metadata cache from ${PORTDIR}/metadata/cache/ to"
		print "              /var/cache/edb/dep/ as is normally done on the tail end of an"
		print "              rsync update using " + bold("emerge --sync") + ". This process populates the"
		print "              cache database that portage uses for pre-parsed lookups of"
		print "              package data.  It does not populate cache for the overlays"
		print "              listed in PORTDIR_OVERLAY.  In order to generate cache for"
		print "              overlays, use " + bold("--regen") + "."
		print
		print "       "+green("--prune")+" ("+green("-P")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all but the highest installed version of a package"
		print "              from your system. This action doesn't verify the possible binary"
		print "              compatibility between versions and can thus remove essential"
		print "              dependencies from your system. Use --prune together with"
		print "              --verbose to show reverse dependencies or with --nodeps to"
		print "              ignore all dependencies."
		print
		print "       "+green("--regen")
		print "              Causes portage to check and update the dependency cache of all"
		print "              ebuilds in the portage tree. This is not recommended for rsync"
		print "              users as rsync updates the cache using server-side caches."
		print "              Rsync users should simply 'emerge --sync' to regenerate."
		desc = "In order to specify parallel --regen behavior, use "+ \
			"the ---jobs and --load-average options."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--resume")
		print "              Resumes the most recent merge list that has been aborted due to an"
		print "              error. Please note that this operation will only return an error"
		print "              on failure. If there is nothing for portage to do, then portage"
		print "              will exit with a message and a success condition. A resume list"
		print "              will persist until it has been completed in entirety or until"
		print "              another aborted merge list replaces it. The resume history is"
		print "              capable of storing two merge lists. After one resume list"
		print "              completes, it is possible to invoke --resume once again in order"
		print "              to resume an older list."
		print
		print "       "+green("--search")+" ("+green("-s")+" short option)"
		print "              Searches for matches of the supplied string in the current local"
		print "              portage tree. By default emerge uses a case-insensitive simple "
		print "              search, but you can enable a regular expression search by "
		print "              prefixing the search string with %."
		print "              Prepending the expression with a '@' will cause the category to"
		print "              be included in the search."
		print "              A few examples:"
		print "              "+bold("emerge --search libc")
		print "                  list all packages that contain libc in their name"
		print "              "+bold("emerge --search '%^kde'")
		print "                  list all packages starting with kde"
		print "              "+bold("emerge --search '%gcc$'")
		print "                  list all packages ending with gcc"
		print "              "+bold("emerge --search '%@^dev-java.*jdk'")
		print "                  list all available Java JDKs"
		print
		print "       "+green("--searchdesc")+" ("+green("-S")+" short option)"
		print "              Matches the search string against the description field as well"
		print "              the package's name. Take caution as the descriptions are also"
		print "              matched as regular expressions."
		print "                emerge -S html"
		print "                emerge -S applet"
		print "                emerge -S 'perl.*module'"
		print
		print "       "+green("--unmerge")+" ("+green("-C")+" short option)"
		print "              "+turquoise("WARNING: This action can remove important packages!")
		print "              Removes all matching packages. This does no checking of"
		print "              dependencies, so it may remove packages necessary for the proper"
		print "              operation of your system. Its arguments can be atoms or"
		print "              ebuilds. For a dependency aware version of --unmerge, use"
		print "              --depclean or --prune."
		print
		print "       "+green("--update")+" ("+green("-u")+" short option)"
		print "              Updates packages to the best version available, which may not"
		print "              always be the highest version number due to masking for testing"
		print "              and development. This will also update direct dependencies which"
		print "              may not what you want. Package atoms specified on the command line"
		print "              are greedy, meaning that unspecific atoms may match multiple"
		print "              installed versions of slotted packages."
		print
		print "       "+green("--version")+" ("+green("-V")+" short option)"
		print "              Displays the currently installed version of portage along with"
		print "              other information useful for quick reference on a system. See"
		print "              "+bold("emerge info")+" for more advanced information."
		print
		print turquoise("Options:")
		print "       "+green("--alphabetical")
		print "              When displaying USE and other flag output, combines the enabled"
		print "              and disabled flags into a single list and sorts it alphabetically."
		print "              With this option, output such as USE=\"dar -bar -foo\" will instead"
		print "              be displayed as USE=\"-bar dar -foo\""
		print
		print "       "+green("--ask")+" ("+green("-a")+" short option)"
		print "              before performing the merge, display what ebuilds and tbz2s will"
		print "              be installed, in the same format as when using --pretend; then"
		print "              ask whether to continue with the merge or abort. Using --ask is"
		print "              more efficient than using --pretend and then executing the same"
		print "              command without --pretend, as dependencies will only need to be"
		print "              calculated once. WARNING: If the \"Enter\" key is pressed at the"
		print "              prompt (with no other input), it is interpreted as acceptance of"
		print "              the first choice.  Note that the input buffer is not cleared prior"
		print "              to the prompt, so an accidental press of the \"Enter\" key at any"
		print "              time prior to the prompt will be interpreted as a choice!"
		print
		print "       "+green("--buildpkg")+" ("+green("-b")+" short option)"
		desc = "Tells emerge to build binary packages for all ebuilds processed in" + \
			" addition to actually merging the packages. Useful for maintainers" + \
			" or if you administrate multiple Gentoo Linux systems (build once," + \
			" emerge tbz2s everywhere) as well as disaster recovery. The package" + \
			" will be created in the" + \
			" ${PKGDIR}/All directory. An alternative for already-merged" + \
			" packages is to use quickpkg(1) which creates a tbz2 from the" + \
			" live filesystem."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--buildpkgonly")+" ("+green("-B")+" short option)"
		print "              Creates a binary package, but does not merge it to the"
		print "              system. This has the restriction that unsatisfied dependencies"
		print "              must not exist for the desired package as they cannot be used if"
		print "              they do not exist on the system."
		print
		print "       "+green("--changelog")+" ("+green("-l")+" short option)"
		print "              When pretending, also display the ChangeLog entries for packages"
		print "              that will be upgraded."
		print
		print "       "+green("--color") + " < " + turquoise("y") + " | "+ turquoise("n")+" >"
		print "              Enable or disable color output. This option will override NOCOLOR"
		print "              (see make.conf(5)) and may also be used to force color output when"
		print "              stdout is not a tty (by default, color is disabled unless stdout"
		print "              is a tty)."
		print
		print "       "+green("--columns")
		print "              Display the pretend output in a tabular form. Versions are"
		print "              aligned vertically."
		print
		print "       "+green("--complete-graph")
		desc = "This causes emerge to consider the deep dependencies of all" + \
			" packages from the system and world sets. With this option enabled," + \
			" emerge will bail out if it determines that the given operation will" + \
			" break any dependencies of the packages that have been added to the" + \
			" graph. Like the --deep option, the --complete-graph" + \
			" option will significantly increase the time taken for dependency" + \
			" calculations. Note that, unlike the --deep option, the" + \
			" --complete-graph option does not cause any more packages to" + \
			" be updated than would have otherwise been updated with the option disabled."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--debug")+" ("+green("-d")+" short option)"
		print "              Tell emerge to run the ebuild command in --debug mode. In this"
		print "              mode, the bash build environment will run with the -x option,"
		print "              causing it to output verbose debug information print to stdout."
		print "              --debug is great for finding bash syntax errors as providing"
		print "              very verbose information about the dependency and build process."
		print
		print "       "+green("--deep")+" ("+green("-D")+" short option)"
		print "              This flag forces emerge to consider the entire dependency tree of"
		print "              packages, instead of checking only the immediate dependencies of"
		print "              the packages. As an example, this catches updates in libraries"
		print "              that are not directly listed in the dependencies of a package."
		print "              Also see --with-bdeps for behavior with respect to build time"
		print "              dependencies that are not strictly required."
		print 
		print "       "+green("--emptytree")+" ("+green("-e")+" short option)"
		print "              Virtually tweaks the tree of installed packages to contain"
		print "              nothing. This is great to use together with --pretend. This makes"
		print "              it possible for developers to get a complete overview of the"
		print "              complete dependency tree of a certain package."
		print
		print "       "+green("--fetchonly")+" ("+green("-f")+" short option)"
		print "              Instead of doing any package building, just perform fetches for"
		print "              all packages (main package as well as all dependencies.) When"
		print "              used in combination with --pretend all the SRC_URIs will be"
		print "              displayed multiple mirrors per line, one line per file."
		print
		print "       "+green("--fetch-all-uri")+" ("+green("-F")+" short option)"
		print "              Same as --fetchonly except that all package files, including those"
		print "              not required to build the package, will be processed."
		print
		print "       "+green("--getbinpkg")+" ("+green("-g")+" short option)"
		print "              Using the server and location defined in PORTAGE_BINHOST, portage"
		print "              will download the information from each binary file there and it"
		print "              will use that information to help build the dependency list. This"
		print "              option implies '-k'. (Use -gK for binary-only merging.)"
		print
		print "       "+green("--getbinpkgonly")+" ("+green("-G")+" short option)"
		print "              This option is identical to -g, as above, except it will not use"
		print "              ANY information from the local machine. All binaries will be"
		print "              downloaded from the remote server without consulting packages"
		print "              existing in the packages directory."
		print
		print "       " + green("--jobs") + " " + turquoise("JOBS")
		desc = "Specifies the number of packages " + \
			"to build simultaneously. Also see " + \
			"the related --load-average option."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--keep-going")
		desc = "Continue as much as possible after " + \
			"an error. When an error occurs, " + \
			"dependencies are recalculated for " + \
			"remaining packages and any with " + \
			"unsatisfied dependencies are " + \
			"automatically dropped. Also see " + \
			"the related --skipfirst option."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       " + green("--load-average") + " " + turquoise("LOAD")
		desc = "Specifies that no new builds should " + \
			"be started if there are other builds " + \
			"running and the load average is at " + \
			"least LOAD (a floating-point number)."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--newuse")+" ("+green("-N")+" short option)"
		print "              Tells emerge to include installed packages where USE flags have "
		print "              changed since installation."
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
		print "              ebuilds, or deps you specify on the command-line *will* cause"
		print "              Portage to remerge the package, even if it is already installed."
		print "              Note that Portage won't remerge dependencies by default."
		print 
		print "       "+green("--nospinner")
		print "              Disables the spinner regardless of terminal type."
		print
		print "       "+green("--oneshot")+" ("+green("-1")+" short option)"
		print "              Emerge as normal, but don't add packages to the world profile."
		print "              This package will only be updated if it is depended upon by"
		print "              another package."
		print
		print "       "+green("--onlydeps")+" ("+green("-o")+" short option)"
		print "              Only merge (or pretend to merge) the dependencies of the"
		print "              specified packages, not the packages themselves."
		print
		print "       "+green("--pretend")+" ("+green("-p")+" short option)"
		print "              Instead of actually performing the merge, simply display what"
		print "              ebuilds and tbz2s *would* have been installed if --pretend"
		print "              weren't used.  Using --pretend is strongly recommended before"
		print "              installing an unfamiliar package.  In the printout, N = new,"
		print "              U = updating, R = replacing, F = fetch  restricted, B = blocked"
		print "              by an already installed package, D = possible downgrading,"
		print "              S = slotted install. --verbose causes affecting use flags to be"
		print "              printed out accompanied by a '+' for enabled and a '-' for"
		print "              disabled USE flags."
		print
		print "       "+green("--quiet")+" ("+green("-q")+" short option)"
		print "              Effects vary, but the general outcome is a reduced or condensed"
		print "              output from portage's displays."
		print
		print "       "+green("--reinstall ") + turquoise("changed-use")
		print "              Tells emerge to include installed packages where USE flags have"
		print "              changed since installation.  Unlike --newuse, this option does"
		print "              not trigger reinstallation when flags that the user has not"
		print "              enabled are added or removed."
		print
		print "       "+green("--skipfirst")
		desc = "This option is only valid when " + \
			"used with --resume.  It removes the " + \
			"first package in the resume list. " + \
			"Dependencies are recalculated for " + \
			"remaining packages and any that " + \
			"have unsatisfied dependencies or are " + \
			"masked will be automatically dropped. " + \
			"Also see the related " + \
			"--keep-going option."
		for line in wrap(desc, desc_width):
			print desc_indent + line
		print
		print "       "+green("--tree")+" ("+green("-t")+" short option)"
		print "              Shows the dependency tree using indentation for dependencies."
		print "              The packages are also listed in reverse merge order so that"
		print "              a package's dependencies follow the package. Only really useful"
		print "              in combination with --emptytree, --update or --deep."
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
		print "              Effects vary, but the general outcome is an increased or expanded"
		print "              display of content in portage's displays."
		print
		print "       "+green("--with-bdeps")+" < " + turquoise("y") + " | "+ turquoise("n")+" >"
		print "              In dependency calculations, pull in build time dependencies that"
		print "              are not strictly required. This defaults to 'n' for installation"
		print "              actions and 'y' for the --depclean action. This setting can be"
		print "              added to EMERGE_DEFAULT_OPTS (see make.conf(5)) and later"
		print "              overridden via the command line."
		print
	elif myaction == "sync":
		print
		print bold("Usage: ")+turquoise("emerge")+" "+turquoise("--sync")
		print
		print "       'emerge --sync' tells emerge to update the Portage tree as specified in"
		print "       The SYNC variable found in /etc/make.conf.  By default, SYNC instructs"
		print "       emerge to perform an rsync-style update with rsync.gentoo.org."
		print
		print "       'emerge-webrsync' exists as a helper app to emerge --sync, providing a"
		print "       method to receive the entire portage tree as a tarball that can be"
		print "       extracted and used. First time syncs would benefit greatly from this."
		print
		print "       "+turquoise("WARNING:")
		print "       If using our rsync server, emerge will clean out all files that do not"
		print "       exist on it, including ones that you may have created. The exceptions"
		print "       to this are the distfiles, local and packages directories."
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
	elif myaction=="world":
		print
		print bold("Usage: ")+turquoise("emerge")+" [ "+green("options")+" ] "+turquoise("world")
		print
		print "       'emerge world' is the Portage command for completely updating your"
		print "       system.  The normal procedure is to first do an 'emerge --sync' and"
		print "       then an 'emerge --update --deep world'.  The first command brings your"
		print "       local Portage tree up-to-date with the latest version information and"
		print "       ebuilds.  The second command then rebuilds all packages for which newer"
		print "       versions or newer ebuilds have become available since you last did a"
		print "       sync and update."
		print

