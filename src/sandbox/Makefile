# Copyright (C) 2001 The Leaf, http://www.theleaf.be
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@theleaf.be>
# $Header$
default: sandbox libsandbox.so

sandbox: sandbox.c
	gcc -Wall -O2 -o sandbox sandbox.c

libsandbox.so: libsandbox.c
	gcc -Wall -O2 -ldl --shared -o libsandbox.so libsandbox.c

clean:
	rm sandbox
	rm libsandbox.so
