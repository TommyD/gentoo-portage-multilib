# portage: Constants
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
cvs_id_string="$Id$"[5:-2]

# note this is lifted out of portage 2.  so... it's held onto for the sake of having stuff we still need,
# but it does need cleanup.

#VDB_PATH                = "var/db/pkg"

PRIVATE_PATH            = "/var/lib/portage"

USER_CONFIG_PATH        = "/etc/portage"
#CUSTOM_PROFILE_PATH     = USER_CONFIG_PATH+"/profile"

#PORTAGE_BASE_PATH       = "/usr/lib/portage"
try:
	import portage_custom_path
	PORTAGE_BASE_PATH	= portage_custom_path.PORTAGE_BASE_PATH

except ImportError:
	portage_custom_path = None
	print "warning, can't find portage_custom_path.  which means no custom PORTAGE_BASE_PATH"
	print "so... that means you're getting /home/bharring/new/ , which quite likely isn't what you want"
	PORTAGE_BASE_PATH			= "/home/bharring/new"

PORTAGE_BIN_PATH	= getattr(portage_custom_path, "PORTAGE_BIN_PATH", PORTAGE_BASE_PATH+"/bin")
DEFAULT_CONF_FILE = getattr(portage_custom_path, "DEFAULT_CONF_FILE", USER_CONFIG_PATH+"/config")
CONF_DEFAULTS		= getattr(portage_custom_path, "CONF_DEFAULTS", PORTAGE_BASE_PATH+"/conf_default_types")

#PORTAGE_PYM_PATH        = PORTAGE_BASE_PATH+"/pym"
#PROFILE_PATH            = "/etc/make.profile"
LOCALE_DATA_PATH        = PORTAGE_BASE_PATH+"/locale"

EBUILD_DAEMON_PATH      = PORTAGE_BIN_PATH+"/ebuild-daemon.sh"

SANDBOX_BINARY          = "/usr/bin/sandbox"

# XXX compatibility hack.  this shouldn't ever hit a stable release.
import os
if not os.path.exists(SANDBOX_BINARY):
	if os.path.exists(PORTAGE_BIN_PATH+"/sandbox"):
		SANDBOX_BINARY=PORTAGE_BIN_PATH+"/sandbox"

DEPSCAN_SH_BINARY       = "/sbin/depscan.sh"
BASH_BINARY             = "/bin/bash"
MOVE_BINARY             = "/bin/mv"
PRELINK_BINARY          = "/usr/sbin/prelink"

WORLD_FILE              = PRIVATE_PATH+"/world"
#MAKE_CONF_FILE          = "/etc/make.conf"
#MAKE_DEFAULTS_FILE      = PROFILE_PATH + "/make.defaults"

#DEPRECATED_PROFILE_FILE = PROFILE_PATH+"/deprecated"
#USER_VIRTUALS_FILE      = USER_CONFIG_PATH+"/virtuals"
#EBUILD_SH_ENV_FILE      = USER_CONFIG_PATH+"/bashrc"
INVALID_ENV_FILE        = "/etc/spork/is/not/valid/profile.env"
CUSTOM_MIRRORS_FILE     = USER_CONFIG_PATH+"/mirrors"
SANDBOX_PIDS_FILE       = "/tmp/sandboxpids.tmp"

# since I didn't know wtf this was, it's used for knowing when CONFIG_PROTECT* can be ignored.
CONFIG_MEMORY_FILE      = PRIVATE_PATH + "/config"

# wtf is this actually used for!?
#STICKIES=["KEYWORDS_ACCEPT","USE","CFLAGS","CXXFLAGS","MAKEOPTS","EXTRA_ECONF","EXTRA_EINSTALL","EXTRA_EMAKE"]

#CONFCACHE_FILE          = CACHE_PATH+"/confcache"
#CONFCACHE_LIST          = CACHE_PATH+"/confcache_files.anydbm"

LIBFAKEROOT_PATH        = "/usr/lib/libfakeroot.so"
FAKEROOT_PATH           = "/usr/bin/fakeroot"

RSYNC_BIN               = "/usr/bin/rsync"
RSYNC_HOST              = "rsync.gentoo.org/gentoo-portage"

CVS_BIN                 = "/usr/bin/cvs"

# find a better place for this...
EBUILD_PHASES			= "setup unpack compile test install preinst postinst prerm postrm"

