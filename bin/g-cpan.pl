#!/usr/bin/perl -w
# $Header$

# History: 

# 01/08/03: jrray@gentoo.org: remove dependency on Digest::MD5
#
# 01/07/03: jrray@gentoo.org: getting the way subroutines are fed variables
#	    sorted out (they're in @_)
#	    Clean out module_check, unnecessary temp variables are evil.
#	    It isn't okay to skip a module if module_check succeeds when
#	    that module is listed as a dependency for a module we're trying
#	    to install, the subsequent emerge can fail if the ebuild doesn't
#	    exist.  So only skip a module if it is a first order module from
#	    the command line but not if it is being considered to meet a
#	    dependency.
#	    Use the portage python module to learn some configuration values
#	    instead of trying to parse make.conf.
#	    Need to use system and not exec when calling out to emerge, exec
#	    ends our process!
#
# 12/09/02: baz@bluefuton.com: some further amends:
#           standardised code, declared external vars early, 
#           amended layout and sub styles for consistency and brevity,
#           also removed a 'spare' function :-)
#
# 12/07/02: mcummings: Reviewed baz's comments (thanks!). Moved the make.conf check to an external
#	     sub so that we could grab other important functions. Added Digest::MD5 so that we could
#	     check the checksum more cleanly instead of making a system call.
#	     Thanks to stocke2 for pointing me in the direction of File::Path -
#	     and helping me debug silly michael coding with rmtree
#
# 12/07/02: baz@bluefuton.com: comments added, basically a very picky code review.
#
# 12/06/02: mcummings; Added emerge functionality. Now emerges modules on the 
# fly
#
# 12/03/02: mcummings; Added checks for /var/db/pkg and manually installed 
#	modules
#
# 11/07/02: jrray : Initial upload to bug 3450
#

# modules to use - these will need to be marked as
# dependancies, and installable by portage
use strict;
use File::Spec;
use File::Path;
use CPAN;
eval 'use Digest::MD5;';
my $have_digestmd5 = $@ ? 0 : 1;

# output error if no arguments
unless (@ARGV) {
    print "Feed me perl modules\n";
    exit;
}

# Set our temporary overlay directory for the scope of this run. By setting an overlay directory,
# we bypass the predefined portage directory and allow portage to build a package outside of its
# normal tree.
my $tmp_overlay_dir = "/tmp/perl-modules_$$";
my @ebuild_list;

# Set up global paths
my $TMP_DEV_PERL_DIR = '/var/tmp/db/dev-perl';
my $MAKECONF         = '/etc/make.conf';
my ( $OVERLAY_DIR, $PORTAGE_DIR, $PORTAGE_DEV_PERL ) = get_globals();

#this should never find the dir, but just to be safe
unless ( -d $tmp_overlay_dir ) {
    mkpath( [$tmp_overlay_dir], 1, 0755 )
      or die "Couldn't create '$tmp_overlay_dir': $|";
}

# Now we cat our dev-perl directory onto our overlay directory.
# This is done so that portage records the appropriate path, i.e. dev-perl/package
my $perldev_overlay = File::Spec->catfile( $tmp_overlay_dir, 'dev-perl' );

unless ( -d $perldev_overlay ) {
    # create perldev overlay dir if not present
    mkpath( [$perldev_overlay], 1, 0755 )
      or die "Couldn't create '$perldev_overlay': $|";
}

# Now we export our overlay directory into the session's env vars
$ENV{'PORTDIR_OVERLAY'} = $tmp_overlay_dir;

# jrray printing functions
sub printbig {
    print '*' x 72, "\n";
    print '*',   "\n";
    print '*',   "\n";
    print '*  ', @_;
    print '*',   "\n";
    print '*',   "\n";
    print '*' x 72, "\n";
}

sub ebuild_exists {
    my ($dir) = @_;

    # check the main portage tree
    return 1
      if ( ( -d File::Spec->catfile( $PORTAGE_DEV_PERL, $dir ) )
        || ( -d File::Spec->catfile( $OVERLAY_DIR,      $dir ) )
        || ( -d File::Spec->catfile( $tmp_overlay_dir,  $dir ) )
        || ( -d File::Spec->catfile( $TMP_DEV_PERL_DIR, $dir ) ) );

    return 0;
}

sub module_check {

    # module_check evaluates whether a module can be loaded from @INC.
    # This allows us to assure that if a module has been manually installed, we know about it.
    my $check = shift;
    eval "use $check;";
    return $@ ? 0 : 1;
}

sub portage_dir {
    my $obj  = shift;
    my $file = $obj->cpan_file;

    # turn this into a directory name suitable for portage tree
    return unless ( $file =~ m|.*/(.*)-[^-]+\.| );
    return $1;
}

sub create_ebuild {
    my ( $module, $dir, $file, $prereq_pm, $md5 ) = @_;

    # First, make the directory
    my $fulldir  = File::Spec->catdir( $perldev_overlay, $dir );
    my $filesdir = File::Spec->catdir( $fulldir,         'files' );
    mkdir $fulldir,  0755 or die "Couldn't create '$fulldir': $!";
    mkdir $filesdir, 0755 or die "Couldn't create '$filesdir': $!";

    # What to call this ebuild?
    unless ( $file =~ m/(.*)\/(.*?)\.(?:tar|tgz|zip|bz2|gz)/ ) {
        warn("Couldn't turn '$file' into an ebuild name\n");
        return;
    }
    my ( $modpath, $filename ) = ( $1, $2 );
    my $ebuild = File::Spec->catdir( $fulldir,  "$filename.ebuild" );
    my $digest = File::Spec->catdir( $filesdir, "digest-$filename" );

    my $desc = $module->description;

    open EBUILD, ">$ebuild" or die "Could not write to '$ebuild': $!";
    print EBUILD <<"HERE";


# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2

inherit perl-module

S=\${WORKDIR}/\${P}
DESCRIPTION="$desc"
SRC_URI="http://www.cpan.org/modules/by-authors/id/$modpath/\${P}.tar.gz"
HOMEPAGE="http://www.cpan.org/modules/by-authors/id/$modpath/\${P}.readme"

SLOT="0"
LICENSE="Artistic | GPL-2"
KEYWORDS="x86 sparc sparc64 ppc alpha"

HERE

    if ( $prereq_pm && keys %$prereq_pm ) {

        print EBUILD q|DEPEND="|;

        my $first = 1;
        my %dup_check;
        for ( keys %$prereq_pm ) {

            my $obj = CPAN::Shell->expandany($_);
            my $dir = portage_dir($obj);
            next if $dir eq "perl";
            if ( ( !$dup_check{$dir} ) && ( !module_check($dir) ) ) {
                $dup_check{$dir} = 1;
                print EBUILD "\n\t" unless $first;
                print EBUILD "dev-perl/$dir";
            }
            $first = 0;
        }
        print EBUILD qq|"\n\n|;
    }

    close EBUILD;

    # write the digest too
    open DIGEST, ">$digest" or die "Could not write to '$digest': $!";
    print DIGEST $md5, "\n";
    close DIGEST;
}

sub install_module {
    my ($module_name, $recursive) = @_;

    my $obj = CPAN::Shell->expandany($module_name);
    unless ( ref $obj eq "CPAN::Module" ) {
        warn("Don't know what '$module_name' is\n");
        return;
    }

    my $file = $obj->cpan_file;
    my $dir  = portage_dir($obj);
    unless ($dir) {
        warn("Couldn't turn '$file' into a directory name\n");
        return;
    }

    if ( ebuild_exists($dir) ) {
        printbig "Ebuild already exists for '$module_name': $dir\n";
        return;

    }
    elsif ( !defined $recursive && module_check($module_name) ) {
        printbig "Module already installed for '$module_name'\n";
        return;
    }

    printbig "Need to create ebuild for '$module_name': $dir\n";

    # check depends ... with CPAN have to make the module
    # before it can tell us what the depends are, this stinks

    $CPAN::Config->{prerequisites_policy} = "";
    $CPAN::Config->{inactivity_timeout}   = 30;

    my $pack = $CPAN::META->instance( 'CPAN::Distribution', $file );
    $pack->called_for( $obj->id );
    $pack->make;
    $pack->unforce if $pack->can("unforce") && exists $obj->{'force_update'};
    delete $obj->{'force_update'};

    # grab the MD5 checksum for the source file now

    my $localfile = $pack->{localfile};
    ( my $base = $file ) =~ s/.*\/(.*)/$1/;

    my $md5digest;
    if ($have_digestmd5) {
    open( DIGIFILE, $localfile ) or die "Can't open '$file': $!";
    binmode(DIGIFILE);
	    $md5digest = Digest::MD5->new->addfile(*DIGIFILE)->hexdigest;
    close(DIGIFILE);
    } else {
    	    ($md5digest = qx(/usr/bin/md5sum $localfile)) =~ s/^(.*?)\s.*$/$1/s;
    }

    my $md5string = sprintf "MD5 %s %s %d", $md5digest, $base,
      -s $localfile;

    # make ebuilds for all the prereqs
    my $prereq_pm = $pack->prereq_pm;
    install_module($_, 1) for ( keys %$prereq_pm );

    create_ebuild( $obj, $dir, $file, $prereq_pm, $md5string );

    push @ebuild_list, $dir;
}

sub clean_up {

    #Probably don't need to do this, but for sanity's sake, we reset this var
    $ENV{'PORTDIR_OVERLAY'} = $OVERLAY_DIR;

    #Clean out the /tmp tree we were using
    rmtree( ["$tmp_overlay_dir"] );
}

sub emerge_module {
    foreach my $ebuild_name (@ebuild_list) {
        $ebuild_name =~ m/.*\/(.*)-[^-]+\./;
        print "emerging $ebuild_name\n";
        system("emerge $ebuild_name");

    }
}

sub get_globals {

    my ( $OVERLAY_DIR, $PORTAGE_DIR, $PORTAGE_DEV_PERL );

    # let's not beat around the bush here, make.conf isn't the
    # only place these variables can be defined

    eval qx(/usr/bin/python -c 'import portage; print \"\$OVERLAY_DIR=\\\"\"+portage.settings[\"PORTDIR_OVERLAY\"]+\"\\\";\"; print \"\$PORTAGE_DIR=\\\"\"+portage.settings[\"PORTDIR\"]+\"\\\";\"');
    
    unless ( length $OVERLAY_DIR && -d $OVERLAY_DIR ) {
        $OVERLAY_DIR = "";
    }

    unless ( length $PORTAGE_DIR && -d $PORTAGE_DIR ) {
        $PORTAGE_DIR = "/usr/portage";
    }

    # Finally, set the dev-perl dir explicitly
    $PORTAGE_DEV_PERL = "$PORTAGE_DIR/dev-perl";

    return ( $OVERLAY_DIR, $PORTAGE_DIR, $PORTAGE_DEV_PERL );

}

install_module($_) for (@ARGV);
emerge_module($_) for  (@ARGV);
clean_up();
