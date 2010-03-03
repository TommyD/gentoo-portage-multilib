# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ['getmaskingreason']

import portage
from portage import os
from portage.const import USER_CONFIG_PATH
from portage.dep import match_from_list
from portage.localization import _
from portage.util import grablines, normalize_path
from portage.versions import catpkgsplit

def getmaskingreason(mycpv, metadata=None, settings=None, portdb=None, return_location=False):
	if settings is None:
		settings = portage.settings
	if portdb is None:
		portdb = portage.portdb
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError(_("invalid CPV: %s") % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(zip(db_keys, portdb.aux_get(mycpv, db_keys)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
	if metadata is None:
		# Can't access SLOT due to corruption.
		cpv_slot_list = [mycpv]
	else:
		cpv_slot_list = ["%s:%s" % (mycpv, metadata["SLOT"])]
	mycp=mysplit[0]+"/"+mysplit[1]

	# XXX- This is a temporary duplicate of code from the config constructor.
	locations = [os.path.join(settings["PORTDIR"], "profiles")]
	locations.extend(settings.profiles)
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(normalize_path(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH))
	locations.reverse()
	pmasklists = [(x, grablines(os.path.join(x, "package.mask"), recursive=1)) for x in locations]

	if mycp in settings.pmaskdict:
		for x in settings.pmaskdict[mycp]:
			if match_from_list(x, cpv_slot_list):
				for pmask in pmasklists:
					comment = ""
					comment_valid = -1
					pmask_filename = os.path.join(pmask[0], "package.mask")
					for i in range(len(pmask[1])):
						l = pmask[1][i].strip()
						if l == "":
							comment = ""
							comment_valid = -1
						elif l[0] == "#":
							comment += (l+"\n")
							comment_valid = i + 1
						elif l == x:
							if comment_valid != i:
								comment = ""
							if return_location:
								return (comment, pmask_filename)
							else:
								return comment
						elif comment_valid != -1:
							# Apparently this comment applies to muliple masks, so
							# it remains valid until a blank line is encountered.
							comment_valid += 1
	if return_location:
		return (None, None)
	else:
		return None
