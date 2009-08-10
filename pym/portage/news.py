# portage: news management code
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ["NewsManager", "NewsItem", "DisplayRestriction",
	"DisplayProfileRestriction", "DisplayKeywordRestriction",
	"DisplayInstalledRestriction"]

import codecs
import logging
import os
import re
from portage.util import apply_secpass_permissions, ensure_dirs, \
	grabfile, normalize_path, write_atomic, writemsg_level
from portage.data import portage_gid
from portage.dep import isvalidatom
from portage.locks import lockfile, unlockfile
from portage.exception import InvalidLocation, OperationNotPermitted, \
	PermissionDenied

class NewsManager(object):
	"""
	This object manages GLEP 42 style news items.  It will cache news items
	that have previously shown up and notify users when there are relevant news
	items that apply to their packages that the user has not previously read.
	
	Creating a news manager requires:
	root - typically ${ROOT} see man make.conf and man emerge for details
	news_path - path to news items; usually $REPODIR/metadata/news
	unread_path - path to the news.repoid.unread file; this helps us track news items
	
	"""

	def __init__(self, portdb, vardb, news_path, unread_path, language_id='en'):
		self.news_path = news_path
		self.unread_path = unread_path
		self.target_root = vardb.root
		self.language_id = language_id
		self.config = vardb.settings
		self.vdb = vardb
		self.portdb = portdb

		# GLEP 42 says:
		#   All news item related files should be root owned and in the
		#   portage group with the group write (and, for directories,
		#   execute) bits set. News files should be world readable.
		self._uid = int(self.config["PORTAGE_INST_UID"])
		self._gid = portage_gid
		self._file_mode = 00064
		self._dir_mode  = 00074
		self._mode_mask = 00000

		portdir = portdb.porttree_root
		profiles_base = os.path.join(portdir, 'profiles') + os.path.sep
		profile_path = None
		if portdb.mysettings.profile_path:
			profile_path = normalize_path(
				os.path.realpath(portdb.mysettings.profile_path))
			if profile_path.startswith(profiles_base):
				profile_path = profile_path[len(profiles_base):]
		self._profile_path = profile_path

	def _unread_filename(self, repoid):
		return os.path.join(self.unread_path, 'news-%s.unread' % repoid)

	def _skip_filename(self, repoid):
		return os.path.join(self.unread_path, 'news-%s.skip' % repoid)

	def _news_dir(self, repoid):
		repo_path = self.portdb.getRepositoryPath(repoid)
		if repo_path is None:
			raise AssertionError("Invalid repoID: %s" % repoid)
		return os.path.join(repo_path, self.news_path)

	def updateItems(self, repoid):
		"""
		Figure out which news items from NEWS_PATH are both unread and relevant to
		the user (according to the GLEP 42 standards of relevancy).  Then add these
		items into the news.repoid.unread file.
		"""

		# Ensure that the unread path exists and is writable.

		try:
			ensure_dirs(self.unread_path, uid=self._uid, gid=self._gid,
				mode=self._dir_mode, mask=self._mode_mask)
		except (OperationNotPermitted, PermissionDenied):
			return

		if not os.access(self.unread_path, os.W_OK):
			return

		news_dir = self._news_dir(repoid)
		try:
			news = os.listdir(news_dir)
		except OSError:
			return

		skip_filename = self._skip_filename(repoid)
		unread_filename = self._unread_filename(repoid)
		unread_lock = lockfile(unread_filename, wantnewlockfile=1)
		try:
			try:
				unread = set(grabfile(unread_filename))
				unread_orig = unread.copy()
				skip = set(grabfile(skip_filename))
				skip_orig = skip.copy()
			except PermissionDenied:
				return

			updates = []
			for itemid in news:
				if itemid in skip:
					continue
				filename = os.path.join(news_dir, itemid,
					itemid + "." + self.language_id + ".txt")
				if not os.path.isfile(filename):
					continue
				if not isinstance(itemid, unicode):
					itemid = unicode(itemid, encoding='utf_8', errors='replace')
				item = NewsItem(filename, itemid)
				if not item.isValid():
					continue
				if item.isRelevant(profile=self._profile_path,
					config=self.config, vardb=self.vdb):
					unread.add(item.name)
					skip.add(item.name)

			if unread != unread_orig:
				write_atomic(unread_filename,
					"".join("%s\n" % x for x in sorted(unread)))
				apply_secpass_permissions(unread_filename,
					uid=self._uid, gid=self._gid,
					mode=self._file_mode, mask=self._mode_mask)

			if skip != skip_orig:
				write_atomic(skip_filename,
					"".join("%s\n" % x for x in sorted(skip)))
				apply_secpass_permissions(skip_filename,
					uid=self._uid, gid=self._gid,
					mode=self._file_mode, mask=self._mode_mask)

		finally:
			unlockfile(unread_lock)

	def getUnreadItems(self, repoid, update=False):
		"""
		Determine if there are unread relevant items in news.repoid.unread.
		If there are unread items return their number.
		If update is specified, updateNewsItems( repoid ) will be called to
		check for new items.
		"""

		if update:
			self.updateItems(repoid)

		unread_filename = self._unread_filename(repoid)
		unread_lock = None
		try:
			unread_lock = lockfile(unread_filename, wantnewlockfile=1)
		except (InvalidLocation, OperationNotPermitted, PermissionDenied):
			pass
		try:
			try:
				return len(grabfile(unread_filename))
			except PermissionDenied:
				return 0
		finally:
			if unread_lock:
				unlockfile(unread_lock)

_installedRE = re.compile("Display-If-Installed:(.*)\n")
_profileRE = re.compile("Display-If-Profile:(.*)\n")
_keywordRE = re.compile("Display-If-Keyword:(.*)\n")

class NewsItem(object):
	"""
	This class encapsulates a GLEP 42 style news item.
	It's purpose is to wrap parsing of these news items such that portage can determine
	whether a particular item is 'relevant' or not.  This requires parsing the item
	and determining 'relevancy restrictions'; these include "Display if Installed" or
	"display if arch: x86" and so forth.

	Creation of a news item involves passing in the path to the particular news item.

	"""

	def __init__(self, path, name):
		"""
		For a given news item we only want if it path is a file.
		"""
		self.path = path
		self.name = name
		self._parsed = False
		self._valid = True

	def isRelevant(self, vardb, config, profile):
		"""
		This function takes a dict of keyword arguments; one should pass in any
		objects need to do to lookups (like what keywords we are on, what profile,
		and a vardb so we can look at installed packages).
		Each restriction will pluck out the items that are required for it to match
		or raise a ValueError exception if the required object is not present.
		"""

		if not self._parsed:
			self.parse()

		if not len(self.restrictions):
			return True # no restrictions to match means everyone should see it

		kwargs = \
			{ 'vardb' : vardb,
				'config' : config,
				'profile' : profile }

		for restriction in self.restrictions:
			if restriction.checkRestriction(**kwargs):
				return True

		return False # No restrictions were met; thus we aren't relevant :(

	def isValid(self):
		if not self._parsed:
			self.parse()
		return self._valid

	def parse(self):
		lines = codecs.open(self.path, mode='r',
			encoding='utf_8', errors='replace').readlines()
		self.restrictions = []
		invalids = []
		for i, line in enumerate(lines):
			#Optimization to ignore regex matchines on lines that
			#will never match
			if not line.startswith('D'):
				continue
			restricts = {  _installedRE : DisplayInstalledRestriction,
					_profileRE : DisplayProfileRestriction,
					_keywordRE : DisplayKeywordRestriction }
			for regex, restriction in restricts.iteritems():
				match = regex.match(line)
				if match:
					self.restrictions.append(restriction(match.groups()[0].strip()))
					if not self.restrictions[-1].isValid():
						invalids.append((i + 1, line.rstrip("\n")))
					continue
		if invalids:
			self._valid = False
			msg = []
			msg.append("Invalid news item: %s" % (self.path,))
			for lineno, line in invalids:
				msg.append("  line %d: %s" % (lineno, line))
			writemsg_level("".join("!!! %s\n" % x for x in msg),
				level=logging.ERROR, noiselevel=-1)

		self._parsed = True

class DisplayRestriction(object):
	"""
	A base restriction object representing a restriction of display.
	news items may have 'relevancy restrictions' preventing them from
	being important.  In this case we need a manner of figuring out if
	a particular item is relevant or not.  If any of it's restrictions
	are met, then it is displayed
	"""

	def isValid(self):
		return True

	def checkRestriction(self, **kwargs):
		raise NotImplementedError('Derived class should over-ride this method')

class DisplayProfileRestriction(DisplayRestriction):
	"""
	A profile restriction where a particular item shall only be displayed
	if the user is running a specific profile.
	"""

	def __init__(self, profile):
		self.profile = profile

	def checkRestriction(self, **kwargs):
		if self.profile == kwargs['profile']:
			return True
		return False

class DisplayKeywordRestriction(DisplayRestriction):
	"""
	A keyword restriction where a particular item shall only be displayed
	if the user is running a specific keyword.
	"""

	def __init__(self, keyword):
		self.keyword = keyword

	def checkRestriction(self, **kwargs):
		if kwargs['config']['ARCH'] == self.keyword:
			return True
		return False

class DisplayInstalledRestriction(DisplayRestriction):
	"""
	An Installation restriction where a particular item shall only be displayed
	if the user has that item installed.
	"""

	def __init__(self, atom):
		self.atom = atom

	def isValid(self):
		return isvalidatom(self.atom)

	def checkRestriction(self, **kwargs):
		vdb = kwargs['vardb']
		if vdb.match(self.atom):
			return True
		return False
