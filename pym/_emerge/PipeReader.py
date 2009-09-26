# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask
from _emerge.PollConstants import PollConstants
import sys
import fcntl
import array

class PipeReader(AbstractPollTask):

	"""
	Reads output from one or more files and saves it in memory,
	for retrieval via the getvalue() method. This is driven by
	the scheduler's poll() loop, so it runs entirely within the
	current process.
	"""

	__slots__ = ("input_files",) + \
		("_read_data", "_reg_ids")

	def _start(self):
		self._reg_ids = set()
		self._read_data = []
		for k, f in self.input_files.items():
			fcntl.fcntl(f.fileno(), fcntl.F_SETFL,
				fcntl.fcntl(f.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK)
			self._reg_ids.add(self.scheduler.register(f.fileno(),
				self._registered_events, self._output_handler))
		self._registered = True

	def isAlive(self):
		return self._registered

	def cancel(self):
		if self.returncode is None:
			self.returncode = 1
			self.cancelled = True
		self.wait()

	def _wait(self):
		if self.returncode is not None:
			return self.returncode

		if self._registered:
			self.scheduler.schedule(self._reg_ids)
			self._unregister()

		self.returncode = os.EX_OK
		return self.returncode

	def getvalue(self):
		"""Retrieve the entire contents"""
		if sys.hexversion >= 0x3000000:
			return bytes().join(self._read_data)
		return "".join(self._read_data)

	def close(self):
		"""Free the memory buffer."""
		self._read_data = None

	def _output_handler(self, fd, event):

		if event & PollConstants.POLLIN:

			for f in self.input_files.values():
				if fd == f.fileno():
					break

			buf = array.array('B')
			try:
				buf.fromfile(f, self._bufsize)
			except EOFError:
				pass

			if buf:
				self._read_data.append(buf.tostring())
			else:
				self._unregister()
				self.wait()

		self._unregister_if_appropriate(event)
		return self._registered

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self._reg_ids is not None:
			for reg_id in self._reg_ids:
				self.scheduler.unregister(reg_id)
			self._reg_ids = None

		if self.input_files is not None:
			for f in self.input_files.values():
				f.close()
			self.input_files = None

