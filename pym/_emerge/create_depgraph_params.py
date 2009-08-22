# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import logging
from portage.util import writemsg_level

def create_depgraph_params(myopts, myaction):
	#configure emerge engine parameters
	#
	# self:      include _this_ package regardless of if it is merged.
	# selective: exclude the package if it is merged
	# recurse:   go into the dependencies
	# deep:      go into the dependencies of already merged packages
	# empty:     pretend nothing is merged
	# complete:  completely account for all known dependencies
	# remove:    build graph for use in removing packages
	myparams = {"recurse" : True}

	if myaction == "remove":
		myparams["remove"] = True
		myparams["complete"] = True
		return myparams

	if "--update" in myopts or \
		"--newuse" in myopts or \
		"--reinstall" in myopts or \
		"--noreplace" in myopts or \
		myopts.get("--selective", "n") != "n":
		myparams["selective"] = True
	if "--emptytree" in myopts:
		myparams["empty"] = True
		myparams.pop("selective", None)
	if "--nodeps" in myopts:
		myparams.pop("recurse", None)
	if "--deep" in myopts:
		myparams["deep"] = myopts["--deep"]
	if "--complete-graph" in myopts:
		myparams["complete"] = True
	if myopts.get("--selective") == "n":
		# --selective=n can be used to remove selective
		# behavior that may have been implied by some
		# other option like --update.
		myparams.pop("selective", None)

	if '--debug' in myopts:
		writemsg_level('\n\nmyparams %s\n\n' % myparams,
			noiselevel=-1, level=logging.DEBUG)

	return myparams

