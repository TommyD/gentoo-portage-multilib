# Copyright 1998-2002 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2

codes={}
codes["reset"]="\x1b[0m"
codes["bold"]="\x1b[01m"
codes["teal"]="\x1b[36;03m"
codes["turquoise"]="\x1b[36;01m"
codes["fuscia"]="\x1b[35;01m"
codes["purple"]="\x1b[35;03m"
codes["blue"]="\x1b[34;01m"
codes["darkblue"]="\x1b[34;03m"
codes["yellow"]="\x1b[33;01m"
codes["brown"]="\x1b[33;03m"
codes["green"]="\x1b[32;01m"
codes["darkgreen"]="\x1b[32;03m"
codes["red"]="\x1b[31;01m"

def nocolor():
	"turn off colorization"
	for x in codes.keys():
		codes[x]=""

def resetColor():
	return codes["reset"]

def ctext(color,text):
	return codes[ctext]+text+codes["reset"]

def bold(text):
	return codes["bold"]+text+codes["reset"]

def teal(text):
	return codes["teal"]+text+codes["reset"]

def turquoise(text):
	return codes["turquoise"]+text+codes["reset"]

def green(text):
	return codes["blue"]+text+codes["reset"]

def darkgreen(text):
	return codes["darkblue"]+text+codes["reset"]

def green(text):
	return codes["green"]+text+codes["reset"]

def darkgreen(text):
	return codes["darkgreen"]+text+codes["reset"]

def white(text):
	return codes["bold"]+text+codes["reset"]

def yellow(text):
	return codes["yellow"]+text+codes["reset"]

def red(text):
	return codes["red"]+text+codes["reset"]
