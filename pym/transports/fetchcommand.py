#11/02/2004
#Brian Harring
#<ferringb@gentoo.org

#user specified fetchcommand
#basically a wrapper around a file system binary being called.

import urlparse,types
import portage_exec

class CustomConnection:
	"""abstraction representing a portage.config instances FETCHCOMMAND and RESUMECOMMAND"""
	def __init__(self,mysettings,selinux_context=None, verbose=True):
		"""selinux_context should always be passed in, actual control of whether or not
		the context is switched is based upon if it's a selinux capable system
		verbose controls whether this instance makes noise or not"""
		self.__fc = mysettings["FETCHCOMMAND"]
		self.__rc = mysettings["RESUMECOMMAND"]
		self.__verbose = verbose
		self.__cfc = {}
		self.__crc = {}
		self.__selinux_context = selinux_context
		self.__distdir=mysettings["DISTDIR"]
		for k in mysettings.environ().keys():
			if k.startswith("FETCHCOMMAND_"):
				self.__cfc[k[13:]] = mysettings[k]
			elif k.startswith("RESUMECOMMAND_"):
				self.__crc[k[14:]] = mysettings[k]
			

	def fetch(self, uri, file_name=None, distdir=None,verbose=None):
		"""fetch uri, storing it to file_name
		distdir can be used to overload the stored directory, although it is deprecated"""
		return self.__execute(uri,file_name,distdir,False,verbose)

	def resume(self, uri, file_name=None, distdir=None,verbose=None):
		"""resume uri into file_name"""
		return self.__execute(uri,file_name,distdir,True,verbose)

	def __execute(self, uri, file_name, distdir, resume,verbose):
		"""internal function doing the actual work of fetch/resume"""
		if verbose==None:
			verbose=self.__verbose
		if not distdir:
			distdir = self.__distdir
		if not file_name:
			x = uri.rfind("/")
			if x == -1:
				raise Exception,"Unable to deterimine file_name from %s" % uri
			file_name = uri[x+1:]

		proto = urlparse.urlparse(uri)[0].upper()
		
		if resume:
			f = self.__crc.get(proto, self.__rc)
		else:
			f = self.__cfc.get(proto, self.__fc)

		f=f.replace("${DISTDIR}", distdir)
		f=f.replace("${URI}",uri)
		f=f.replace("${FILE}",file_name)
		if verbose:
			fd_pipes={1:1,2:2}
		else:
			fd_pipes={}
		return portage_exec.spawn(f,fd_pipes=fd_pipes,selinux_context=self.__selinux_context)
			
