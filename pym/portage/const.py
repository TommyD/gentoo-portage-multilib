# portage: Constants
# Copyright 1998-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

# There are two types of variables here which can easily be confused,
# resulting in arbitrary bugs, mainly exposed with an offset
# installation (Prefix).  The two types relate to the usage of
# config_root or target_root.
# The first, config_root (PORTAGE_CONFIGROOT), can be a path somewhere,
# from which all derived paths need to be relative (e.g.
# USER_CONFIG_PATH) without EPREFIX prepended in Prefix.  This means
# config_root can for instance be set to "$HOME/my/config".  Obviously,
# in such case it is not appropriate to prepend EPREFIX to derived
# constants.  The default value of config_root is EPREFIX (in non-Prefix
# the empty string) -- overriding the value loses the EPREFIX as one
# would expect.
# Second there is target_root (ROOT) which is used to install somewhere
# completely else, in Prefix of limited use.  Because this is an offset
# always given, the EPREFIX should always be applied in it.  Those
# constants (like VDB_PATH) are always absolute and hence DO have
# EPREFIX prepended in Prefix.
# The variables in this file are grouped by config_root, target_root.

# variables used with config_root (these need to be relative)
MAKE_CONF_FILE           = "etc/make.conf"
USER_CONFIG_PATH         = "etc/portage"
MODULES_FILE_PATH        = USER_CONFIG_PATH + "/modules"
CUSTOM_PROFILE_PATH      = USER_CONFIG_PATH + "/profile"
USER_VIRTUALS_FILE       = USER_CONFIG_PATH + "/virtuals"
EBUILD_SH_ENV_FILE       = USER_CONFIG_PATH + "/bashrc"
CUSTOM_MIRRORS_FILE      = USER_CONFIG_PATH + "/mirrors"
COLOR_MAP_FILE           = USER_CONFIG_PATH + "/color.map"
PROFILE_PATH             = "etc/make.profile"
MAKE_DEFAULTS_FILE       = PROFILE_PATH + "/make.defaults"  # FIXME: not used
DEPRECATED_PROFILE_FILE  = PROFILE_PATH + "/deprecated"

# variables used with targetroot (these need to be absolute, but not
# have a leading '/' since they are used directly with os.path.join)
VDB_PATH                 = "var/db/pkg"
CACHE_PATH               = "var/cache/edb"
PRIVATE_PATH             = "var/lib/portage"
WORLD_FILE               = PRIVATE_PATH + "/world"
WORLD_SETS_FILE          = PRIVATE_PATH + "/world_sets"
CONFIG_MEMORY_FILE       = PRIVATE_PATH + "/config"
NEWS_LIB_PATH            = "var/lib/gentoo"

# these variables are not used with target_root or config_root
DEPCACHE_PATH            = "/var/cache/edb/dep"
GLOBAL_CONFIG_PATH       = "/usr/share/portage/config"
PORTAGE_BASE_PATH        = os.path.join(os.sep, os.sep.join(__file__.split(os.sep)[:-3]))
PORTAGE_BIN_PATH         = PORTAGE_BASE_PATH + "/bin"
PORTAGE_PYM_PATH         = PORTAGE_BASE_PATH + "/pym"
LOCALE_DATA_PATH         = PORTAGE_BASE_PATH + "/locale"  # FIXME: not used
EBUILD_SH_BINARY         = PORTAGE_BIN_PATH + "/ebuild.sh"
MISC_SH_BINARY           = PORTAGE_BIN_PATH + "/misc-functions.sh"
SANDBOX_BINARY           = "/usr/bin/sandbox"
FAKEROOT_BINARY          = "/usr/bin/fakeroot"
BASH_BINARY              = "/bin/bash"
MOVE_BINARY              = "/bin/mv"
PRELINK_BINARY           = "/usr/sbin/prelink"

INVALID_ENV_FILE         = "/etc/spork/is/not/valid/profile.env"
REPO_NAME_FILE           = "repo_name"
REPO_NAME_LOC            = "profiles" + "/" + REPO_NAME_FILE

PORTAGE_PACKAGE_ATOM     = "sys-apps/portage"
LIBC_PACKAGE_ATOM        = "virtual/libc"

INCREMENTALS             = ("USE", "USE_EXPAND", "USE_EXPAND_HIDDEN",
                           "FEATURES", "ACCEPT_KEYWORDS",
                           "CONFIG_PROTECT_MASK", "CONFIG_PROTECT",
                           "PRELINK_PATH", "PRELINK_PATH_MASK",
                           "PROFILE_ONLY_VARIABLES","NO_AUTO_FLAG",
                           "MULTILIB_BINARIES")
EBUILD_PHASES            = ("setup", "unpack", "prepare", "configure",
                           "compile", "test", "install",
                           "package", "preinst", "postinst","prerm", "postrm",
                           "nofetch", "config", "info", "other")

EAPI                     = 3

HASHING_BLOCKSIZE        = 32768
MANIFEST1_HASH_FUNCTIONS = ("MD5", "SHA256", "RMD160")
MANIFEST2_HASH_FUNCTIONS = ("SHA1", "SHA256", "RMD160")

MANIFEST1_REQUIRED_HASH  = "MD5"
MANIFEST2_REQUIRED_HASH  = "SHA1"

MANIFEST2_IDENTIFIERS    = ("AUX", "MISC", "DIST", "EBUILD")
# ===========================================================================
# END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANTS -- END OF CONSTANT
# ===========================================================================
