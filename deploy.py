import os.path
import StringIO
import sh
import sys
import urlparse
import paramiko
from ftplib import FTP

def debug_dest( files ):
    for f in files:
        print f.name
        if hasattr( f, 'mode' ):
            print 'Mode: ', f.mode
        print '-' * len( f.name )
        print f.read()
        print

def debug_pipe( files ):
    for f in files:
        print f.name

        yield f

class local_dest( object ):
    def __init__( self, path ):
        self.path = path

    def __call__( self, files ):
        for f in files:
            dfn = os.path.join( self.path, f.name )

            # Ensure dest paths exist
            dpath = os.path.dirname( dfn )
            if not os.path.exists( dpath ):
                os.makedirs( dpath )

            if f.mode != 'D':
                print 'Deploying %s as %s...' % ( f.name, dfn ),
                open( dfn, 'wb' ).write( f.read() )
                print 'Done'
            else:
                print 'Removing %s...' % ( dfn ),
                os.remove( dfn )
                print 'Done'

class lazy_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self.file = None
        self.a = a
        self.kw = kw

    def open( self ):
        self.file = open( self.name, *self.a, **self.kw )

    def read( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.read( *a, **kw )

    def write( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.write( *a, **kw )

    def seek( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.seek( *a, **kw )

    def tell( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.tell( *a, **kw )

class queue_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self.q = []
        self.pos = 0

    def write( self, data ):
        self.q.append( data )
        self.pos += len( data )

    def read( self ):
        if len( self.q ):
            return self.q.pop( 0 )

    def tell( self ):
        return self.pos

class ftp_dest( object ):
    def __init__( self, url ):
        self.con = None

        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )
        self.url = url

    def __call__( files ):
        for f in files:
            if not self.con:
                self.connect()

            if f.delete:
                self.rm( f )
            else:
                self.put( f )

    def connect( self ):
        self.con = FTP( self.url.hostname, urllib.unquote( self.url.username ), urllib.unquote( self.url.password ) )

    def get( self, from_path, to_path = None ):
        if to_path is None:
            to_path = from_path

        env.ftp_con.cwd( os.path.dirname( from_path ) )

        env.ftp_con.retrbinary( 'RETR %s' % os.path.basename( from_path ), file( to_path, 'wb' ).write )

        return [ to_path ]

    def put( self, f ):
        self.con.cwd( os.path.dirname( f.name ) )

        self.con.storbinary( 'STOR %s' % os.path.basename( f.name ), f )

    def rm( self, fpath ):
        try:
            env.ftp_con.cwd( os.path.dirname( fpath ) )
        except Exception, e:
            print 'FTP-ERROR: Could not change directory to', os.path.dirname( fpath )
            print e
            print 'FTP-ERROR: Could not delete', fpath
            return

        try:
            env.ftp_con.delete( os.path.basename( fpath ) )
        except Exception, e:
            print 'FTP-ERROR: Could not delete', fpath
            print e


class ssh_dest( object ):
    def __init__( self, url ):
        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )

        self.url = url

    def __call__( self, files ):
        print 'Connecting to', self.url.hostname
        con = paramiko.SSHClient()
        con.set_missing_host_key_policy( paramiko.AutoAddPolicy() )
        con.connect( self.url.hostname, port = self.url.port )
        sftp = con.open_sftp()
        sftp.chdir( self.url.path )

        for f in files:
            path = os.path.dirname( f.name )
            
            try:
                sftp.stat( path )
            except IOError:
                sftp.mkdir( path )

            print 'Deploying %s...' % ( f.name ),
            sftp.putfo( f, f.name, callback = self.report_progress )
            print 'Done'

    def report_progress( self, a, b ):
        print a, b

def test_splitter( files ):
    for f in files:
        if f.name in [ __file__, 'targets.py' ] or f.name.endswith( '.pyc' ):
            pass
        elif f.name.endswith( '.txt' ):
            yield uppercase( f )
        elif f.name.endswith( '.less' ):
            yield lessc( f, f.name.replace( '.less', '.css' ) )
        else:
            yield f

def dest_select( files, targets ):
    if len( sys.argv ) > 1:
        return getattr( targets, sys.argv[1] )( files )
    else:
        return targets.default( files )

def uppercase( f ):
    pipe = StringIO.StringIO()
    # todo: run in thread to allow concurrency
    pipe.write( f.read().upper() )
    pipe.seek( 0 )
    pipe.name = f.name
    return pipe

def lessc( f, d ):
    pipe = StringIO.StringIO()
    pipe.name = d
    sh.lessc( '-', _in = f, _out = pipe )
    pipe.seek( 0 )
    return pipe

class dirlist_source( object ):
    def __init__( self, path = '.', recursive = True ):
        self.path = path
        self.recursive = recursive

    def __call__( self ):
        for fpath in os.listdir( self.path ):
            fpath = os.path.relpath( os.path.join( self.path, fpath ) )
            if os.path.isfile( fpath ):
                yield lazy_file( fpath )
            elif os.path.isdir( fpath ) and self.recursive:
                for f in dirlist_source( fpath, True )():
                    yield f

class git_source( object ):
    def __init__( self, path = '.' ):
        self.path = path

    def get_ref_commit( self, ref = 'HEAD' ):
        return str( sh.git( 'rev-parse', ref ) )

    def __call__( self, from_commit = None, to_commit = None ):
        if from_commit is not None:
            if to_commit is not None:
                files = sh.git.diff( '--name-status', '--no-renames', '--color=never', from_commit, to_commit, _iter = True, _tty_out = False )
            else:
                files = sh.git.diff( '--name-status', '--no-renames', '--color=never', from_commit, _iter = True, _tty_out = False )

            all_files = False
        else:
            files = sh.git( "ls-files", _iter = True, _tty_out = False )
            all_files = True

        for l in files:
            if not all_files:
                mode, fname = l.strip().split( '\t' )
            else:
                mode = 'A'
                fname = l.strip()

            f = lazy_file( fname )
            f.mode = mode

            yield f
