# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


class PortageException(Exception):
	"""General superclass for portage exceptions"""
	def __init__(self,value):
		self.value = value[:]
	def __str__(self):
		if isinstance(self.value, basestring):
			return self.value
		else:
			return repr(self.value)

class CorruptionError(PortageException):
	"""Corruption indication"""

class InvalidDependString(PortageException):
	"""An invalid depend string has been encountered"""

class InvalidVersionString(PortageException):
	"""An invalid version string has been encountered"""

class SecurityViolation(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""

class IncorrectParameter(PortageException):
	"""A parameter of the wrong type was passed"""

class MissingParameter(PortageException):
	"""A parameter is required for the action requested but was not passed"""

class ParseError(PortageException):
	"""An error was generated while attempting to parse the request"""

class InvalidData(PortageException):
	"""An incorrect formatting was passed instead of the expected one"""

class InvalidDataType(PortageException):
	"""An incorrect type was passed instead of the expected one"""

class InvalidLocation(PortageException):
	"""Data was not found when it was expected to exist or was specified incorrectly"""

class FileNotFound(InvalidLocation):
	"""A file was not found when it was expected to exist"""

class DirectoryNotFound(InvalidLocation):
	"""A directory was not found when it was expected to exist"""

class OperationNotPermitted(PortageException):
	"""An operation was not permitted operating system"""

class PermissionDenied(PortageException):
	from errno import EACCES as errno
	"""Permission denied"""

class ReadOnlyFileSystem(PortageException):
	"""Read-only file system"""

class CommandNotFound(PortageException):
	"""A required binary was not available or executable"""


class PortagePackageException(PortageException):
	"""Malformed or missing package data"""

class PackageNotFound(PortagePackageException):
	"""Missing Ebuild or Binary"""

class InvalidPackageName(PortagePackageException):
	"""Malformed package name"""

class InvalidAtom(PortagePackageException):
	"""Malformed atom spec"""

class UnsupportedAPIException(PortagePackageException):
	"""Unsupported API"""
	def __init__(self, cpv, eapi):
		self.cpv, self.eapi = cpv, eapi
	def __str__(self):
		msg = ("Unable to do any operations on '%s', since " + \
		"it's EAPI is higher than this portage version's. Please upgrade" + \
		" to a portage version that supports EAPI '%s'.") % \
		(self.cpv, str(self.eapi).lstrip("-"))
		return msg



class SignatureException(PortageException):
	"""Signature was not present in the checked file"""

class DigestException(SignatureException):
	"""A problem exists in the digest"""

class MissingSignature(SignatureException):
	"""Signature was not present in the checked file"""

class InvalidSignature(SignatureException):
	"""Signature was checked and was not a valid, current, nor trusted signature"""

class UntrustedSignature(SignatureException):
	"""Signature was not certified to the desired security level"""

