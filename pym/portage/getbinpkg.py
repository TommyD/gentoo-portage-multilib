# getbinpkg.py -- Portage binary-package helper functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.output import colorize
from portage.cache.mappings import slot_dict_class
import portage.xpak
import HTMLParser
import sys
import os
import socket
import time
import tempfile
import base64
import urllib2

try:
	import cPickle as pickle
except ImportError:
	import pickle

try:
	import ftplib
except ImportError, e:
	sys.stderr.write(colorize("BAD","!!! CANNOT IMPORT FTPLIB: ")+str(e)+"\n")

try:
	import httplib
except ImportError, e:
	sys.stderr.write(colorize("BAD","!!! CANNOT IMPORT HTTPLIB: ")+str(e)+"\n")

def make_metadata_dict(data):
	myid,myglob = data
	
	mydict = {}
	for x in portage.xpak.getindex_mem(myid):
		mydict[x] = portage.xpak.getitem(data,x)

	return mydict

class ParseLinks(HTMLParser.HTMLParser):
	"""Parser class that overrides HTMLParser to grab all anchors from an html
	page and provide suffix and prefix limitors"""
	def __init__(self):
		self.PL_anchors = []
		HTMLParser.HTMLParser.__init__(self)

	def get_anchors(self):
		return self.PL_anchors
		
	def get_anchors_by_prefix(self,prefix):
		newlist = []
		for x in self.PL_anchors:
			if x.startswith(prefix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist
		
	def get_anchors_by_suffix(self,suffix):
		newlist = []
		for x in self.PL_anchors:
			if x.endswith(suffix):
				if x not in newlist:
					newlist.append(x[:])
		return newlist
		
	def	handle_endtag(self,tag):
		pass

	def	handle_starttag(self,tag,attrs):
		if tag == "a":
			for x in attrs:
				if x[0] == 'href':
					if x[1] not in self.PL_anchors:
						self.PL_anchors.append(urllib2.unquote(x[1]))


def create_conn(baseurl,conn=None):
	"""(baseurl,conn) --- Takes a protocol://site:port/address url, and an
	optional connection. If connection is already active, it is passed on.
	baseurl is reduced to address and is returned in tuple (conn,address)"""

	parts = baseurl.split("://",1)
	if len(parts) != 2:
		raise ValueError("Provided URL does not " + \
			"contain protocol identifier. '%s'" % baseurl)
	protocol,url_parts = parts
	del parts

	url_parts = url_parts.split("/")
	host = url_parts[0]
	if len(url_parts) < 2:
		address = "/"
	else:
		address = "/"+"/".join(url_parts[1:])
	del url_parts

	userpass_host = host.split("@",1)
	if len(userpass_host) == 1:
		host = userpass_host[0]
		userpass = ["anonymous"]
	else:
		host = userpass_host[1]
		userpass = userpass_host[0].split(":")
	del userpass_host

	if len(userpass) > 2:
		raise ValueError("Unable to interpret username/password provided.")
	elif len(userpass) == 2:
		username = userpass[0]
		password = userpass[1]
	elif len(userpass) == 1:
		username = userpass[0]
		password = None
	del userpass

	http_headers = {}
	http_params = {}
	if username and password:
		http_headers = {
			"Authorization": "Basic %s" %
			  base64.encodestring("%s:%s" % (username, password)).replace(
			    "\012",
			    ""
			  ),
		}

	if not conn:
		if protocol == "https":
			conn = httplib.HTTPSConnection(host)
		elif protocol == "http":
			conn = httplib.HTTPConnection(host)
		elif protocol == "ftp":
			passive = 1
			if(host[-1] == "*"):
				passive = 0
				host = host[:-1]
			conn = ftplib.FTP(host)
			if password:
				conn.login(username,password)
			else:
				sys.stderr.write(colorize("WARN",
					" * No password provided for username")+" '%s'" % \
					(username,) + "\n\n")
				conn.login(username)
			conn.set_pasv(passive)
			conn.set_debuglevel(0)
		elif protocol == "sftp":
			try:
				import paramiko
			except ImportError:
				raise NotImplementedError(
					"paramiko must be installed for sftp support")
			t = paramiko.Transport(host)
			t.connect(username=username, password=password)
			conn = paramiko.SFTPClient.from_transport(t)
		else:
			raise NotImplementedError, "%s is not a supported protocol." % protocol

	return (conn,protocol,address, http_params, http_headers)

def make_ftp_request(conn, address, rest=None, dest=None):
	"""(conn,address,rest) --- uses the conn object to request the data
	from address and issuing a rest if it is passed."""
	try:
	
		if dest:
			fstart_pos = dest.tell()
	
		conn.voidcmd("TYPE I")
		fsize = conn.size(address)

		if (rest != None) and (rest < 0):
			rest = fsize+int(rest)
		if rest < 0:
			rest = 0

		if rest != None:
			mysocket = conn.transfercmd("RETR "+str(address), rest)
		else:
			mysocket = conn.transfercmd("RETR "+str(address))

		mydata = ""
		while 1:
			somedata = mysocket.recv(8192)
			if somedata:
				if dest:
					dest.write(somedata)
				else:
					mydata = mydata + somedata
			else:
				break

		if dest:
			data_size = fstart_pos - dest.tell()
		else:
			data_size = len(mydata)

		mysocket.close()
		conn.voidresp()
		conn.voidcmd("TYPE A")

		return mydata,not (fsize==data_size),""

	except ValueError, e:
		return None,int(str(e)[:4]),str(e)
	

def make_http_request(conn, address, params={}, headers={}, dest=None):
	"""(conn,address,params,headers) --- uses the conn object to request
	the data from address, performing Location forwarding and using the
	optional params and headers."""

	rc = 0
	response = None
	while (rc == 0) or (rc == 301) or (rc == 302):
		try:
			if (rc != 0):
				conn,ignore,ignore,ignore,ignore = create_conn(address)
			conn.request("GET", address, params, headers)
		except SystemExit, e:
			raise
		except Exception, e:
			return None,None,"Server request failed: "+str(e)
		response = conn.getresponse()
		rc = response.status

		# 301 means that the page address is wrong.
		if ((rc == 301) or (rc == 302)):
			ignored_data = response.read()
			del ignored_data
			for x in str(response.msg).split("\n"):
				parts = x.split(": ",1)
				if parts[0] == "Location":
					if (rc == 301):
						sys.stderr.write(colorize("BAD",
							"Location has moved: ") + str(parts[1]) + "\n")
					if (rc == 302):
						sys.stderr.write(colorize("BAD",
							"Location has temporarily moved: ") + \
							str(parts[1]) + "\n")
					address = parts[1]
					break
	
	if (rc != 200) and (rc != 206):
		return None,rc,"Server did not respond successfully ("+str(response.status)+": "+str(response.reason)+")"

	if dest:
		dest.write(response.read())
		return "",0,""

	return response.read(),0,""


def match_in_array(array, prefix="", suffix="", match_both=1, allow_overlap=0):
	myarray = []
	
	if not (prefix and suffix):
		match_both = 0
		
	for x in array:
		add_p = 0
		if prefix and (len(x) >= len(prefix)) and (x[:len(prefix)] == prefix):
			add_p = 1

		if match_both:
			if prefix and not add_p: # Require both, but don't have first one.
				continue
		else:
			if add_p:     # Only need one, and we have it.
				myarray.append(x[:])
				continue

		if not allow_overlap: # Not allow to overlap prefix and suffix
			if len(x) >= (len(prefix)+len(suffix)):
				pass
			else:
				continue          # Too short to match.
		else:
			pass                      # Do whatever... We're overlapping.
		
		if suffix and (len(x) >= len(suffix)) and (x[-len(suffix):] == suffix):
			myarray.append(x)   # It matches
		else:
			continue            # Doesn't match.

	return myarray
			


def dir_get_list(baseurl,conn=None):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	listing = None
	if protocol in ["http","https"]:
		if not address.endswith("/"):
			# http servers can return a 400 error here
			# if the address doesn't end with a slash.
			address += "/"
		page,rc,msg = make_http_request(conn,address,params,headers)
		
		if page:
			parser = ParseLinks()
			parser.feed(page)
			del page
			listing = parser.get_anchors()
		else:
			import portage.exception
			raise portage.exception.PortageException(
				"Unable to get listing: %s %s" % (rc,msg))
	elif protocol in ["ftp"]:
		if address[-1] == '/':
			olddir = conn.pwd()
			conn.cwd(address)
			listing = conn.nlst()
			conn.cwd(olddir)
			del olddir
		else:
			listing = conn.nlst(address)
	elif protocol == "sftp":
		listing = conn.listdir(address)
	else:
		raise TypeError("Unknown protocol. '%s'" % protocol)

	if not keepconnection:
		conn.close()

	return listing

def file_get_metadata(baseurl,conn=None, chunk_size=3000):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	if protocol in ["http","https"]:
		headers["Range"] = "bytes=-"+str(chunk_size)
		data,rc,msg = make_http_request(conn, address, params, headers)
	elif protocol in ["ftp"]:
		data,rc,msg = make_ftp_request(conn, address, -chunk_size)
	elif protocol == "sftp":
		f = conn.open(address)
		try:
			f.seek(-chunk_size, 2)
			data = f.read()
		finally:
			f.close()
	else:
		raise TypeError("Unknown protocol. '%s'" % protocol)
	
	if data:
		xpaksize = portage.xpak.decodeint(data[-8:-4])
		if (xpaksize+8) > chunk_size:
			myid = file_get_metadata(baseurl, conn, (xpaksize+8))
			if not keepconnection:
				conn.close()
			return myid
		else:
			xpak_data = data[len(data)-(xpaksize+8):-8]
		del data

		myid = portage.xpak.xsplit_mem(xpak_data)
		if not myid:
			myid = None,None
		del xpak_data
	else:
		myid = None,None

	if not keepconnection:
		conn.close()

	return myid


def file_get(baseurl,dest,conn=None,fcmd=None):
	"""(baseurl,dest,fcmd=) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://[user[:pass]@]<site>[:port]<path>"""

	if not fcmd:
		return file_get_lib(baseurl,dest,conn)

	variables = {
		"DISTDIR": dest,
		"URI":     baseurl,
		"FILE":    os.path.basename(baseurl)
	}
	import shlex, StringIO
	from portage.util import varexpand
	from portage.process import spawn
	lexer = shlex.shlex(StringIO.StringIO(fcmd), posix=True)
	lexer.whitespace_split = True
	myfetch = [varexpand(x, mydict=variables) for x in lexer]
	fd_pipes= {
		0:sys.stdin.fileno(),
		1:sys.stdout.fileno(),
		2:sys.stdout.fileno()
	}
	retval = spawn(myfetch, env=os.environ.copy(), fd_pipes=fd_pipes)
	if retval != os.EX_OK:
		sys.stderr.write("Fetcher exited with a failure condition.\n")
		return 0
	return 1

def file_get_lib(baseurl,dest,conn=None):
	"""(baseurl[,connection]) -- Takes a base url to connect to and read from.
	URL should be in the for <proto>://<site>[:port]<path>
	Connection is used for persistent connection instances."""

	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	conn,protocol,address,params,headers = create_conn(baseurl, conn)

	sys.stderr.write("Fetching '"+str(os.path.basename(address)+"'\n"))
	if protocol in ["http","https"]:
		data,rc,msg = make_http_request(conn, address, params, headers, dest=dest)
	elif protocol in ["ftp"]:
		data,rc,msg = make_ftp_request(conn, address, dest=dest)
	elif protocol == "sftp":
		rc = 0
		try:
			f = conn.open(address)
		except SystemExit:
			raise
		except Exception:
			rc = 1
		else:
			try:
				if dest:
					bufsize = 8192
					while True:
						data = f.read(bufsize)
						if not data:
							break
						dest.write(data)
			finally:
				f.close()
	else:
		raise TypeError("Unknown protocol. '%s'" % protocol)
	
	if not keepconnection:
		conn.close()

	return rc


def dir_get_metadata(baseurl, conn=None, chunk_size=3000, verbose=1, usingcache=1, makepickle=None):
	"""(baseurl,conn,chunk_size,verbose) -- 
	"""
	if not conn:
		keepconnection = 0
	else:
		keepconnection = 1

	cache_path = "/var/cache/edb"
	metadatafilename = os.path.join(cache_path, 'remote_metadata.pickle')

	if makepickle is None:
		makepickle = "/var/cache/edb/metadata.idx.most_recent"

	try:
		conn, protocol, address, params, headers = create_conn(baseurl, conn)
	except socket.error, e:
		# ftplib.FTP(host) can raise errors like this:
		#   socket.error: (111, 'Connection refused')
		sys.stderr.write("!!! %s\n" % (e,))
		return {}

	out = sys.stdout
	try:
		metadatafile = open(metadatafilename, 'rb')
		metadata = pickle.load(metadatafile)
		out.write("Loaded metadata pickle.\n")
		out.flush()
		metadatafile.close()
	except (pickle.UnpicklingError, OSError, IOError, EOFError):
		metadata = {}
	if baseurl not in metadata:
		metadata[baseurl]={}
	if "indexname" not in metadata[baseurl]:
		metadata[baseurl]["indexname"]=""
	if "timestamp" not in metadata[baseurl]:
		metadata[baseurl]["timestamp"]=0
	if "unmodified" not in metadata[baseurl]:
		metadata[baseurl]["unmodified"]=0
	if "data" not in metadata[baseurl]:
		metadata[baseurl]["data"]={}

	if not os.access(cache_path, os.W_OK):
		sys.stderr.write("!!! Unable to write binary metadata to disk!\n")
		sys.stderr.write("!!! Permission denied: '%s'\n" % cache_path)
		return metadata[baseurl]["data"]

	import portage.exception
	try:
		filelist = dir_get_list(baseurl, conn)
	except portage.exception.PortageException, e:
		sys.stderr.write("!!! Error connecting to '%s'.\n" % baseurl)
		sys.stderr.write("!!! %s\n" % str(e))
		del e
		return metadata[baseurl]["data"]
	tbz2list = match_in_array(filelist, suffix=".tbz2")
	metalist = match_in_array(filelist, prefix="metadata.idx")
	del filelist
	
	# Determine if our metadata file is current.
	metalist.sort()
	metalist.reverse() # makes the order new-to-old.
	for mfile in metalist:
		if usingcache and \
		   ((metadata[baseurl]["indexname"] != mfile) or \
			  (metadata[baseurl]["timestamp"] < int(time.time()-(60*60*24)))):
			# Try to download new cache until we succeed on one.
			data=""
			for trynum in [1,2,3]:
				mytempfile = tempfile.TemporaryFile()
				try:
					file_get(baseurl+"/"+mfile, mytempfile, conn)
					if mytempfile.tell() > len(data):
						mytempfile.seek(0)
						data = mytempfile.read()
				except ValueError, e:
					sys.stderr.write("--- "+str(e)+"\n")
					if trynum < 3:
						sys.stderr.write("Retrying...\n")
					sys.stderr.flush()
					mytempfile.close()
					continue
				if match_in_array([mfile],suffix=".gz"):
					out.write("gzip'd\n")
					out.flush()
					try:
						import gzip
						mytempfile.seek(0)
						gzindex = gzip.GzipFile(mfile[:-3],'rb',9,mytempfile)
						data = gzindex.read()
					except SystemExit, e:
						raise
					except Exception, e:
						mytempfile.close()
						sys.stderr.write("!!! Failed to use gzip: "+str(e)+"\n")
						sys.stderr.flush()
					mytempfile.close()
				try:
					metadata[baseurl]["data"] = pickle.loads(data)
					del data
					metadata[baseurl]["indexname"] = mfile
					metadata[baseurl]["timestamp"] = int(time.time())
					metadata[baseurl]["modified"]  = 0 # It's not, right after download.
					out.write("Pickle loaded.\n")
					out.flush()
					break
				except SystemExit, e:
					raise
				except Exception, e:
					sys.stderr.write("!!! Failed to read data from index: "+str(mfile)+"\n")
					sys.stderr.write("!!! "+str(e)+"\n")
					sys.stderr.flush()
			try:
				metadatafile = open(metadatafilename, 'wb')
				pickle.dump(metadata,metadatafile)
				metadatafile.close()
			except SystemExit, e:
				raise
			except Exception, e:
				sys.stderr.write("!!! Failed to write binary metadata to disk!\n")
				sys.stderr.write("!!! "+str(e)+"\n")
				sys.stderr.flush()
			break
	# We may have metadata... now we run through the tbz2 list and check.

	class CacheStats(object):
		from time import time
		def __init__(self, out):
			self.misses = 0
			self.hits = 0
			self.last_update = 0
			self.out = out
			self.min_display_latency = 0.2
		def update(self):
			cur_time = self.time()
			if cur_time - self.last_update >= self.min_display_latency:
				self.last_update = cur_time
				self.display()
		def display(self):
			self.out.write("\r"+colorize("WARN",
				"cache miss: '"+str(self.misses)+"'") + \
				" --- "+colorize("GOOD","cache hit: '"+str(self.hits)+"'"))
			self.out.flush()

	cache_stats = CacheStats(out)
	have_tty = out.isatty()
	if have_tty:
		cache_stats.display()
	binpkg_filenames = set()
	for x in tbz2list:
		x = os.path.basename(x)
		binpkg_filenames.add(x)
		if x not in metadata[baseurl]["data"]:
			cache_stats.misses += 1
			if have_tty:
				cache_stats.update()
			metadata[baseurl]["modified"] = 1
			myid = None
			for retry in xrange(3):
				try:
					myid = file_get_metadata(
						"/".join((baseurl.rstrip("/"), x.lstrip("/"))),
						conn, chunk_size)
					break
				except httplib.BadStatusLine:
					# Sometimes this error is thrown from conn.getresponse() in
					# make_http_request().  The docstring for this error in
					# httplib.py says "Presumably, the server closed the
					# connection before sending a valid response".
					conn, protocol, address, params, headers = create_conn(
						baseurl)
				except httplib.ResponseNotReady:
					# With some http servers this error is known to be thrown
					# from conn.getresponse() in make_http_request() when the
					# remote file does not have appropriate read permissions.
					# Maybe it's possible to recover from this exception in
					# cases though, so retry.
					conn, protocol, address, params, headers = create_conn(
						baseurl)

			if myid and myid[0]:
				metadata[baseurl]["data"][x] = make_metadata_dict(myid)
			elif verbose:
				sys.stderr.write(colorize("BAD",
					"!!! Failed to retrieve metadata on: ")+str(x)+"\n")
				sys.stderr.flush()
		else:
			cache_stats.hits += 1
			if have_tty:
				cache_stats.update()
	cache_stats.display()
	# Cleanse stale cache for files that don't exist on the server anymore.
	stale_cache = set(metadata[baseurl]["data"]).difference(binpkg_filenames)
	if stale_cache:
		for x in stale_cache:
			del metadata[baseurl]["data"][x]
		metadata[baseurl]["modified"] = 1
	del stale_cache
	del binpkg_filenames
	out.write("\n")
	out.flush()

	try:
		if "modified" in metadata[baseurl] and metadata[baseurl]["modified"]:
			metadata[baseurl]["timestamp"] = int(time.time())
			metadatafile = open(metadatafilename, 'wb')
			pickle.dump(metadata,metadatafile)
			metadatafile.close()
		if makepickle:
			metadatafile = open(makepickle, 'wb')
			pickle.dump(metadata[baseurl]["data"],metadatafile)
			metadatafile.close()
	except SystemExit, e:
		raise
	except Exception, e:
		sys.stderr.write("!!! Failed to write binary metadata to disk!\n")
		sys.stderr.write("!!! "+str(e)+"\n")
		sys.stderr.flush()

	if not keepconnection:
		conn.close()
	
	return metadata[baseurl]["data"]

def _cmp_cpv(d1, d2):
	cpv1 = d1["CPV"]
	cpv2 = d2["CPV"]
	if cpv1 > cpv2:
		return 1
	elif cpv1 == cpv2:
		return 0
	else:
		return -1

class PackageIndex(object):

	def __init__(self,
		allowed_pkg_keys=None,
		default_header_data=None,
		default_pkg_data=None,
		inherited_keys=None,
		translated_keys=None):

		self._pkg_slot_dict = None
		if allowed_pkg_keys is not None:
			self._pkg_slot_dict = slot_dict_class(allowed_pkg_keys)

		self._default_header_data = default_header_data
		self._default_pkg_data = default_pkg_data
		self._inherited_keys = inherited_keys
		self._write_translation_map = {}
		self._read_translation_map = {}
		if translated_keys:
			self._write_translation_map.update(translated_keys)
			self._read_translation_map.update(((y, x) for (x, y) in translated_keys))
		self.header = {}
		if self._default_header_data:
			self.header.update(self._default_header_data)
		self.packages = []
		self.modified = True

	def _readpkgindex(self, pkgfile, pkg_entry=True):

		allowed_keys = None
		if self._pkg_slot_dict is None or not pkg_entry:
			d = {}
		else:
			d = self._pkg_slot_dict()
			allowed_keys = d.allowed_keys

		for line in pkgfile:
			line = line.rstrip("\n")
			if not line:
				break
			line = line.split(":", 1)
			if not len(line) == 2:
				continue
			k, v = line
			if v:
				v = v[1:]
			k = self._read_translation_map.get(k, k)
			if allowed_keys is not None and \
				k not in allowed_keys:
				continue
			d[k] = v
		return d

	def _writepkgindex(self, pkgfile, items):
		for k, v in items:
			pkgfile.write("%s: %s\n" % \
				(self._write_translation_map.get(k, k), v))
		pkgfile.write("\n")

	def read(self, pkgfile):
		self.readHeader(pkgfile)
		self.readBody(pkgfile)

	def readHeader(self, pkgfile):
		self.header.update(self._readpkgindex(pkgfile, pkg_entry=False))

	def readBody(self, pkgfile):
		while True:
			d = self._readpkgindex(pkgfile)
			if not d:
				break
			mycpv = d.get("CPV")
			if not mycpv:
				continue
			if self._default_pkg_data:
				for k, v in self._default_pkg_data.iteritems():
					d.setdefault(k, v)
			if self._inherited_keys:
				for k in self._inherited_keys:
					v = self.header.get(k)
					if v is not None:
						d.setdefault(k, v)
			self.packages.append(d)

	def write(self, pkgfile):
		if self.modified:
			self.header["TIMESTAMP"] = str(long(time.time()))
			self.header["PACKAGES"] = str(len(self.packages))
		keys = self.header.keys()
		keys.sort()
		self._writepkgindex(pkgfile, [(k, self.header[k]) \
			for k in keys if self.header[k]])
		for metadata in sorted(self.packages, _cmp_cpv):
			metadata = metadata.copy()
			cpv = metadata["CPV"]
			if self._inherited_keys:
				for k in self._inherited_keys:
					v = self.header.get(k)
					if v is not None and v == metadata.get(k):
						del metadata[k]
			if self._default_pkg_data:
				for k, v in self._default_pkg_data.iteritems():
					if metadata.get(k) == v:
						metadata.pop(k, None)
			keys = metadata.keys()
			keys.sort()
			self._writepkgindex(pkgfile,
				[(k, metadata[k]) for k in keys if metadata[k]])
