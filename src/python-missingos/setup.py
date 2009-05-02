#!/usr/bin/python
# $Id: setup.py 3483 2006-06-10 21:40:40Z genone $

from os import chdir, stat
from distutils.core import setup, Extension

setup (# Distribution meta-data
        name = "python-missingos",
        version = "0.2",
        description = "",
        author = "Jonathon D Nelson",
        author_email = "jnelson@gentoo.org",
       	license = "",
        long_description = \
         '''''',
        ext_modules = [ Extension(
                            "missingos",
                            ["missingos.c"],
                            libraries=[],
                        ) 
                      ],
        url = "",
      )

