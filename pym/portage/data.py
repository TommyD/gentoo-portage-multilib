# data.py -- Calculated/Discovered Data Values
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, sys, pwd, grp
from portage.util import writemsg
from portage.output import green,red
from portage.output import create_color_func
bad = create_color_func("BAD")

ostype=os.uname()[0]

userland = None
lchown = getattr(os, "lchown", None)
os.environ.setdefault("XARGS", "xargs")
if ostype == "Linux" or \
	ostype.lower().startswith("gnu") or \
	ostype.lower().endswith("gnu"):
	userland="GNU"
elif ostype == "Darwin":
	userland="Darwin"
elif ostype.endswith("BSD") or ostype =="DragonFly":
	userland="BSD"

if not lchown:
		try:
			import missingos
			lchown = missingos.lchown
		except ImportError:
			def lchown(*pos_args, **key_args):
				writemsg(red("!!!") + " It seems that os.lchown does not" + \
					" exist.  Please rebuild python.\n", noiselevel=-1)
			lchown()

def portage_group_warning():
	warn_prefix = bad("*** WARNING ***  ")
	mylines = [
		"For security reasons, only system administrators should be",
		"allowed in the portage group.  Untrusted users or processes",
		"can potentially exploit the portage group for attacks such as",
		"local privilege escalation."
	]
	for x in mylines:
		writemsg(warn_prefix, noiselevel=-1)
		writemsg(x, noiselevel=-1)
		writemsg("\n", noiselevel=-1)
	writemsg("\n", noiselevel=-1)

# Portage has 3 security levels that depend on the uid and gid of the main
# process and are assigned according to the following table:
#
# Privileges  secpass  uid    gid
# normal      0        any    any
# group       1        any    portage_gid
# super       2        0      any
#
# If the "wheel" group does not exist then wheelgid falls back to 0.
# If the "portage" group does not exist then portage_uid falls back to wheelgid.

secpass=0

uid=os.getuid()
wheelgid=0

if uid==0:
	secpass=2
try:
	wheelgid=grp.getgrnam("wheel")[2]
except KeyError:
	pass

#Discover the uid and gid of the portage user/group
try:
	portage_uid=pwd.getpwnam("portage")[2]
	portage_gid=grp.getgrnam("portage")[2]
	if secpass < 1 and portage_gid in os.getgroups():
		secpass=1
except KeyError:
	portage_uid=0
	portage_gid=0
	writemsg("\n")
	writemsg(  red("portage: 'portage' user or group missing. Please update baselayout\n"))
	writemsg(  red("         and merge portage user(250) and group(250) into your passwd\n"))
	writemsg(  red("         and group files. Non-root compilation is disabled until then.\n"))
	writemsg(      "         Also note that non-root/wheel users will need to be added to\n")
	writemsg(      "         the portage group to do portage commands.\n")
	writemsg("\n")
	writemsg(      "         For the defaults, line 1 goes into passwd, and 2 into group.\n")
	writemsg(green("         portage:x:250:250:portage:/var/tmp/portage:/bin/false\n"))
	writemsg(green("         portage::250:portage\n"))
	writemsg("\n")
	portage_group_warning()

userpriv_groups = [portage_gid]
if secpass >= 2:
	# Get a list of group IDs for the portage user.  Do not use grp.getgrall()
	# since it is known to trigger spurious SIGPIPE problems with nss_ldap.
	from commands import getstatusoutput
	mystatus, myoutput = getstatusoutput("id -G portage")
	if mystatus == os.EX_OK:
		for x in myoutput.split():
			try:
				userpriv_groups.append(int(x))
			except ValueError:
				pass
			del x
		userpriv_groups = list(set(userpriv_groups))
	del getstatusoutput, mystatus, myoutput
