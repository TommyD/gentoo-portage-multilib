# $Header$

class CorruptionError(Exception):
	"""Corruption indication"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidDependString(Exception):
	"""An invalid depend string has been encountered"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class SecurityViolation(Exception):
	"""An incorrect formatting was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class MissingParameter(Exception):
	"""An parameter is required for the action requested but was not passed"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidData(Exception):
	"""An incorrect formatting was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidDataType(Exception):
	"""An incorrect type was passed instead of the expected one"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class FileNotFound(Exception):
	"""A file was not found when it was expected to exist"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class DirectoryNotFound(Exception):
	"""A directory was not found when it was expected to exist"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class CommandNotFound(Exception):
	"""A required binary was not available or executable"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class MissingSignature(Exception):
	"""Signature was not present in the checked file"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class InvalidSignature(Exception):
	"""Signature was checked and was not a valid, current, nor trusted signature"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

class UntrustedSignature(Exception):
	"""Signature was not certified to the desired security level"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		return repr(self.value)

