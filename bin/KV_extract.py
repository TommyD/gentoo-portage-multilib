#! /usr/bin/python
#
# Code to extract the full version of a kernel from the Makefile
# This certainly depends on the Makefile for the kernel 
# being in a certain format, with specific values.
#
# Written 4 May 2002 for the Gentoo Linux distribution
# by Jon Nelson <jnelson@gentoo.org>
#
# Placed into the public domain, no warranty, etc..
#
# Confirmed to work with 2.2.20 and 2.4.18, both bone stock.
#

import string, sys

def ExtractKernelVersion(filename):
  lines = open(filename, 'r').readlines()
  lines = map(string.strip, lines)

  item_dict = { 'VERSION':[],
                'PATCHLEVEL':[],
                'SUBLEVEL':[],
                'EXTRAVERSION':[]
              }

  item_dict_keys = item_dict.keys()
  line_number = 0

  for line in lines:
    line_number = line_number + 1
    if ' ' not in line:
      continue
    if '=' not in line:
      continue

    items = string.split(line)
    if items[0] in item_dict_keys:
      item_dict[items[0]].append( (line, line_number) )

  # OK, check
  error = 0
  for (key,value) in item_dict.items():
    if value == [] and key != 'EXTRAVERSION':
      print 'E:Unable to locate %s' % (key)
      error = error + 1
      continue
    if len(value) > 1:
      print 'E:Too many values matched for key %s!' % (key)
      for (match,line_number) in value:
        print 'E: Line %d reads \"%s\"' % (line_number, match)
        error = error + 1
      continue
    if len(value) == 1: # redundant
      real_value = string.split(value[0][0])[2]
      item_dict[key] = real_value

  if error == 0:
    print "%s.%s.%s%s" % (item_dict['VERSION'],
                            item_dict['PATCHLEVEL'],
                            item_dict['SUBLEVEL'],
                            item_dict['EXTRAVERSION'])
  sys.exit(error)

if __name__ == "__main__":
  filename = '/usr/src/linux/Makefile'
  if len(sys.argv[1:]) == 1:
    filename = sys.argv[1]
  ExtractKernelVersion(filename)
