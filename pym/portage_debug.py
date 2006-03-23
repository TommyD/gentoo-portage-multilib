# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import os, sys, threading

import portage_const
from portage_util import writemsg

def set_trace(on=True):
	if on:
		t = trace_handler()
		threading.settrace(t.event_handler)
		sys.settrace(t.event_handler)
	else:
		sys.settrace(None)
		threading.settrace(None)

class trace_handler(object):

	def __init__(self):
		python_base = None
		for x in sys.path:
			if os.path.basename(x).startswith("python2."):
				python_base = x
				break

		self.ignore_prefixes = []
		if python_base is not None:
			self.ignore_prefixes.append(python_base + os.sep)

		self.trim_filename = prefix_trimmer(os.path.join(portage_const.PORTAGE_BASE_PATH, "pym") + os.sep).trim
		self.show_local_lines = False
		self.max_repr_length = 200

	def event_handler(self, *args):
		frame, event, arg = args
		if "line" == event:
			if self.show_local_lines:
				self.trace_line(*args)
		else:
			if not self.ignore_filename(frame.f_code.co_filename):
				self.trace_event(*args)
				return self.event_handler

	def trace_event(self, frame, event, arg):
		writemsg("%s line=%d name=%s event=%s %slocals=%s\n" % \
		(self.trim_filename(frame.f_code.co_filename),
		frame.f_lineno,
		frame.f_code.co_name,
		event,
		self.arg_repr(frame, event, arg),
		self.locals_repr(frame, event, arg)))

	def arg_repr(self, frame, event, arg):
		my_repr = None
		if "return" == event:
			my_repr = repr(arg)
			if len(my_repr) > self.max_repr_length:
				my_repr = "'omitted'"
			return "value=%s " % my_repr
		elif "exception" == event:
			my_repr = repr(arg[1])
			if len(my_repr) > self.max_repr_length:
				my_repr = "'omitted'"
			return "type=%s value=%s " % (arg[0], my_repr)

		return ""

	def trace_line(self, frame, event, arg):
		writemsg("%s line=%d\n" % (self.trim_filename(frame.f_code.co_filename), frame.f_lineno))

	def ignore_filename(self, filename):
		if filename:
			for x in self.ignore_prefixes:
				if filename.startswith(x):
					return True
		return False

	def locals_repr(self, frame, event, arg):
		"""Create a representation of the locals dict that is suitable for
		tracing output."""

		my_locals = frame.f_locals.copy()

		# prevent unsafe  __repr__ call on self when __init__ is called
		# (method calls aren't safe until after __init__  has completed).
		if frame.f_code.co_name == "__init__" and "self" in my_locals:
			my_locals["self"] = "omitted"

		# We omit items that will lead to unreasonable bloat of the trace
		# output (and resulting log file).
		for k, v in my_locals.iteritems():
			my_repr = repr(v)
			if len(my_repr) > self.max_repr_length:
				my_locals[k] = "omitted"
		return my_locals

class prefix_trimmer(object):
	def __init__(self, prefix):
		self.prefix = prefix
		self.cut_index = len(prefix)
		self.previous = None
		self.previous_trimmed = None

	def trim(self, s):
		"""Remove a prefix from the string and return the result.
		The previous result is automatically cached."""
		if s == self.previous:
			return self.previous_trimmed
		else:
			if s.startswith(self.prefix):
				self.previous_trimmed = s[self.cut_index:]
			else:
				self.previous_trimmed = s
			return self.previous_trimmed
