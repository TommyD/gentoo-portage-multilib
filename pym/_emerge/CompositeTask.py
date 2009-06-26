# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.AsynchronousTask import AsynchronousTask
import os
class CompositeTask(AsynchronousTask):

	__slots__ = ("scheduler",) + ("_current_task",)

	def isAlive(self):
		return self._current_task is not None

	def cancel(self):
		self.cancelled = True
		if self._current_task is not None:
			self._current_task.cancel()

	def _poll(self):
		"""
		This does a loop calling self._current_task.poll()
		repeatedly as long as the value of self._current_task
		keeps changing. It calls poll() a maximum of one time
		for a given self._current_task instance. This is useful
		since calling poll() on a task can trigger advance to
		the next task could eventually lead to the returncode
		being set in cases when polling only a single task would
		not have the same effect.
		"""

		prev = None
		while True:
			task = self._current_task
			if task is None or task is prev:
				# don't poll the same task more than once
				break
			task.poll()
			prev = task

		return self.returncode

	def _wait(self):

		prev = None
		while True:
			task = self._current_task
			if task is None:
				# don't wait for the same task more than once
				break
			if task is prev:
				# Before the task.wait() method returned, an exit
				# listener should have set self._current_task to either
				# a different task or None. Something is wrong.
				raise AssertionError("self._current_task has not " + \
					"changed since calling wait", self, task)
			task.wait()
			prev = task

		return self.returncode

	def _assert_current(self, task):
		"""
		Raises an AssertionError if the given task is not the
		same one as self._current_task. This can be useful
		for detecting bugs.
		"""
		if task is not self._current_task:
			raise AssertionError("Unrecognized task: %s" % (task,))

	def _default_exit(self, task):
		"""
		Calls _assert_current() on the given task and then sets the
		composite returncode attribute if task.returncode != os.EX_OK.
		If the task failed then self._current_task will be set to None.
		Subclasses can use this as a generic task exit callback.

		@rtype: int
		@returns: The task.returncode attribute.
		"""
		self._assert_current(task)
		if task.returncode != os.EX_OK:
			self.returncode = task.returncode
			self._current_task = None
		return task.returncode

	def _final_exit(self, task):
		"""
		Assumes that task is the final task of this composite task.
		Calls _default_exit() and sets self.returncode to the task's
		returncode and sets self._current_task to None.
		"""
		self._default_exit(task)
		self._current_task = None
		self.returncode = task.returncode
		return self.returncode

	def _default_final_exit(self, task):
		"""
		This calls _final_exit() and then wait().

		Subclasses can use this as a generic final task exit callback.

		"""
		self._final_exit(task)
		return self.wait()

	def _start_task(self, task, exit_handler):
		"""
		Register exit handler for the given task, set it
		as self._current_task, and call task.start().

		Subclasses can use this as a generic way to start
		a task.

		"""
		task.addExitListener(exit_handler)
		self._current_task = task
		task.start()

