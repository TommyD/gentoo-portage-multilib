# Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@uwyn.com>
default: sandbox_muttbug libsandbox_muttbug.so libsandbox_emacsbug.so

sandbox: sandbox_muttbug.c
	gcc -Wall -O2 -o sandbox_muttbug sandbox_muttbug.c

libsandbox_muttbug.so: libsandbox_muttbug.c
	gcc -Wall -O2 -ldl --shared -o libsandbox_muttbug.so libsandbox_muttbug.c

libsandbox_emacsbug.so: libsandbox_emacsbug.c
	gcc -Wall -O2 -ldl --shared -o libsandbox_emacsbug.so libsandbox_emacsbug.c

clean:
	rm sandbox_muttbug
	rm libsandbox_muttbug.so
	rm libsandbox_emacsbug.so
