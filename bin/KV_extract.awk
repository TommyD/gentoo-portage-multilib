#
# Code to extract the full version of a kernel from the Makefile
# This certainly depends on the Makefile for the kernel 
# being in a certain format, with specific values.
#
# Written 29 Apr 2002 for the Gentoo Linux distribution
# by Jon Nelson <jnelson@gentoo.org>
#
# Placed into the public domain, no warranty, etc..
#
# Confirmed to work with 2.2.20 and 2.4.18, both bone stock.
#

BEGIN { 
  version="";
  patchlevel="";
  sublevel="";
  extraversion="";
  error=0;
}
  $1 == "VERSION" {
    if (version == "") {
      version=$3;
    } else { 
      print "Matched VERSION more than once!" > "/dev/stderr";
      error=1;
      exit(1);
    }
    next; 
  }
  $1 == "PATCHLEVEL" {
    if (patchlevel == "") { 
      patchlevel=$3;
    } else { 
      print "Matched PATCHLEVEL more than once!" > "/dev/stderr";
      error=2;
      exit(2);
    }
    next; 
  }
  $1 == "SUBLEVEL" { 
    if (sublevel == "") { 
      sublevel=$3 
    } else { 
      print "Matched SUBLEVEL more than once!" > "/dev/stderr";
      error=3;
      exit(3);
    }
    next; 
  }
  $1 == "EXTRAVERSION" { 
    if (extraversion == "") { 
      extraversion=$3 
    } else {
      print "Matched EXTRAVERSION more than once!" > "/dev/stderr";
      error=4;
      exit(4);
    }
    next; 
  }
END {
  if (error != 0) {
    exit(error);
  } else {
    printf "%s.%s.%s%s\n", version, patchlevel,sublevel,extraversion;
  }
}
