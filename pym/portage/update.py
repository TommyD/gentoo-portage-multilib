# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import codecs
import errno
import re
import sys

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.dep:dep_getkey,get_operator,isvalidatom,isjustname,remove_slot',
	'portage.util:ConfigProtect,grabfile,new_protect_filename,' + \
		'normalize_path,write_atomic,writemsg',
	'portage.versions:ververify'
)

from portage.const import USER_CONFIG_PATH
from portage.exception import DirectoryNotFound, PortageException
from portage.localization import _

ignored_dbentries = ("CONTENTS", "environment.bz2")

def update_dbentry(update_cmd, mycontent):
	if update_cmd[0] == "move":
		old_value, new_value = update_cmd[1], update_cmd[2]
		if old_value in mycontent:
			old_value = re.escape(old_value);
			mycontent = re.sub(old_value+"(:|$|\\s)", new_value+"\\1", mycontent)
			def myreplace(matchobj):
				# Strip slot and * operator if necessary
				# so that ververify works.
				ver = remove_slot(matchobj.group(2))
				ver = ver.rstrip("*")
				if ververify(ver):
					return "%s-%s" % (new_value, matchobj.group(2))
				else:
					return "".join(matchobj.groups())
			mycontent = re.sub("(%s-)(\\S*)" % old_value, myreplace, mycontent)
	elif update_cmd[0] == "slotmove" and get_operator(update_cmd[1]) is None:
		pkg, origslot, newslot = update_cmd[1:]
		old_value = "%s:%s" % (pkg, origslot)
		if old_value in mycontent:
			old_value = re.escape(old_value)
			new_value = "%s:%s" % (pkg, newslot)
			mycontent = re.sub(old_value+"($|\\s)", new_value+"\\1", mycontent)
	return mycontent

def update_dbentries(update_iter, mydata):
	"""Performs update commands and returns a
	dict containing only the updated items."""
	updated_items = {}
	for k, mycontent in mydata.iteritems():
		if k not in ignored_dbentries:
			orig_content = mycontent
			for update_cmd in update_iter:
				mycontent = update_dbentry(update_cmd, mycontent)
			if mycontent != orig_content:
				updated_items[k] = mycontent
	return updated_items

def fixdbentries(update_iter, dbdir):
	"""Performs update commands which result in search and replace operations
	for each of the files in dbdir (excluding CONTENTS and environment.bz2).
	Returns True when actual modifications are necessary and False otherwise."""
	mydata = {}
	for myfile in [f for f in os.listdir(dbdir) if f not in ignored_dbentries]:
		file_path = os.path.join(dbdir, myfile)
		mydata[myfile] = codecs.open(_unicode_encode(file_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace').read()
	updated_items = update_dbentries(update_iter, mydata)
	for myfile, mycontent in updated_items.iteritems():
		file_path = os.path.join(dbdir, myfile)
		write_atomic(file_path, mycontent)
	return len(updated_items) > 0

def grab_updates(updpath, prev_mtimes=None):
	"""Returns all the updates from the given directory as a sorted list of
	tuples, each containing (file_path, statobj, content).  If prev_mtimes is
	given then only updates with differing mtimes are considered."""
	try:
		mylist = os.listdir(updpath)
	except OSError, oe:
		if oe.errno == errno.ENOENT:
			raise DirectoryNotFound(updpath)
		raise
	if prev_mtimes is None:
		prev_mtimes = {}
	# validate the file name (filter out CVS directory, etc...)
	mylist = [myfile for myfile in mylist if len(myfile) == 7 and myfile[1:3] == "Q-"]
	if len(mylist) == 0:
		return []
	
	# update names are mangled to make them sort properly
	mylist = [myfile[3:]+"-"+myfile[:2] for myfile in mylist]
	mylist.sort()
	mylist = [myfile[5:]+"-"+myfile[:4] for myfile in mylist]

	update_data = []
	for myfile in mylist:
		file_path = os.path.join(updpath, myfile)
		mystat = os.stat(file_path)
		if file_path not in prev_mtimes or \
		long(prev_mtimes[file_path]) != long(mystat.st_mtime):
			content = codecs.open(_unicode_encode(file_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'], errors='replace'
				).read()
			update_data.append((file_path, mystat, content))
	return update_data

def parse_updates(mycontent):
	"""Valid updates are returned as a list of split update commands."""
	myupd = []
	errors = []
	mylines = mycontent.splitlines()
	for myline in mylines:
		mysplit = myline.split()
		if len(mysplit) == 0:
			continue
		if mysplit[0] not in ("move", "slotmove"):
			errors.append(_("ERROR: Update type not recognized '%s'") % myline)
			continue
		if mysplit[0] == "move":
			if len(mysplit) != 3:
				errors.append(_("ERROR: Update command invalid '%s'") % myline)
				continue
			orig_value, new_value = mysplit[1], mysplit[2]
			for cp in (orig_value, new_value):
				if not (isvalidatom(cp) and isjustname(cp)):
					errors.append(
						_("ERROR: Malformed update entry '%s'") % myline)
					continue
		if mysplit[0] == "slotmove":
			if len(mysplit)!=4:
				errors.append(_("ERROR: Update command invalid '%s'") % myline)
				continue
			pkg, origslot, newslot = mysplit[1], mysplit[2], mysplit[3]
			if not isvalidatom(pkg):
				errors.append(_("ERROR: Malformed update entry '%s'") % myline)
				continue
		
		# The list of valid updates is filtered by continue statements above.
		myupd.append(mysplit)
	return myupd, errors

def update_config_files(config_root, protect, protect_mask, update_iter):
	"""Perform global updates on /etc/portage/package.*.
	config_root - location of files to update
	protect - list of paths from CONFIG_PROTECT
	protect_mask - list of paths from CONFIG_PROTECT_MASK
	update_iter - list of update commands as returned from parse_updates()"""

	config_root = normalize_path(config_root)
	update_files = {}
	file_contents = {}
	myxfiles = ["package.mask", "package.unmask", \
		"package.keywords", "package.use"]
	myxfiles += [os.path.join("profile", x) for x in myxfiles]
	abs_user_config = os.path.join(config_root, USER_CONFIG_PATH)
	recursivefiles = []
	for x in myxfiles:
		config_file = os.path.join(abs_user_config, x)
		if os.path.isdir(config_file):
			for parent, dirs, files in os.walk(config_file):
				for y in dirs:
					try:
						y = _unicode_decode(y,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeDecodeError:
						dirs.remove(y)
						continue
					if y.startswith("."):
						dirs.remove(y)
				for y in files:
					try:
						y = _unicode_decode(y,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeDecodeError:
						continue
					if y.startswith("."):
						continue
					recursivefiles.append(
						os.path.join(parent, y)[len(abs_user_config) + 1:])
		else:
			recursivefiles.append(x)
	myxfiles = recursivefiles
	for x in myxfiles:
		try:
			file_contents[x] = codecs.open(
				_unicode_encode(os.path.join(abs_user_config, x),
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'],
				errors='replace').readlines()
		except IOError:
			if file_contents.has_key(x):
				del file_contents[x]
			continue

	# update /etc/portage/packages.*
	ignore_line_re = re.compile(r'^#|^\s*$')
	for update_cmd in update_iter:
		for x, contents in file_contents.iteritems():
			for pos, line in enumerate(contents):
				if ignore_line_re.match(line):
					continue
				atom = line.split()[0]
				if atom.startswith("-"):
					# package.mask supports incrementals
					atom = atom[1:]
				if not isvalidatom(atom):
					continue
				new_atom = update_dbentry(update_cmd, atom)
				if atom != new_atom:
					contents[pos] = line.replace(atom, new_atom)
					update_files[x] = 1
					sys.stdout.write("p")
					sys.stdout.flush()

	protect_obj = ConfigProtect(
		config_root, protect, protect_mask)
	for x in update_files:
		updating_file = os.path.join(abs_user_config, x)
		if protect_obj.isprotected(updating_file):
			updating_file = new_protect_filename(updating_file)
		try:
			write_atomic(updating_file, "".join(file_contents[x]))
		except PortageException, e:
			writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
			writemsg(_("!!! An error occured while updating a config file:") + \
				" '%s'\n" % updating_file, noiselevel=-1)
			continue

def dep_transform(mydep, oldkey, newkey):
	if dep_getkey(mydep) == oldkey:
		return mydep.replace(oldkey, newkey, 1)
	return mydep
