# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SlotObject import SlotObject
class AsynchronousTask(SlotObject):
	"""
	Subclasses override _wait() and _poll() so that calls
	to public methods can be wrapped for implementing
	hooks such as exit listener notification.

	Sublasses should call self.wait() to notify exit listeners after
	the task is complete and self.returncode has been set.
	"""

	__slots__ = ("background", "cancelled", "returncode") + \
		("_exit_listeners", "_exit_listener_stack", "_start_listeners")

	def start(self):
		"""
		Start an asynchronous task and then return as soon as possible.
		"""
		self._start_hook()
		self._start()

	def _start(self):
		raise NotImplementedError(self)

	def isAlive(self):
		return self.returncode is None

	def poll(self):
		self._wait_hook()
		return self._poll()

	def _poll(self):
		return self.returncode

	def wait(self):
		if self.returncode is None:
			self._wait()
		self._wait_hook()
		return self.returncode

	def _wait(self):
		return self.returncode

	def cancel(self):
		self.cancelled = True
		self.wait()

	def addStartListener(self, f):
		"""
		The function will be called with one argument, a reference to self.
		"""
		if self._start_listeners is None:
			self._start_listeners = []
		self._start_listeners.append(f)

	def removeStartListener(self, f):
		if self._start_listeners is None:
			return
		self._start_listeners.remove(f)

	def _start_hook(self):
		if self._start_listeners is not None:
			start_listeners = self._start_listeners
			self._start_listeners = None

			for f in start_listeners:
				f(self)

	def addExitListener(self, f):
		"""
		The function will be called with one argument, a reference to self.
		"""
		if self._exit_listeners is None:
			self._exit_listeners = []
		self._exit_listeners.append(f)

	def removeExitListener(self, f):
		if self._exit_listeners is None:
			if self._exit_listener_stack is not None:
				self._exit_listener_stack.remove(f)
			return
		self._exit_listeners.remove(f)

	def _wait_hook(self):
		"""
		Call this method after the task completes, just before returning
		the returncode from wait() or poll(). This hook is
		used to trigger exit listeners when the returncode first
		becomes available.
		"""
		if self.returncode is not None and \
			self._exit_listeners is not None:

			# This prevents recursion, in case one of the
			# exit handlers triggers this method again by
			# calling wait(). Use a stack that gives
			# removeExitListener() an opportunity to consume
			# listeners from the stack, before they can get
			# called below. This is necessary because a call
			# to one exit listener may result in a call to
			# removeExitListener() for another listener on
			# the stack. That listener needs to be removed
			# from the stack since it would be inconsistent
			# to call it after it has been been passed into
			# removeExitListener().
			self._exit_listener_stack = self._exit_listeners
			self._exit_listeners = None

			self._exit_listener_stack.reverse()
			while self._exit_listener_stack:
				self._exit_listener_stack.pop()(self)

