# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import logging
import select

from portage.util import writemsg_level

from _emerge.SlotObject import SlotObject
from _emerge.getloadavg import getloadavg
from _emerge.PollConstants import PollConstants
from _emerge.PollSelectAdapter import PollSelectAdapter

class PollScheduler(object):

	class _sched_iface_class(SlotObject):
		__slots__ = ("register", "schedule", "unregister")

	def __init__(self):
		self._max_jobs = 1
		self._max_load = None
		self._jobs = 0
		self._poll_event_queue = []
		self._poll_event_handlers = {}
		self._poll_event_handler_ids = {}
		# Increment id for each new handler.
		self._event_handler_id = 0
		self._poll_obj = create_poll_instance()
		self._scheduling = False

	def _schedule(self):
		"""
		Calls _schedule_tasks() and automatically returns early from
		any recursive calls to this method that the _schedule_tasks()
		call might trigger. This makes _schedule() safe to call from
		inside exit listeners.
		"""
		if self._scheduling:
			return False
		self._scheduling = True
		try:
			return self._schedule_tasks()
		finally:
			self._scheduling = False

	def _running_job_count(self):
		return self._jobs

	def _can_add_job(self):
		max_jobs = self._max_jobs
		max_load = self._max_load

		if self._max_jobs is not True and \
			self._running_job_count() >= self._max_jobs:
			return False

		if max_load is not None and \
			(max_jobs is True or max_jobs > 1) and \
			self._running_job_count() >= 1:
			try:
				avg1, avg5, avg15 = getloadavg()
			except OSError:
				return False

			if avg1 >= max_load:
				return False

		return True

	def _poll(self, timeout=None):
		"""
		All poll() calls pass through here. The poll events
		are added directly to self._poll_event_queue.
		In order to avoid endless blocking, this raises
		StopIteration if timeout is None and there are
		no file descriptors to poll.
		"""
		if not self._poll_event_handlers:
			self._schedule()
			if timeout is None and \
				not self._poll_event_handlers:
				raise StopIteration(
					"timeout is None and there are no poll() event handlers")

		# The following error is known to occur with Linux kernel versions
		# less than 2.6.24:
		#
		#   select.error: (4, 'Interrupted system call')
		#
		# This error has been observed after a SIGSTOP, followed by SIGCONT.
		# Treat it similar to EAGAIN if timeout is None, otherwise just return
		# without any events.
		while True:
			try:
				self._poll_event_queue.extend(self._poll_obj.poll(timeout))
				break
			except select.error as e:
				writemsg_level("\n!!! select error: %s\n" % (e,),
					level=logging.ERROR, noiselevel=-1)
				del e
				if timeout is not None:
					break

	def _next_poll_event(self, timeout=None):
		"""
		Since the _schedule_wait() loop is called by event
		handlers from _poll_loop(), maintain a central event
		queue for both of them to share events from a single
		poll() call. In order to avoid endless blocking, this
		raises StopIteration if timeout is None and there are
		no file descriptors to poll.
		"""
		if not self._poll_event_queue:
			self._poll(timeout)
		return self._poll_event_queue.pop()

	def _poll_loop(self):

		event_handlers = self._poll_event_handlers
		event_handled = False

		try:
			while event_handlers:
				f, event = self._next_poll_event()
				try:
					handler, reg_id = event_handlers[f]
				except KeyError:
					# This means unregister was called for a file descriptor
					# that still had a pending event in _poll_event_queue.
					# Since unregister has been called, we should assume that
					# the event can be safely ignored.
					continue
				handler(f, event)
				event_handled = True
		except StopIteration:
			event_handled = True

		if not event_handled:
			raise AssertionError("tight loop")

	def _schedule_yield(self):
		"""
		Schedule for a short period of time chosen by the scheduler based
		on internal state. Synchronous tasks should call this periodically
		in order to allow the scheduler to service pending poll events. The
		scheduler will call poll() exactly once, without blocking, and any
		resulting poll events will be serviced.
		"""
		event_handlers = self._poll_event_handlers
		events_handled = 0

		if not event_handlers:
			return bool(events_handled)

		if not self._poll_event_queue:
			self._poll(0)

		try:
			while event_handlers and self._poll_event_queue:
				f, event = self._next_poll_event()
				handler, reg_id = event_handlers[f]
				handler(f, event)
				events_handled += 1
		except StopIteration:
			events_handled += 1

		return bool(events_handled)

	def _register(self, f, eventmask, handler):
		"""
		@rtype: Integer
		@return: A unique registration id, for use in schedule() or
			unregister() calls.
		"""
		if f in self._poll_event_handlers:
			raise AssertionError("fd %d is already registered" % f)
		self._event_handler_id += 1
		reg_id = self._event_handler_id
		self._poll_event_handler_ids[reg_id] = f
		self._poll_event_handlers[f] = (handler, reg_id)
		self._poll_obj.register(f, eventmask)
		return reg_id

	def _unregister(self, reg_id):
		f = self._poll_event_handler_ids[reg_id]
		self._poll_obj.unregister(f)
		del self._poll_event_handlers[f]
		del self._poll_event_handler_ids[reg_id]

	def _schedule_wait(self, wait_ids):
		"""
		Schedule until wait_id is not longer registered
		for poll() events.
		@type wait_id: int
		@param wait_id: a task id to wait for
		"""
		event_handlers = self._poll_event_handlers
		handler_ids = self._poll_event_handler_ids
		event_handled = False

		if isinstance(wait_ids, int):
			wait_ids = frozenset([wait_ids])

		try:
			while wait_ids.intersection(handler_ids):
				f, event = self._next_poll_event()
				handler, reg_id = event_handlers[f]
				handler(f, event)
				event_handled = True
		except StopIteration:
			event_handled = True

		return event_handled


_can_poll_device = None

def can_poll_device():
	"""
	Test if it's possible to use poll() on a device such as a pty. This
	is known to fail on Darwin.
	@rtype: bool
	@returns: True if poll() on a device succeeds, False otherwise.
	"""

	global _can_poll_device
	if _can_poll_device is not None:
		return _can_poll_device

	if not hasattr(select, "poll"):
		_can_poll_device = False
		return _can_poll_device

	try:
		dev_null = open('/dev/null', 'rb')
	except IOError:
		_can_poll_device = False
		return _can_poll_device

	p = select.poll()
	p.register(dev_null.fileno(), PollConstants.POLLIN)

	invalid_request = False
	for f, event in p.poll():
		if event & PollConstants.POLLNVAL:
			invalid_request = True
			break
	dev_null.close()

	_can_poll_device = not invalid_request
	return _can_poll_device

def create_poll_instance():
	"""
	Create an instance of select.poll, or an instance of
	PollSelectAdapter there is no poll() implementation or
	it is broken somehow.
	"""
	if can_poll_device():
		return select.poll()
	return PollSelectAdapter()
