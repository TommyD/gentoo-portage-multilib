#! /usr/bin/env python
# $Id: setup.py 3483 2006-06-10 21:40:40Z genone $

from os import chdir, stat
from distutils.core import setup, Extension

setup (# Distribution meta-data
        name = "bsd-chflags",
        version = "0.1",
        description = "",
        author = "Stephen Bennett",
        author_email = "spb@gentoo.org",
       	license = "",
        long_description = \
         '''''',
        ext_modules = [ Extension(
                            "chflags",
                            ["chflags.c"],
                            libraries=[],
                        ) 
                      ],
        url = "",
      )

