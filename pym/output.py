# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/output.py,v 1.24.2.4 2005/04/17 09:01:55 jstubbs Exp $


import commands,os,sys,re

havecolor=1
dotitles=1

esc_seq = "\x1b["

g_attr = {}
g_attr["normal"]       =  0

g_attr["bold"]         =  1
g_attr["faint"]        =  2
g_attr["standout"]     =  3
g_attr["underline"]    =  4
g_attr["blink"]        =  5
g_attr["overline"]     =  6  # Why is overline actually useful?
g_attr["reverse"]      =  7
g_attr["invisible"]    =  8

g_attr["no-attr"]      = 22
g_attr["no-standout"]  = 23
g_attr["no-underline"] = 24
g_attr["no-blink"]     = 25
g_attr["no-overline"]  = 26
g_attr["no-reverse"]   = 27
# 28 isn't defined?
# 29 isn't defined?
g_attr["black"]        = 30
g_attr["red"]          = 31
g_attr["green"]        = 32
g_attr["yellow"]       = 33
g_attr["blue"]         = 34
g_attr["magenta"]      = 35
g_attr["cyan"]         = 36
g_attr["white"]        = 37
# 38 isn't defined?
g_attr["default"]      = 39
g_attr["bg_black"]     = 40
g_attr["bg_red"]       = 41
g_attr["bg_green"]     = 42
g_attr["bg_yellow"]    = 43
g_attr["bg_blue"]      = 44
g_attr["bg_magenta"]   = 45
g_attr["bg_cyan"]      = 46
g_attr["bg_white"]     = 47
g_attr["bg_default"]   = 49


# make_seq("blue", "black", "normal")
def color(fg, bg="default", attr=["normal"]):
	mystr = esc_seq[:] + "%02d" % g_attr[fg]
	for x in [bg]+attr:
		mystr += ";%02d" % g_attr[x]
	return mystr+"m"



codes={}
codes["reset"]     = esc_seq + "39;49;00m"

codes["bold"]      = esc_seq + "01m"
codes["faint"]     = esc_seq + "02m"
codes["standout"]  = esc_seq + "03m"
codes["underline"] = esc_seq + "04m"
codes["blink"]     = esc_seq + "05m"
codes["overline"]  = esc_seq + "06m"  # Who made this up? Seriously.

codes["teal"]      = esc_seq + "36m"
codes["turquoise"] = esc_seq + "36;01m"

codes["fuchsia"]   = esc_seq + "35;01m"
codes["purple"]    = esc_seq + "35m"

codes["blue"]      = esc_seq + "34;01m"
codes["darkblue"]  = esc_seq + "34m"

codes["green"]     = esc_seq + "32;01m"
codes["darkgreen"] = esc_seq + "32m"

codes["yellow"]    = esc_seq + "33;01m"
codes["brown"]     = esc_seq + "33m"

codes["red"]       = esc_seq + "31;01m"
codes["darkred"]   = esc_seq + "31m"

def nc_len(mystr):
	tmp = re.sub(esc_seq + "^m]+m", "", mystr);
	return len(tmp)

def xtermTitle(mystr):
	if havecolor and dotitles and os.environ.has_key("TERM") and sys.stderr.isatty():
		myt=os.environ["TERM"]
		legal_terms = ["xterm","Eterm","aterm","rxvt","screen","kterm","rxvt-unicode","gnome"]
		for term in legal_terms:
			if myt.startswith(term):
				sys.stderr.write("\x1b]2;"+str(mystr)+"\x07")
				sys.stderr.flush()
				break

default_xterm_title = None

def xtermTitleReset():
	global default_xterm_title
	if default_xterm_title is None:
		prompt_command = os.getenv('PROMPT_COMMAND')
		if prompt_command is not None:
			default_xterm_title = commands.getoutput(prompt_command)
		else:
			pwd = os.getenv('PWD','')
			home = os.getenv('HOME', '')
			if home != '' and pwd.startswith(home):
				pwd = '~' + pwd[len(home):]
			default_xterm_title = '%s@%s:%s' % (
				os.getenv('LOGNAME', ''), os.getenv('HOSTNAME', '').split('.', 1)[0], pwd)
	xtermTitle(default_xterm_title)

def notitles():
	"turn off title setting"
	dotitles=0

def nocolor():
	"turn off colorization"
	havecolor=0
	for x in codes.keys():
		codes[x]=""

def resetColor():
	return codes["reset"]

def colorize(color_key, text):
	return codes[color_key] + text + codes["reset"]

codes["darkteal"]   = codes["turquoise"]
codes["darkyellow"] = codes["brown"]
codes["fuscia"]     = codes["fuchsia"]
codes["white"]      = codes["bold"]

compat_functions_colors = ["bold","white","teal","turquoise","darkteal",
	"fuscia","fuchsia","purple","blue","darkblue","green","darkgreen","yellow",
	"brown","darkyellow","red","darkred"]

def create_color_func(color_key):
	def derived_func(*args):
		newargs = list(args)
		newargs.insert(0, color_key)
		return colorize(*newargs)
	return derived_func

for c in compat_functions_colors:
	setattr(sys.modules[__name__], c, create_color_func(c))
