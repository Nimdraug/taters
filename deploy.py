import os.path
import ftplib
import StringIO
import sh
import sys
import urlparse
import paramiko
import urllib

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
        print '+', f.name

        yield f

class lazy_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self._name = name
        self.file = None
        self.a = a
        self.kw = kw
        self.delete = False

    def open( self ):
        self.file = open( self._name, *self.a, **self.kw )

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

    def rename( self, name ):
        print '>', name
        self.name = name

        return self

class pipe( StringIO.StringIO ):
    def __init__( self, name, *a, **kw ):
        StringIO.StringIO.__init__( self, *a, **kw )
        self.name = name
        self.delete = False

    def reset( self ):
        self.seek( 0 )

    def rename( self, name ):
        print '>', name
        self.name = name

        return self

class ftp_dest( object ):
    def __init__( self, url ):
        self.con = None

        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )
        self.url = url

    def __call__( self, files ):
        for f in files:
            if not self.con:
                self.connect()

            f.name = os.path.join( self.url.path, f.name )

            if f.delete:
                self.rm( f )
            else:
                try:
                    self.put( f )
                except ftplib.error_perm as e:
                    if e.message.startswith( '550' ):
                        self.mkdirs( os.path.dirname( f.name ) )
                    else:
                        raise

    def connect( self ):
        self.con = ftplib.FTP( self.url.hostname, urllib.unquote( self.url.username ), urllib.unquote( self.url.password ) )

    def get( self, path ):
        self.con.cwd( os.path.dirname( path ) )

        p = pipe( path )

        self.con.retrbinary( 'RETR %s' % os.path.basename( path ), p.write )
        p.reset()

        return p

    def put( self, f ):
        print f.name
        self.con.cwd( os.path.dirname( f.name ) )

        print '%s:%s' % ( self.url.hostname, f.name )
        self.con.storbinary( 'STOR %s' % os.path.basename( f.name ), f )

    def rm( self, f ):
        try:
            self.con.cwd( os.path.dirname( f.name ) )
        except Exception, e:
            print 'FTP-ERROR: Could not change directory to', os.path.dirname( f.name )
            print e
            print 'FTP-ERROR: Could not delete', f.name
            return

        try:
            print '%s DELETE %s' % ( self.url.hostname, f.name )
            self.con.delete( os.path.basename( f.name ) )
        except Exception, e:
            print 'FTP-ERROR: Could not delete', f.name
            print e

    def mkdirs( self, path ):
        if path.startswith( '/' ):
            path = path[1:]

        if not path:
            return

        self.con.cwd( '/' )

        last_existed = True
        for p in path.split( os.sep ):
            if not last_existed or p not in self.con.nlst():
                self.con.mkd( p )
                last_existed = False
            self.con.cwd( p )

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

            if f.delete:
                print '%s DELETE %s' % ( self.url.hostname, f.name )
                sftp.remove( f.name )
            else:
                print '%s:%s' % ( self.url.hostname, f.name )
                sftp.putfo( f, f.name, callback = self.report_progress )

    def report_progress( self, a, b ):
        print a, b

def example_splitter( files ):
    for f in files:
        if f.delete:
            yield f

        if f.name in [ __file__, 'targets.py' ] or f.name.endswith( '.pyc' ):
            pass
        elif f.name.endswith( '.txt' ):
            yield uppercase( f )
        elif f.name.endswith( '.less' ):
            yield lessc( f ).rename( f.name.replace( '.less', '.css' ) )
        else:
            yield f

def dest_select( files, targets ):
    if len( sys.argv ) > 1:
        return getattr( targets, sys.argv[1] )( files )
    else:
        return targets.default( files )

def uppercase( f ):
    p = pipe( f.name )
    # todo: run in thread to allow concurrency
    p.write( f.read().upper() )
    p.reset()
    return p

def lessc( f ):
    p = pipe( f.name )
    sh.lessc( '-', _in = f, _out = p )
    p.reset()
    return p

def uglifyjs( file_paths ):
    p = pipe( '' )
    sh.uglifyjs( file_paths, _out = p )
    p.reset()
    return p

class git_source( object ):
    def __init__( self, path = '.' ):
        self.path = path

    def get_ref_commit( self, ref = 'HEAD' ):
        return str( sh.git( 'rev-parse', ref ) ).strip()

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
            mode = 'A'
            if not all_files:
                mode, fname = l.strip().split( '\t' )
            else:
                fname = l.strip()

            f = lazy_file( fname )
            if mode == 'D':
                f.delete = True

            yield f
