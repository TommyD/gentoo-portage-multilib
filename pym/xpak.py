# $Header$

# The format for a tbz2/xpak:
#
#  tbz2: tar.bz2 + xpak + (xpak_offset) + "STOP"
#  xpak: "XPAKPACK" + (index_len) + (data_len) + index + data + "XPAKSTOP"
# index: (pathname_len) + pathname + (data_offset) + (data_len)
#        index entries are concatenated end-to-end.
#  data: concatenated data chunks, end-to-end.
#
# [tarball]XPAKPACKIIIIDDDD[index][data]XPAKSTOPOOOOSTOP
#
# (integer) == encodeint(integer)  ===> 4 characters (big-endian copy)
# '+' means concatenate the fields ===> All chunks are strings

import sys,os,string
from stat import *

def addtolist(mylist,curdir):
	"""(list, dir) --- Takes an array(list) and appends all files from dir down
	the directory tree. Returns nothing. list is modified."""
	for x in os.listdir("."):
		if os.path.isdir(x):
			os.chdir(x)
			addtolist(mylist,curdir+x+"/")
			os.chdir("..")
		else:
			if curdir+x not in mylist:
				mylist.append(curdir+x)

def encodeint(myint):
	"""Takes a 4 byte integer and converts it into a string of 4 characters.
	Returns the characters in a string."""
	part1=chr((myint >> 24 ) & 0x000000ff)
	part2=chr((myint >> 16 ) & 0x000000ff)
	part3=chr((myint >> 8 ) & 0x000000ff)
	part4=chr(myint & 0x000000ff)
	return part1+part2+part3+part4

def decodeint(mystring):
	"""Takes a 4 byte string and converts it into a 4 byte integer.
	Returns an integer."""
	myint=0
	myint=myint+ord(mystring[3])
	myint=myint+(ord(mystring[2]) << 8)
	myint=myint+(ord(mystring[1]) << 16)
	myint=myint+(ord(mystring[0]) << 24)
	return myint

def xpak(rootdir,outfile=None):
	"""(rootdir,outfile) -- creates an xpak segment of the directory 'rootdir'
	and under the name 'outfile' if it is specified. Otherwise it returns the
	xpak segment."""
	origdir=os.getcwd()
	os.chdir(rootdir)
	mylist=[]

	addtolist(mylist,"")
	mylist.sort()

	#Our list index has been created
	
	indexglob=""
	indexpos=0
	dataglob=""
	datapos=0
	for x in mylist:
		a=open(x,"r")
		newglob=a.read()
		a.close()
		mydatasize=len(newglob)
		indexglob=indexglob+encodeint(len(x))+x+encodeint(datapos)+encodeint(mydatasize)
		indexpos=indexpos+4+len(x)+4+4
		dataglob=dataglob+newglob
		datapos=datapos+mydatasize
	os.chdir(origdir)
	if outfile:
		outf=open(outfile,"w")
		outf.write("XPAKPACK"+encodeint(len(indexglob))+encodeint(len(dataglob)))
		outf.write(indexglob)
		outf.write(dataglob)
		outf.write("XPAKSTOP")
		outf.close()
	else:
		myret="XPAKPACK"+encodeint(len(indexglob))+encodeint(len(dataglob))
		myret=myret+indexglob+dataglob+"XPAKSTOP"
		return myret

def xsplit(infile):
	"""(infile) -- Splits the infile into two files.
	'infile.index' contains the index segment.
	'infile.dat' contails the data segment."""
	myfile=open(infile,"r")
	mydat=myfile.read()
	myfile.close()
	if mydat[0:8]!="XPAKPACK":
		return
	if mydat[-8:]!="XPAKSTOP":
		return
	indexsize=decodeint(mydat[8:12])
	datasize=decodeint(mydat[12:16])
	myfile=open(infile+".index","w")
	myfile.write(mydat[16:indexsize+16])
	myfile.close()
	myfile=open(infile+".dat","w")
	myfile.write(mydat[indexsize+16:-8])
	myfile.close()

def getindex(infile):
	"""(infile) -- grabs the index segment from the infile and returns it."""
	myfile=open(infile,"r")
	myheader=myfile.read(16)
	if myheader[0:8]!="XPAKPACK":
		myfile.close()
		return
	indexsize=decodeint(myheader[8:12])
	myindex=myfile.read(indexsize)
	myfile.close()
	return myindex

def getboth(infile):
	"""(infile) -- grabs the index and data segments from the infile.
	Returns an array [indexSegment,dataSegment]"""
	myfile=open(infile,"r")
	myheader=myfile.read(16)
	if myheader[0:8]!="XPAKPACK":
		myfile.close()
		return
	indexsize=decodeint(myheader[8:12])
	datasize=decodeint(myheader[12:16])
	myindex=myfile.read(indexsize)
	mydata=myfile.read(datasize)
	myfile.close()
	return [myindex,mydata]

def listindex(myindex):
	"""Print to the terminal the filenames listed in the indexglob passed in."""
	for x in getindex(myindex):
		print x

def getindex(myindex):
	"""Returns the filenames listed in the indexglob passed in."""
	myindexlen=len(myindex)
	startpos=0
	myret=[]
	while ((startpos+8)<myindexlen):
		mytestlen=decodeint(myindex[startpos:startpos+4])
		myret=myret+[myindex[startpos+4:startpos+4+mytestlen]]
		startpos=startpos+mytestlen+12
	return myret

def searchindex(myindex,myitem):
	"""(index,item) -- Finds the offset and length of the file 'item' in the
	datasegment via the index 'index' provided."""
	mylen=len(myitem)
	myindexlen=len(myindex)
	startpos=0
	while ((startpos+8)<myindexlen):
		mytestlen=decodeint(myindex[startpos:startpos+4])
		if mytestlen==mylen:
			if myitem==myindex[startpos+4:startpos+4+mytestlen]:
				#found
				datapos=decodeint(myindex[startpos+4+mytestlen:startpos+8+mytestlen]);
				datalen=decodeint(myindex[startpos+8+mytestlen:startpos+12+mytestlen]);
				return [datapos,datalen]
		startpos=startpos+mytestlen+12
		
def getitem(myid,myitem):
	myindex=myid[0]
	mydata=myid[1]
	myloc=searchindex(myindex,myitem)
	if not myloc:
		return None
	return mydata[myloc[0]:myloc[0]+myloc[1]]

def xpand(myid,mydest):
	myindex=myid[0]
	mydata=myid[1]
	origdir=os.getcwd()
	os.chdir(mydest)
	myindexlen=len(myindex)
	startpos=0
	while ((startpos+8)<myindexlen):
		namelen=decodeint(myindex[startpos:startpos+4])
		datapos=decodeint(myindex[startpos+4+namelen:startpos+8+namelen]);
		datalen=decodeint(myindex[startpos+8+namelen:startpos+12+namelen]);
		myname=myindex[startpos+4:startpos+4+namelen]
		dirname=os.path.dirname(myname)
		if dirname:
			if not os.path.exists(dirname):
				os.makedirs(dirname)
		mydat=open(myname,"w")
		mydat.write(mydata[datapos:datapos+datalen])
		mydat.close()
		startpos=startpos+namelen+12
	os.chdir(origdir)

class tbz2:
	def __init__(self,myfile):
		self.file=myfile
		self.filestat=None
		self.index=""
		self.infosize=0
		self.indexsize=None
		self.datasize=None
		self.indexpos=None
		self.datapos=None
		self.scan()
	
	def decompose(self,datadir,cleandir=1):
		"""Alias for unpackinfo() --- Complement to recompose() but optionally
		deletes the destination directory. Extracts the xpak from the tbz2 into
		the directory provided. Raises IOError if scan() fails.
		Returns result of upackinfo()."""
		if not self.scan():
			raise IOError
		if cleandir and os.path.exists(datadir):
			spawn("rm -Rf "+datadir+"/*",free=1)
		return self.unpackinfo(datadir)
	def compose(self,datadir):
		"""Alias for recompose()."""
		return recompose(datadir)
	def recompose(self,datadir):
		"""Creates an xpak segment from the datadir provided, truncates the tbz2
		to the end of regular data if an xpak segment already exists, and adds
		the new segment to the file with terminating info."""
		self.scan() # Don't care about condition... We'll rewrite the data anyway.
		myfile=open(self.file,"a+")
		if not myfile:
			raise IOError
		myfile.seek(-self.infosize,2) # 0,2 or -0,2 just mean EOF.
		myfile.truncate()
		xpdata=xpak(datadir)
		myfile.write(xpdata+encodeint(len(xpdata))+"STOP")
		myfile.flush()
		myfile.close()
		return 1

	def scan(self):
		"""Scans the tbz2 to locate the xpak segment and setup internal values.
		This function is called by relevant functions already."""
		mystat=os.lstat(self.file)
		if self.filestat:
			changed=0
			for x in [ST_SIZE, ST_MTIME, ST_CTIME]:
				if mystat[x] != self.filestat[x]:
					changed=1
			if not changed:
				return 1
		self.filestat=mystat
		a=open(self.file,"r")
		a.seek(-16,2)
		trailer=a.read()
		self.infosize=0
		if trailer[-4:]!="STOP":
			a.close()
			return 0
		if trailer[0:8]!="XPAKSTOP":
			a.close()
			return 0
		self.infosize=decodeint(trailer[8:12])
		a.seek(-(self.infosize+8),2)
		header=a.read(16)
		if header[0:8]!="XPAKPACK":
			a.close()
			return 0
		self.indexsize=decodeint(header[8:12])
		self.datasize=decodeint(header[12:16])
		self.indexpos=a.tell()
		self.index=a.read(self.indexsize)
		self.datapos=a.tell()
		a.close()
		return 1

	def filelist(self):
		"""Return an array of each file listed in the index."""
		if not self.scan():
			return None
		return getindex(self.index)

	def getfile(self,myfile,mydefault=None):
		"""Finds 'myfile' in the data segment and returns it."""
		if not self.scan():
			return None
		myresult=searchindex(self.index,myfile)
		if not myresult:
			return mydefault
		a=open(self.file,"r")
		a.seek(self.datapos+myresult[0],0)
		myreturn=a.read(myresult[1])
		a.close()
		return myreturn

	def getelements(self,myfile):
		"""A split/array representation of tbz2.getfile()"""
		mydat=self.getfile(myfile)
		if not mydat:
			return []
		return string.split(mydat)

	def unpackinfo(self,mydest):
		"""Unpacks all the files from the dataSegment into 'mydest'."""
		if not self.scan():
			return 0
		origdir=os.getcwd()
		a=open(self.file,"r")
		if not os.path.exists(mydest):
			os.makedirs(mydest)
		os.chdir(mydest)
		startpos=0
		while ((startpos+8)<self.indexsize):
			namelen=decodeint(self.index[startpos:startpos+4])
			datapos=decodeint(self.index[startpos+4+namelen:startpos+8+namelen]);
			datalen=decodeint(self.index[startpos+8+namelen:startpos+12+namelen]);
			myname=self.index[startpos+4:startpos+4+namelen]
			dirname=os.path.dirname(myname)
			if dirname:
				if not os.path.exists(dirname):
					os.makedirs(dirname)
			mydat=open(myname,"w")
			a.seek(self.datapos+datapos)
			mydat.write(a.read(datalen))
			mydat.close()
			startpos=startpos+namelen+12
		a.close()
		os.chdir(origdir)
		return 1




