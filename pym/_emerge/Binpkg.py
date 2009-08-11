# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.EbuildPhase import EbuildPhase
from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.BinpkgExtractorAsync import BinpkgExtractorAsync
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
from _emerge.EbuildMerge import EbuildMerge
from _emerge.EbuildBuildDir import EbuildBuildDir
from portage.util import writemsg
import portage
from portage import os
import codecs
from portage.output import colorize

class Binpkg(CompositeTask):

	__slots__ = ("find_blockers",
		"ldpath_mtimes", "logger", "opts",
		"pkg", "pkg_count", "prefetcher", "settings", "world_atom") + \
		("_bintree", "_build_dir", "_ebuild_path", "_fetched_pkg",
		"_image_dir", "_infloc", "_pkg_path", "_tree", "_verify")

	def _writemsg_level(self, msg, level=0, noiselevel=0):

		if not self.background:
			portage.util.writemsg_level(msg,
				level=level, noiselevel=noiselevel)

		log_path = self.settings.get("PORTAGE_LOG_FILE")
		if  log_path is not None:
			f = codecs.open(log_path, mode='a',
				encoding='utf_8', errors='replace')
			try:
				f.write(msg)
			finally:
				f.close()

	def _start(self):

		pkg = self.pkg
		settings = self.settings
		settings.setcpv(pkg)
		self._tree = "bintree"
		self._bintree = self.pkg.root_config.trees[self._tree]
		self._verify = not self.opts.pretend

		dir_path = os.path.join(settings["PORTAGE_TMPDIR"],
			"portage", pkg.category, pkg.pf)
		self._build_dir = EbuildBuildDir(dir_path=dir_path,
			pkg=pkg, settings=settings)
		self._image_dir = os.path.join(dir_path, "image")
		self._infloc = os.path.join(dir_path, "build-info")
		self._ebuild_path = os.path.join(self._infloc, pkg.pf + ".ebuild")
		settings["EBUILD"] = self._ebuild_path
		debug = settings.get("PORTAGE_DEBUG") == "1"
		portage.doebuild_environment(self._ebuild_path, "setup",
			settings["ROOT"], settings, debug, 1, self._bintree.dbapi)
		settings.configdict["pkg"]["EMERGE_FROM"] = pkg.type_name

		# The prefetcher has already completed or it
		# could be running now. If it's running now,
		# wait for it to complete since it holds
		# a lock on the file being fetched. The
		# portage.locks functions are only designed
		# to work between separate processes. Since
		# the lock is held by the current process,
		# use the scheduler and fetcher methods to
		# synchronize with the fetcher.
		prefetcher = self.prefetcher
		if prefetcher is None:
			pass
		elif not prefetcher.isAlive():
			prefetcher.cancel()
		elif prefetcher.poll() is None:

			waiting_msg = ("Fetching '%s' " + \
				"in the background. " + \
				"To view fetch progress, run `tail -f " + \
				"/var/log/emerge-fetch.log` in another " + \
				"terminal.") % prefetcher.pkg_path
			msg_prefix = colorize("GOOD", " * ")
			from textwrap import wrap
			waiting_msg = "".join("%s%s\n" % (msg_prefix, line) \
				for line in wrap(waiting_msg, 65))
			if not self.background:
				writemsg(waiting_msg, noiselevel=-1)

			self._current_task = prefetcher
			prefetcher.addExitListener(self._prefetch_exit)
			return

		self._prefetch_exit(prefetcher)

	def _prefetch_exit(self, prefetcher):

		pkg = self.pkg
		pkg_count = self.pkg_count
		if not (self.opts.pretend or self.opts.fetchonly):
			self._build_dir.lock()
			# If necessary, discard old log so that we don't
			# append to it.
			self._build_dir.clean_log()
			# Initialze PORTAGE_LOG_FILE.
			portage.prepare_build_dirs(self.settings["ROOT"], self.settings, 1)
		fetcher = BinpkgFetcher(background=self.background,
			logfile=self.settings.get("PORTAGE_LOG_FILE"), pkg=self.pkg,
			pretend=self.opts.pretend, scheduler=self.scheduler)
		pkg_path = fetcher.pkg_path
		self._pkg_path = pkg_path

		if self.opts.getbinpkg and self._bintree.isremote(pkg.cpv):

			msg = " --- (%s of %s) Fetching Binary (%s::%s)" %\
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path)
			short_msg = "emerge: (%s of %s) %s Fetch" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			self.logger.log(msg, short_msg=short_msg)
			self._start_task(fetcher, self._fetcher_exit)
			return

		self._fetcher_exit(fetcher)

	def _fetcher_exit(self, fetcher):

		# The fetcher only has a returncode when
		# --getbinpkg is enabled.
		if fetcher.returncode is not None:
			self._fetched_pkg = True
			if self._default_exit(fetcher) != os.EX_OK:
				self._unlock_builddir()
				self.wait()
				return

		if self.opts.pretend:
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		verifier = None
		if self._verify:
			logfile = None
			if self.background:
				logfile = self.settings.get("PORTAGE_LOG_FILE")
			verifier = BinpkgVerifier(background=self.background,
				logfile=logfile, pkg=self.pkg)
			self._start_task(verifier, self._verifier_exit)
			return

		self._verifier_exit(verifier)

	def _verifier_exit(self, verifier):
		if verifier is not None and \
			self._default_exit(verifier) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		logger = self.logger
		pkg = self.pkg
		pkg_count = self.pkg_count
		pkg_path = self._pkg_path

		if self._fetched_pkg:
			self._bintree.inject(pkg.cpv, filename=pkg_path)

		if self.opts.fetchonly:
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		msg = " === (%s of %s) Merging Binary (%s::%s)" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path)
		short_msg = "emerge: (%s of %s) %s Merge Binary" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv)
		logger.log(msg, short_msg=short_msg)

		phase = "clean"
		settings = self.settings
		ebuild_phase = EbuildPhase(background=self.background,
			pkg=pkg, phase=phase, scheduler=self.scheduler,
			settings=settings, tree=self._tree)

		self._start_task(ebuild_phase, self._clean_exit)

	def _clean_exit(self, clean_phase):
		if self._default_exit(clean_phase) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		dir_path = self._build_dir.dir_path

		infloc = self._infloc
		pkg = self.pkg
		pkg_path = self._pkg_path

		dir_mode = 0755
		for mydir in (dir_path, self._image_dir, infloc):
			portage.util.ensure_dirs(mydir, uid=portage.data.portage_uid,
				gid=portage.data.portage_gid, mode=dir_mode)

		# This initializes PORTAGE_LOG_FILE.
		portage.prepare_build_dirs(self.settings["ROOT"], self.settings, 1)
		self._writemsg_level(">>> Extracting info\n")

		pkg_xpak = portage.xpak.tbz2(self._pkg_path)
		check_missing_metadata = ("CATEGORY", "PF")
		missing_metadata = set()
		for k in check_missing_metadata:
			v = pkg_xpak.getfile(k)
			if not v:
				missing_metadata.add(k)

		pkg_xpak.unpackinfo(infloc)
		for k in missing_metadata:
			if k == "CATEGORY":
				v = pkg.category
			elif k == "PF":
				v = pkg.pf
			else:
				continue

			f = codecs.open(os.path.join(infloc, k), mode='w',
				encoding='utf_8', errors='replace')
			try:
				f.write(v + "\n")
			finally:
				f.close()

		# Store the md5sum in the vdb.
		f = open(os.path.join(infloc, "BINPKGMD5"), "w")
		try:
			f.write(str(portage.checksum.perform_md5(pkg_path)) + "\n")
		finally:
			f.close()

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		settings = self.settings
		settings.setcpv(self.pkg)
		settings["PORTAGE_BINPKG_FILE"] = pkg_path
		settings.backup_changes("PORTAGE_BINPKG_FILE")

		phase = "setup"
		setup_phase = EbuildPhase(background=self.background,
			pkg=self.pkg, phase=phase, scheduler=self.scheduler,
			settings=settings, tree=self._tree)

		setup_phase.addExitListener(self._setup_exit)
		self._current_task = setup_phase
		self.scheduler.scheduleSetup(setup_phase)

	def _setup_exit(self, setup_phase):
		if self._default_exit(setup_phase) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		extractor = BinpkgExtractorAsync(background=self.background,
			image_dir=self._image_dir,
			pkg=self.pkg, pkg_path=self._pkg_path, scheduler=self.scheduler)
		self._writemsg_level(">>> Extracting %s\n" % self.pkg.cpv)
		self._start_task(extractor, self._extractor_exit)

	def _extractor_exit(self, extractor):
		if self._final_exit(extractor) != os.EX_OK:
			self._unlock_builddir()
			writemsg("!!! Error Extracting '%s'\n" % self._pkg_path,
				noiselevel=-1)
		self.wait()

	def _unlock_builddir(self):
		if self.opts.pretend or self.opts.fetchonly:
			return
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		self._build_dir.unlock()

	def install(self):

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		settings = self.settings
		settings["PORTAGE_BINPKG_FILE"] = self._pkg_path
		settings.backup_changes("PORTAGE_BINPKG_FILE")

		merge = EbuildMerge(find_blockers=self.find_blockers,
			ldpath_mtimes=self.ldpath_mtimes, logger=self.logger,
			pkg=self.pkg, pkg_count=self.pkg_count,
			pkg_path=self._pkg_path, scheduler=self.scheduler,
			settings=settings, tree=self._tree, world_atom=self.world_atom)

		try:
			retval = merge.execute()
		finally:
			settings.pop("PORTAGE_BINPKG_FILE", None)
			self._unlock_builddir()
		return retval

