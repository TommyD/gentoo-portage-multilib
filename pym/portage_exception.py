# $Header$

class PortageException(Exception):
	"""General superclass for portage exceptions"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class CorruptionError(PortageException):
	"""Corruption indication"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidDependString(PortageException):
	"""An invalid depend string has been encountered"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidVersionString(PortageException):
	"""An invalid version string has been encountered"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class SecurityViolation(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class IncorrectParameter(PortageException):
	"""An parameter of the wrong type was passed"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class MissingParameter(PortageException):
	"""An parameter is required for the action requested but was not passed"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)




class InvalidData(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidDataType(PortageException):
	"""An incorrect type was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)




class InvalidLocation(PortageException):
	"""Data was not found when it was expected to exist or was specified incorrectly"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class FileNotFound(InvalidLocation):
	"""A file was not found when it was expected to exist"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class DirectoryNotFound(InvalidLocation):
	"""A directory was not found when it was expected to exist"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)



class CommandNotFound(PortageException):
	"""A required binary was not available or executable"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)




class SignatureException(PortageException):
	"""Signature was not present in the checked file"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class MissingSignature(SignatureException):
	"""Signature was not present in the checked file"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidSignature(SignatureException):
	"""Signature was checked and was not a valid, current, nor trusted signature"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class UntrustedSignature(SignatureException):
	"""Signature was not certified to the desired security level"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

