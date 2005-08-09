# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

#from metadata import package as package_base
from portage.util.mappings import LimitedChangeSet

class base(object):
	"""base object representing a conditional node"""

	def __init__(self, node, payload, negate=False):
		self.negate, self.cond, self.restrictions = negate, node, payload

	def __str__(self):	
		if self.negate:	s="!"+self.cond
		else:					s=self.cond
		try:		s2=" ".join(self.restrictions)
		except TypeError:
			s2=str(self.restrictions)
		return "%s? ( %s )" % (s, s2)


	def __iter__(self):
		return iter(self.restrictions)

class PackageWrapper(object):
	def __init__(self, pkg_instance, configurable_attribute_name, initial_settings=[], unchangable_settings=[], attributes_to_wrap={}):
		"""pkg_instance should be an existing package instance
		configurable_attribute_name is the attribute name to fake on this instance for accessing builtup conditional changes
		use, fex, is valid for unconfigured ebuilds
		
		initial_settings is the initial settings of this beast, dict
		attributes_to_wrap should be a dict of attr_name:callable
		the callable receives the 'base' attribute (unconfigured), with the built up conditionals as a second arg
		"""
		self.__wrapped_pkg = pkg_instance
		self.__wrapped_attr = attributes_to_wrap
		if configurable_attribute_name.find(".") != -1:
			raise ValueError("can only wrap first level attributes, 'obj.dar' fex, not '%s'" % (configurable_attribute_name))
		setattr(self, configurable_attribute_name, LimitedChangeSet(initial_settings, unchangable_settings))
		self.__configurable = getattr(self, configurable_attribute_name)
		self.__reuse_pt = 0
		self.__cached_wrapped = {}		

	def rollback(self, point=0):
		self.__configurable.rollback(point)
		# yes, nuking objs isn't necessarily required.  easier this way though.
		# XXX: optimization point
		self.__reuse_pt += 1 
	
	def commit(self):
		self.__configurable.commit()
		
	def changes_count(self):
		return self.__configurable.changes_count()
	
	def push_add(self, key):
		if key not in self.__configurable:
			self.__configurable.add(key)
			self.__reuse_pt += 1
	
	def push_remove(self, key):
		if key in self.__configurable:
			self.__configurable.remove(key)
			self.__reuse_pt += 1
	
	def __getattr__(self, attr):
		if attr in self.__wrapped_attr:
			if attr in self.__cached_wrapped:
				if self.__cached_wrapped[attr][0] == self.__reuse_pt:
					return self.__cached_wrapped[attr][1]
				del self.__cached_wrapped[attr]
			o = self.__wrapped_attr[attr](getattr(self.__wrapped_pkg, attr), self.__configurable)
			self.__cached_wrapped[attr] = (self.__reuse_pt, o)
			return o
		else:
			return getattr(self.__wrapped_pkg, attr)

