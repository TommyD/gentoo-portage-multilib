# repoman: Checks
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

import os
import re
import time
import repoman.errors as errors

class LineCheck(object):
	"""Run a check on a line of an ebuild."""
	"""A regular expression to determine whether to ignore the line"""
	ignore_line = False

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		if self.re.match(line):
			return self.error

class EbuildHeader(LineCheck):
	"""Ensure ebuilds have proper headers
		Copyright header errors
		CVS header errors
		License header errors
	
	Args:
		modification_year - Year the ebuild was last modified
	"""

	repoman_check_name = 'ebuild.badheader'

	gentoo_copyright = r'^# Copyright ((1999|200\d)-)?%s Gentoo Foundation$'
	# Why a regex here, use a string match
	# gentoo_license = re.compile(r'^# Distributed under the terms of the GNU General Public License v2$')
	gentoo_license = r'# Distributed under the terms of the GNU General Public License v2'
	cvs_header = re.compile(r'^#\s*\$Header.*\$$')

	def __init__(self, st_mtime):
		self.modification_year = str(time.gmtime(st_mtime)[0])
		self.gentoo_copyright_re = re.compile(self.gentoo_copyright % self.modification_year)

	def check(self, num, line):
		if num > 2:
			return
		elif num == 0:
			if not self.gentoo_copyright_re.match(line):
				return errors.COPYRIGHT_ERROR
		elif num == 1 and line.strip() != self.gentoo_license:
			return errors.LICENSE_ERROR
		elif num == 2:
			if not self.cvs_header.match(line):
				return errors.CVS_HEADER_ERROR


class EbuildWhitespace(LineCheck):
	"""Ensure ebuilds have proper whitespacing"""

	repoman_check_name = 'ebuild.minorsyn'

	ignore_line = re.compile(r'(^$)|(^(\t)*#)')
	leading_spaces = re.compile(r'^[\S\t]')
	trailing_whitespace = re.compile(r'.*([\S]$)')	

	def check(self, num, line):
		if not self.leading_spaces.match(line):
			return errors.LEADING_SPACES_ERROR
		if not self.trailing_whitespace.match(line):
			return errors.TRAILING_WHITESPACE_ERROR


class EbuildQuote(LineCheck):
	"""Ensure ebuilds have valid quoting around things like D,FILESDIR, etc..."""

	repoman_check_name = 'ebuild.minorsyn'
	_ignored_commands = ["echo", "local", "export"]
	_ignored_commands += ["eerror", "einfo", "elog", "eqawarn", "ewarn"]
	ignore_line = re.compile(r'(^$)|(^\s*#.*)|(^\s*\w+=.*)' + \
		r'|(^\s*(' + "|".join(_ignored_commands) + r')\s+)')
	var_names = ["D", "DISTDIR", "FILESDIR", "S", "T", "ROOT", "WORKDIR"]

	# variables for games.eclass
	var_names += ["Ddir", "dir", "GAMES_PREFIX_OPT", "GAMES_DATADIR",
		"GAMES_DATADIR_BASE", "GAMES_SYSCONFDIR", "GAMES_STATEDIR",
		"GAMES_LOGDIR", "GAMES_BINDIR"]

	var_names = "(%s)" % "|".join(var_names)
	var_reference = re.compile(r'\$(\{'+var_names+'\}|' + \
		var_names + '\W)')
	missing_quotes = re.compile(r'(\s|^)[^"\'\s]*\$\{?' + var_names + \
		r'\}?[^"\'\s]*(\s|$)')
	cond_begin =  re.compile(r'(^|\s+)\[\[($|\\$|\s+)')
	cond_end =  re.compile(r'(^|\s+)\]\]($|\\$|\s+)')
	
	def check(self, num, line):
		if self.var_reference.search(line) is None:
			return
		# There can be multiple matches / violations on a single line. We
		# have to make sure none of the matches are violators. Once we've
		# found one violator, any remaining matches on the same line can
		# be ignored.
		pos = 0
		while pos <= len(line) - 1:
			missing_quotes = self.missing_quotes.search(line, pos)
			if not missing_quotes:
				break
			# If the last character of the previous match is a whitespace
			# character, that character may be needed for the next
			# missing_quotes match, so search overlaps by 1 character.
			group = missing_quotes.group()
			pos = missing_quotes.end() - 1

			# Filter out some false positives that can
			# get through the missing_quotes regex.
			if self.var_reference.search(group) is None:
				continue

			# This is an attempt to avoid false positives without getting
			# too complex, while possibly allowing some (hopefully
			# unlikely) violations to slip through. We just assume
			# everything is correct if the there is a ' [[ ' or a ' ]] '
			# anywhere in the whole line (possibly continued over one
			# line).
			if self.cond_begin.search(line) is not None:
				continue
			if self.cond_end.search(line) is not None:
				continue

			# Any remaining matches on the same line can be ignored.
			return errors.MISSING_QUOTES_ERROR


class EbuildAssignment(LineCheck):
	"""Ensure ebuilds don't assign to readonly variables."""

	repoman_check_name = 'variable.readonly'

	readonly_assignment = re.compile(r'^\s*(export\s+)?(A|CATEGORY|P|PV|PN|PR|PVR|PF|D|WORKDIR|FILESDIR|FEATURES|USE)=')
	line_continuation = re.compile(r'([^#]*\S)(\s+|\t)\\$')
	ignore_line = re.compile(r'(^$)|(^(\t)*#)')

	def __init__(self):
		self.previous_line = None

	def check(self, num, line):
		match = self.readonly_assignment.match(line)
		e = None
		if match and (not self.previous_line or not self.line_continuation.match(self.previous_line)):
			e = errors.READONLY_ASSIGNMENT_ERROR
		self.previous_line = line
		return e


class EbuildNestedDie(LineCheck):
	"""Check ebuild for nested die statements (die statements in subshells"""
	
	repoman_check_name = 'ebuild.nesteddie'
	nesteddie_re = re.compile(r'^[^#]*\([^)]*\bdie\b')
	
	def check(self, num, line):
		if self.nesteddie_re.match(line):
			return errors.NESTED_DIE_ERROR


class EbuildUselessDodoc(LineCheck):
	"""Check ebuild for useless files in dodoc arguments."""
	repoman_check_name = 'ebuild.minorsyn'
	uselessdodoc_re = re.compile(
		r'^\s*dodoc(\s+|\s+.*\s+)(ABOUT-NLS|COPYING|LICENSE)($|\s)')

	def check(self, num, line):
		match = self.uselessdodoc_re.match(line)
		if match:
			return "Useless dodoc '%s'" % (match.group(2), ) + " on line: %d"


class EbuildUselessCdS(LineCheck):
	"""Check for redundant cd ${S} statements"""
	repoman_check_name = 'ebuild.minorsyn'
	method_re = re.compile(r'^\s*src_(compile|install|test)\s*\(\)')
	cds_re = re.compile(r'^\s*cd\s+("\$(\{S\}|S)"|\$(\{S\}|S))\s')

	def __init__(self):
		self.check_next_line = False

	def check(self, num, line):
		if self.check_next_line:
			self.check_next_line = False
			if self.cds_re.match(line):
				return errors.REDUNDANT_CD_S_ERROR
		elif self.method_re.match(line):
			self.check_next_line = True

class EbuildPatches(LineCheck):
	"""Ensure ebuilds use bash arrays for PATCHES to ensure white space safety"""
	repoman_check_name = 'ebuild.patches'
	re = re.compile(r'^\s*PATCHES=[^\(]')
	error = errors.PATCHES_ERROR

class EbuildQuotedA(LineCheck):
	"""Ensure ebuilds have no quoting around ${A}"""

	repoman_check_name = 'ebuild.minorsyn'
	a_quoted = re.compile(r'.*\"\$(\{A\}|A)\"')

	def check(self, num, line):
		match = self.a_quoted.match(line)
		if match:
			return "Quoted \"${A}\" on line: %d"

_constant_checks = tuple((c() for c in (
	EbuildWhitespace, EbuildQuote,
	EbuildAssignment, EbuildUselessDodoc,
	EbuildUselessCdS, EbuildNestedDie,
	EbuildPatches, EbuildQuotedA)))

_iuse_def_re = re.compile(r'^IUSE=.*')
_comment_re = re.compile(r'(^|\s*)#')
_inherit_autotools_re = re.compile(r'^\s*inherit\s(.*\s)?autotools(\s|$)')
_autotools_funcs = (
	"eaclocal", "eautoconf", "eautoheader",
	"eautomake", "eautoreconf", "_elibtoolize")
_autotools_func_re = re.compile(r'(^|\s)(' + \
	"|".join(_autotools_funcs) + ')(\s|$)')

def run_checks(contents, pkg):
	checks = list(_constant_checks)
	checks.append(EbuildHeader(pkg.mtime))
	iuse_def = None
	inherit_autotools = None
	autotools_func_call = None
	for num, line in enumerate(contents):
		comment = _comment_re.match(line)
		if comment is None:
			if inherit_autotools is None:
				inherit_autotools = _inherit_autotools_re.match(line)
			if inherit_autotools is not None and \
				autotools_func_call is None:
				autotools_func_call = _autotools_func_re.search(line)
			if iuse_def is None:
				iuse_def = _iuse_def_re.match(line)
		for lc in checks:
			ignore = lc.ignore_line
			if not ignore or not ignore.match(line):
				e = lc.check(num, line)
				if e:
					yield lc.repoman_check_name, e % (num + 1)
	if iuse_def is None:
		yield 'IUSE.undefined', 'IUSE is not defined'
	if inherit_autotools and autotools_func_call is None:
		yield 'inherit.autotools', 'no eauto* function called'
