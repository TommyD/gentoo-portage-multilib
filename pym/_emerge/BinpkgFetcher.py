# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SpawnProcess import SpawnProcess
try:
	from urllib.parse import urlparse as urllib_parse_urlparse
except ImportError:
	from urlparse import urlparse as urllib_parse_urlparse
import sys
import portage
from portage import os

if sys.hexversion >= 0x3000000:
	long = int

class BinpkgFetcher(SpawnProcess):

	__slots__ = ("pkg", "pretend",
		"locked", "pkg_path", "_lock_obj")

	def __init__(self, **kwargs):
		SpawnProcess.__init__(self, **kwargs)
		pkg = self.pkg
		self.pkg_path = pkg.root_config.trees["bintree"].getname(pkg.cpv)

	def _start(self):

		if self.cancelled:
			return

		pkg = self.pkg
		pretend = self.pretend
		bintree = pkg.root_config.trees["bintree"]
		settings = bintree.settings
		use_locks = "distlocks" in settings.features
		pkg_path = self.pkg_path

		if not pretend:
			portage.util.ensure_dirs(os.path.dirname(pkg_path))
			if use_locks:
				self.lock()
		exists = os.path.exists(pkg_path)
		resume = exists and os.path.basename(pkg_path) in bintree.invalids
		if not (pretend or resume):
			# Remove existing file or broken symlink.
			try:
				os.unlink(pkg_path)
			except OSError:
				pass

		# urljoin doesn't work correctly with
		# unrecognized protocols like sftp
		if bintree._remote_has_index:
			rel_uri = bintree._remotepkgs[pkg.cpv].get("PATH")
			if not rel_uri:
				rel_uri = pkg.cpv + ".tbz2"
			uri = bintree._remote_base_uri.rstrip("/") + \
				"/" + rel_uri.lstrip("/")
		else:
			uri = settings["PORTAGE_BINHOST"].rstrip("/") + \
				"/" + pkg.pf + ".tbz2"

		if pretend:
			portage.writemsg_stdout("\n%s\n" % uri, noiselevel=-1)
			self.returncode = os.EX_OK
			self.wait()
			return

		protocol = urllib_parse_urlparse(uri)[0]
		fcmd_prefix = "FETCHCOMMAND"
		if resume:
			fcmd_prefix = "RESUMECOMMAND"
		fcmd = settings.get(fcmd_prefix + "_" + protocol.upper())
		if not fcmd:
			fcmd = settings.get(fcmd_prefix)

		fcmd_vars = {
			"DISTDIR" : os.path.dirname(pkg_path),
			"URI"     : uri,
			"FILE"    : os.path.basename(pkg_path)
		}

		fetch_env = dict(settings.items())
		fetch_args = [portage.util.varexpand(x, mydict=fcmd_vars) \
			for x in portage.util.shlex_split(fcmd)]

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes

		# Redirect all output to stdout since some fetchers like
		# wget pollute stderr (if portage detects a problem then it
		# can send it's own message to stderr).
		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes.setdefault(1, sys.stdout.fileno())
		fd_pipes.setdefault(2, sys.stdout.fileno())

		self.args = fetch_args
		self.env = fetch_env
		SpawnProcess._start(self)

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)
		if self.returncode == os.EX_OK:
			# If possible, update the mtime to match the remote package if
			# the fetcher didn't already do it automatically.
			bintree = self.pkg.root_config.trees["bintree"]
			if bintree._remote_has_index:
				remote_mtime = bintree._remotepkgs[self.pkg.cpv].get("MTIME")
				if remote_mtime is not None:
					try:
						remote_mtime = long(remote_mtime)
					except ValueError:
						pass
					else:
						try:
							local_mtime = long(os.stat(self.pkg_path).st_mtime)
						except OSError:
							pass
						else:
							if remote_mtime != local_mtime:
								try:
									os.utime(self.pkg_path,
										(remote_mtime, remote_mtime))
								except OSError:
									pass

		if self.locked:
			self.unlock()

	def lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		self._lock_obj = portage.locks.lockfile(
			self.pkg_path, wantnewlockfile=1)
		self.locked = True

	class AlreadyLocked(portage.exception.PortageException):
		pass

	def unlock(self):
		if self._lock_obj is None:
			return
		portage.locks.unlockfile(self._lock_obj)
		self._lock_obj = None
		self.locked = False

