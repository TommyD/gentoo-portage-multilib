#! /usr/bin/env python2.2

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

