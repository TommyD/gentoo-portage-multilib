# Gentoo Linux Dependency Checking Code
# Copyright 1998-2002 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License
import portage;

def resetColor():
	if portage.settings["NOCOLOR"] and portage.settings["NOCOLOR"]=="true":
		return ""
	return "\x1b[0m"

def startColor(color):
	if portage.settings["NOCOLOR"] and portage.settings["NOCOLOR"]=="true":
		return ""
	return color

def startBold():
	return startColor("\x1b[01m");

def startTurquoise():
	return startColor("\x1b[36;01m");

def startGreen():
	return startColor("\x1b[32;01m");

def startWhite():
	return startColor("\x1b[37;01m");

def startYellow():
	return startColor("\x1b[33;01m");

def startRed():
	return startColor("\x1b[31;01m");

def bold(text):
	return startBold()+text+resetColor()

def turquoise(text):
	return startTurquoise()+text+resetColor()

def green(text):
	return startGreen()+text+resetColor()

def white(text):
	return startWhite()+text+resetColor()

def yellow(text):
	return startYellow()+text+resetColor()

def read(text):
	return startRed()+text+resetColor()
