# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import logging
import errors
from portage_const import CONF_DEFAULTS
from portage.util import modules

# default class settings for types.  dict, loaded when needed
# {type:class} <-- strings.
default_classes = None
section_settings = None

class config:
	"""Global Config representation, based around a ConfigParser.  Section instantiation occurs on demand"""

	# these are options available to all sections, that have special meaning to the parser, and are filtered
	# iow, the callable doesn't see it.  inherit, type, class are also filtered
	filter_opts = ["package.keywords", "package.mask", "package.unmask", "package.use"]

	def __init__(self, cparser, parser_config=None):
		self._cparser = cparser
		if parser_config == None:
			parser_config = load_section_settings()
		self._parser_defaults = parser_config
		self.__domains = {}
		# auto exec.
		s = cparser.sections()

		for x in s:
			if not c.has_option(x, "type"):
				continue
			val = c.get(x, "type").lower()
			if val == "exec":
				# do something a bit more.
				logging.error("skipping section %s of exec type, don't know how to deal with it" % x)
			c.set(x, "type", val)


	def _find_sections(self, type):
		l = []
		for x in self._cparser.sections():
			if not self._cparser.has_option(x, "type'):
				continue
			if self._cparser.get(x, "type").lower() == type:
				l.append(x)
		return l

	def default_domain(self):
		l = self.domains()
		if len(l) == 1:
			return l[0]
		d = c.defaults().get("domain")
		return d

	def get_domain(self, domain):
		if domain in self.__domains:
			return self.__domains[domain]

		if not c.has_section(domain) or c.get(domain, 'type') != "domain":
			raise KeyError("domain %s doesn't exist" % domain)


	def load_repositories(self, repositories=None):
		"""instantiate repositories.  either load a list of repository names (section titles passed 
		in via repositories=[]), or load all.
		Chucks KeyError if a requested repository isn't in this config. or 
		portage.repository.errors.BaseException derivatives"""

		repos = self.repositories()
		if repositories == None:
			repositories = repos:
		else:
			# XXX note this is quadratic.
			for x in repositories:
				if x not in repos:
					raise KeyError(x)
		for x in repositories:
			if x not in self._repo_instances:
				self._repo_instances[x], opts = self._instantiate_section(x)
				if opts:
					

	def _instantiate_section(self, section, additional_filter_list=[]):
		"""handler for instantiating sections defined by class, using default if available.
		Throws UndefinedTypeError, InstantiationError
		returns (obj, filtered opts)"""
		assert section in self._cparser.sections()
		confdict = self._colapse_section(section)
		if not "type" in confdict:
			raise errors.UndefinedTypeError(section)
		defaults = load_defaults()

		# pull what's needed, cleaning up confdict in the process
		type = confdict["type"]
		del confdict["type"]
		if "class" in confdict:
			class = confdict["class"]
			del confdict["class"]
		else:
			if type not in defaults:
				raise errors.ClassRequired(section, type)
			class = defaults[type]

		removed_opts = {}
		for x in self.filter_opts + additional_filter_list:
			if x in confdict:
				removed_opts.append(x)
				del confdict[x]
		# load callable.  must be a callable too, 'coz we check up on it. >:)
		from inspect import isroutine, isclass
		callable = load_attribute(class)
		if not isclass(callable) and not isroutine(callable):
			raise errors.InstantiationError(class, [], confdict, 
				TypeError("%s is not a class/callable" % type(callable))

		sect_settings = load_section_settings()
		if type in sect_settings:
			if 'instantiate' in sect_settings[type]:
				for x in sect_settings[type]['instantiate'].split():
					if x in confdict:
						
		try:	obj = callable(**confdict)
		except Exception, e:
			if isinstance(e, RuntimeError) or isinstance(e, SystemExit):
				raise
			raise errors.InstantiationError(class, [], confdict, e)
		if obj == None:
			raise errors.InstantiationError(class, [], confdict, 
				errors.NoObjectReturned(class))

		return obj, removed_opts

	def _collapse_section(self, section, defaults={}):
		"""given a top level section, walks the section's inherit's, returning a dict.
		defaults if set, must be dict, and are just that, defaults."""

		assert isinstance(defaults, dict)
		if len(defaults.keys):	defaults = defaults.copy()

		slist = [section]
		while self._cparser.has_option(slist[-1], "inherit"):
			newsect = self._cparser.get(slist[-1], "inherit")
			if not self._cparser.has_section(newsect):
				raise errors.InheritError(slist[-1], newsect)
			slist.append(newsect)

		# walk list in reverse, pullints items working way down the list.
		while len(slist):
			d = self._cparser.items(slist[-1])
			# do whatever mangling would occur, here (cleansing inherit fex)
			defaults.update(d)
			slist.pop(-1)
		if "inherit" in d:	del d["inherit"]
		return d

	def domains(self):
		return self._find_sections("domain")

	def repositories(self):
		return self._find_sections("repo")

	def configs(self):
		return self._find_sections("config")


def load_section_settings():
	"""load iff needed default class definitions, returning dict of type:class"""
	global section_settings
	if section_settings != None:
		return section_settings
	c=ConfigParser()
	c.read(CONF_DEFAULT)
	for x in c.sections():
		d2 = c.items(x)
		if len(d2.keys()):
			ds[x] = d2
	section_settings = ds
	return section_settings

