# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage
from portage import os
from _emerge.EbuildMetadataPhase import EbuildMetadataPhase
from _emerge.PollScheduler import PollScheduler

class MetadataRegen(PollScheduler):

	def __init__(self, portdb, cp_iter=None, consumer=None,
		max_jobs=None, max_load=None):
		PollScheduler.__init__(self)
		self._portdb = portdb
		self._global_cleanse = False
		if cp_iter is None:
			cp_iter = self._iter_every_cp()
			# We can globally cleanse stale cache only if we
			# iterate over every single cp.
			self._global_cleanse = True
		self._cp_iter = cp_iter
		self._consumer = consumer

		if max_jobs is None:
			max_jobs = 1

		self._max_jobs = max_jobs
		self._max_load = max_load
		self._sched_iface = self._sched_iface_class(
			register=self._register,
			schedule=self._schedule_wait,
			unregister=self._unregister)

		self._valid_pkgs = set()
		self._cp_set = set()
		self._process_iter = self._iter_metadata_processes()
		self.returncode = os.EX_OK
		self._error_count = 0

	def _iter_every_cp(self):
		every_cp = self._portdb.cp_all()
		every_cp.sort(reverse=True)
		try:
			while True:
				yield every_cp.pop()
		except IndexError:
			pass

	def _iter_metadata_processes(self):
		portdb = self._portdb
		valid_pkgs = self._valid_pkgs
		cp_set = self._cp_set
		consumer = self._consumer

		for cp in self._cp_iter:
			cp_set.add(cp)
			portage.writemsg_stdout("Processing %s\n" % cp)
			cpv_list = portdb.cp_list(cp)
			for cpv in cpv_list:
				valid_pkgs.add(cpv)
				ebuild_path, repo_path = portdb.findname2(cpv)
				metadata, st, emtime = portdb._pull_valid_cache(
					cpv, ebuild_path, repo_path)
				if metadata is not None:
					if consumer is not None:
						consumer(cpv, ebuild_path,
							repo_path, metadata)
					continue

				yield EbuildMetadataPhase(cpv=cpv, ebuild_path=ebuild_path,
					ebuild_mtime=emtime,
					metadata_callback=portdb._metadata_callback,
					portdb=portdb, repo_path=repo_path,
					settings=portdb.doebuild_settings)

	def run(self):

		portdb = self._portdb
		from portage.cache.cache_errors import CacheError
		dead_nodes = {}

		while self._schedule():
			self._poll_loop()

		while self._jobs:
			self._poll_loop()

		if self._global_cleanse:
			for mytree in portdb.porttrees:
				try:
					dead_nodes[mytree] = set(portdb.auxdb[mytree].iterkeys())
				except CacheError, e:
					portage.writemsg("Error listing cache entries for " + \
						"'%s': %s, continuing...\n" % (mytree, e),
						noiselevel=-1)
					del e
					dead_nodes = None
					break
		else:
			cp_set = self._cp_set
			cpv_getkey = portage.cpv_getkey
			for mytree in portdb.porttrees:
				try:
					dead_nodes[mytree] = set(cpv for cpv in \
						portdb.auxdb[mytree].iterkeys() \
						if cpv_getkey(cpv) in cp_set)
				except CacheError, e:
					portage.writemsg("Error listing cache entries for " + \
						"'%s': %s, continuing...\n" % (mytree, e),
						noiselevel=-1)
					del e
					dead_nodes = None
					break

		if dead_nodes:
			for y in self._valid_pkgs:
				for mytree in portdb.porttrees:
					if portdb.findname2(y, mytree=mytree)[0]:
						dead_nodes[mytree].discard(y)

			for mytree, nodes in dead_nodes.iteritems():
				auxdb = portdb.auxdb[mytree]
				for y in nodes:
					try:
						del auxdb[y]
					except (KeyError, CacheError):
						pass

	def _schedule_tasks(self):
		"""
		@rtype: bool
		@returns: True if there may be remaining tasks to schedule,
			False otherwise.
		"""
		while self._can_add_job():
			try:
				metadata_process = self._process_iter.next()
			except StopIteration:
				return False

			self._jobs += 1
			metadata_process.scheduler = self._sched_iface
			metadata_process.addExitListener(self._metadata_exit)
			metadata_process.start()
		return True

	def _metadata_exit(self, metadata_process):
		self._jobs -= 1
		if metadata_process.returncode != os.EX_OK:
			self.returncode = 1
			self._error_count += 1
			self._valid_pkgs.discard(metadata_process.cpv)
			portage.writemsg("Error processing %s, continuing...\n" % \
				(metadata_process.cpv,), noiselevel=-1)

		if self._consumer is not None:
			# On failure, still notify the consumer (in this case the metadata
			# argument is None).
			self._consumer(metadata_process.cpv,
				metadata_process.ebuild_path,
				metadata_process.repo_path,
				metadata_process.metadata)

		self._schedule()

