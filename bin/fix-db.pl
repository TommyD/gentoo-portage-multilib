#!/usr/bin/perl

# fix-db.pl - Fixes COUNTER files in /var/db/pkg
#
# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$


sub fatal_error
{
	print STDERR 'fix-db: fatal: ' . shift() . "\n";
	exit(1);
}


print "Grabbing db contents...\n";

$ebuild_files = `find /var/db/pkg -type f -name "*.ebuild" -mindepth 3 -maxdepth 3`;
$contents_files = `find /var/db/pkg -type f -name "CONTENTS" -mindepth 3 -maxdepth 3`;

$ebuild_files =~ s|^/var/db/pkg/||gm;
$ebuild_files =~ s/\r//g;
$ebuild_files =~ s|^([^/]+)/[^/]+/([^/]+)\.ebuild$|\1/\2|gm;
@ebuild_files = split(/\n/, $ebuild_files);

$contents_files =~ s/\r//g;
@contents_files = split(/\n/, $contents_files);

fatal_error('# of ebuilds doesn\'t match # of CONTENTS files') if
  ($#ebuild_files != $#contents_files);

print "Grabbing mtimes...\n";

foreach $ebuild_file (@ebuild_files)
{
	open(CONTENTS, '/var/db/pkg/' . $ebuild_file . '/CONTENTS') or
    fatal_error('couldn\'t open /var/db/pkg/' . $ebuild_file . '/CONTENTS: ' . $!);
	@contents = <CONTENTS>;
	close(CONTENTS);

	$mtime = -1;
	foreach $contents_line (@contents)
	{
		$contents_line =~ s/[\r\n]//g;

		if ($contents_line =~ /^(obj|sym) /)
		{
			$contents_line =~ s/^.* ([0-9]+)$/\1/;
			if ($contents_line > $mtime)
			{
				$mtime = $contents_line;
			}
		}
	}

	if ($mtime == -1)
	{
		$ebuild_file =~ s|^([^/]+)/[^/]+/([^/]+)|\1/\2|;
		fatal_error('insufficient data for ' . $ebuild_file . "\n\n" .
      "Remove this package's directory from /var/db/pkg to fix this, then start this\n" .
      "script again. If everything worked correctly, you must remerge\n" .
      $ebuild_file . ' to not mess up any dependencies.');
	}

	%mtimes->{$ebuild_file} = $mtime;
}

print "Sorting...\n";

@ebuilds = keys(%mtimes);
@ebuilds = sort({%mtimes->{$a} <=> %mtimes->{$b}} @ebuilds);

print "Writing COUNTERs...\n";

$counter = 1;
foreach $ebuild (@ebuilds)
{
	open(COUNTER, '>/var/db/pkg/' . $ebuild . '/COUNTER') or
    fatal_error('couldn\'t write to /var/db/pkg/' . $ebuild . '/COUNTER: ' . $!);
	print COUNTER $counter . "\n";
	close(COUNTER);

	$counter++;
}

print "Writing /var/cache/edb/counter...\n";

open(COUNTER, '>/var/cache/edb/counter') or
  fatal_error('couldn\'t write to /var/cache/edb/counter: ' . $!);
print COUNTER $counter . "\n";
close(COUNTER);

print "Done.\n";

