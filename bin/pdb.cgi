#!/usr/bin/python
# pdb.cgi -- cgi to update and query local and remote portage package databases
# Copyright (C) Sept 2001, Chris Houser <chouser@bluweb.com>
# Distributed under the GNU General Public License
# $Header$

# config -- begin
dbfile = '/home/c/proj/pkgdb/gentoo'
contpattern = '/var/db/pkg/%s/CONTENTS'
# config -- end

import cgi
import portagedb

pdb = portagedb.DB(dbfile)
form = cgi.FieldStorage()
if form.has_key('contfile'):
	pkgname = None
	if form.has_key('pkgname'):
		pkgname = form['pkgname'].value
	print "Content-Type: text/plain\n"
	pdb.storestream(form['contfile'].file, pkgname)
elif form.has_key('query'):
	print "Content-Type: text/plain\n"
	pdb.doquery([form['query'].value])
else:
	print """Content-Type: text/html

<html>
	<head>
		<title>gentoo pdb form</title>
	</head>
	<body>
		<h1>gentoo pdb query form</h1>
		<form action="pdb.cgi">
			filename: <input name="query" /><br />
			<input type="submit" value="Query">
		</form>

		<h1>gentoo pdb store form</h1>
		<form action="pdb.cgi" enctype="multipart/form-data">
			package name/vers: <input name="pkgname" /><br />
			CONTENTS file:
				<input type="file" name="contfile" /><br />
			<input type="submit" value="Store">
		</form>
	</body>
</html>"""

