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

