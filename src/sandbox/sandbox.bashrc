# Copyright (C) 2001 The Leaf, http://www.theleaf.be
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@theleaf.be>
# $Header$
source /etc/profile
export LD_PRELOAD="$SANDBOX_LIB"
alias make="make LD_PRELOAD=$SANDBOX_LIB"
alias su="su -c '/bin/bash -rcfile $SANDBOX_DIR/sandbox.bashrc'"
