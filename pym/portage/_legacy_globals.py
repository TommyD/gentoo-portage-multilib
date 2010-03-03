# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage
from portage import os
from portage.const import CACHE_PATH, PROFILE_PATH

def _get_legacy_global(name):
	constructed = portage._legacy_globals_constructed
	if name in constructed:
		return getattr(portage, name)

	if name == 'portdb':
		portage.portdb = portage.db[portage.root]["porttree"].dbapi
		constructed.add(name)
		return getattr(portage, name)

	elif name in ('mtimedb', 'mtimedbfile'):
		portage.mtimedbfile = os.path.join(portage.root,
			CACHE_PATH, "mtimedb")
		constructed.add('mtimedbfile')
		portage.mtimedb = portage.MtimeDB(portage.mtimedbfile)
		constructed.add('mtimedb')
		return getattr(portage, name)

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, "/")

	portage._initializing_globals = True
	portage.db = portage.create_trees(**kwargs)
	constructed.add('db')
	del portage._initializing_globals

	settings = portage.db["/"]["vartree"].settings

	for root in portage.db:
		if root != "/":
			settings = portage.db[root]["vartree"].settings
			break

	portage.output._init(config_root=settings['PORTAGE_CONFIGROOT'])

	portage.settings = settings
	constructed.add('settings')

	portage.root = root
	constructed.add('root')

	# COMPATIBILITY
	# These attributes should not be used within
	# Portage under any circumstances.

	portage.archlist = settings.archlist()
	constructed.add('archlist')

	portage.features = settings.features
	constructed.add('features')

	portage.groups = settings["ACCEPT_KEYWORDS"].split()
	constructed.add('groups')

	portage.pkglines = settings.packages
	constructed.add('pkglines')

	portage.selinux_enabled = settings.selinux_enabled()
	constructed.add('selinux_enabled')

	portage.thirdpartymirrors = settings.thirdpartymirrors()
	constructed.add('thirdpartymirrors')

	portage.usedefaults = settings.use_defs
	constructed.add('usedefaults')

	profiledir = os.path.join(settings["PORTAGE_CONFIGROOT"], PROFILE_PATH)
	if not os.path.isdir(profiledir):
		profiledir = None
	portage.profiledir = profiledir
	constructed.add('profiledir')

	return getattr(portage, name)
