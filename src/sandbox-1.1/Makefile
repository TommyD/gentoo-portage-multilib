# Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@uwyn.com>
#
# Modified 15 Apr 2002 Jon Nelson <jnelson@gentoo.org>
#  Clean up Makefile somewhat, and use make's implicit rules
#
# Modified 19 Aug 2002; Martin Schlemmer <azarah@gentoo.org>
#  Major rewrite to support new stuff
#
# Indent:  indent -kr -i2 -ts2 -sob -l80 -ss -bs -psl
#
# $Header$

CC = gcc
LD = ld
CFLAGS =
OBJ_DEFINES = -D_GNU_SOURCE -DPIC -fPIC -D_REENTRANT
LIBS =
LDFLAGS =
DESTDIR =

TARGETS = libsandbox.so sandbox

all:	$(TARGETS)

sandbox: sandbox.o sandbox_futils.o getcwd.c
	$(CC) $^ -ldl -lc -o $@

sandbox.o: sandbox.c sandbox.h
	$(CC) $(CFLAGS) -Wall -c sandbox.c

sandbox_futils.o: localdecls.h sandbox_futils.c sandbox.h
	$(CC) $(CFLAGS) -Wall -c $(OBJ_DEFINES) sandbox_futils.c

libsandbox.so: libsandbox.o sandbox_futils.o
	$(CC) $^ -shared -fPIC -ldl -lc -o $@ -nostdlib -lgcc

libsandbox.o: localdecls.h libsandbox.c canonicalize.c getcwd.c
	$(CC) $(CFLAGS) -Wall -c $(OBJ_DEFINES) libsandbox.c

localdecls.h: create-localdecls libctest.c
	./create-localdecls


install: all
	install -d -m 0755 $(DESTDIR)/lib
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/bin
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/lib
	install -m 0755 libsandbox.so $(DESTDIR)/lib
	install -m 0755 sandbox $(DESTDIR)/usr/lib/portage/bin
	install -m 0644 sandbox.bashrc $(DESTDIR)/usr/lib/portage/lib


clean:
	rm -f $(TARGETS)
	rm -f *.o *~ core
	rm -f localdecls.h


# vim:expandtab noai:cindent ai
