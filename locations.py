from deploy import lazy_file, pipe
import ftplib
import os
import paramiko
import tarfile
import urllib
import urlparse
import sh
import socket
import stat

class location( object ):
    def __init__( self, url ):
        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )
        self.url = url

    def source( self ):
        pass

    def destination( self, files ):
        pass

class local( location ):
    def __init__( self, url = '.' ):
        super( local, self ).__init__( url )

    def source( self, base_path = '', recursive = False ):
        cur_path = os.path.join( self.url.path, base_path )

        for path in os.listdir( cur_path ):
            rel_path = os.path.join( base_path, path )
            full_path = os.path.join( cur_path, path )

            if os.path.isfile( full_path ):
                yield lazy_file( full_path ).rename( rel_path )
            elif os.path.isdir( full_path ) and recursive:
                for f in self.source( rel_path, True ):
                    yield f

    def destination( self, files ):
        for f in files:
            dfn = os.path.join( self.url.path, f.name )

            # Ensure dest paths exist
            dpath = os.path.dirname( dfn )
            if not os.path.exists( dpath ):
                os.makedirs( dpath )

            if not f.delete:
                print 'local:%s' % dfn
                open( dfn, 'wb' ).write( f.read() )
            else:
                print 'local DELETE', dfn
                try:
                    os.remove( dfn )
                except OSError:
                    pass

class remote( location ):
    def __init__( self, url ):
        super( remote, self ).__init__( url )

        self.con = None

    def connect( self ):
        pass

    def destination( self, files ):
        for f in files:
            if not self.con:
                self.connect()

            if f.delete:
                self.rm( f )
            else:
                self.put( f )

class BadPassiveFTP( ftplib.FTP ):
    def makepasv(self):
        host, port = ftplib.FTP.makepasv( self )

        return socket.gethostbyname( self.host ), port

class ftp( remote ):
    def __init__( self, url, bad_passive_server = False ):
        super( ftp, self ).__init__( url )
        self.bad_passive_server = bad_passive_server

    def connect( self ):
        if self.bad_passive_server:
            self.con = ftplib.FTP()
        else:
            self.con = BadPassiveFTP()

        self.con.connect( self.url.hostname, self.url.port )
        self.con.login( urllib.unquote( self.url.username ), urllib.unquote( self.url.password ) )

    def _remote_path( self, f ):
        return os.path.join( self.url.path, os.path.dirname( f.name ) )

    def source( self, base_path = '', recursive = False ):
        if not self.con:
            self.connect()

        cur_path = os.path.join( self.url.path, base_path )

        try:
            paths = self.con.nlst( cur_path )
        except ftplib.error_perm:
            return

        if paths == [ cur_path ]:
            yield self.get( cur_path ).rename( base_path )
            return

        for path in paths:
            if path in [ '.', '..' ]:
                continue

            rel_path = os.path.join( base_path, path )

            for f in self.source( rel_path, recursive ):
                yield f

    def get( self, path ):
        p = pipe( path )
        self.con.cwd( self._remote_path( p ) )

        self.con.retrbinary( 'RETR %s' % os.path.basename( path ), p.write )
        p.reset()

        return p

    def put( self, f ):
        print f.name

        fpath = self._remote_path( f )

        try:
            self.con.cwd( fpath )
        except ftplib.error_perm as e:
            if e.message.startswith( '550' ):
                self.mkdirs( fpath )
                self.con.cwd( fpath )

        print '%s:%s' % ( self.url.hostname, f.name )
        self.con.storbinary( 'STOR %s' % os.path.basename( f.name ), f )

    def rm( self, f ):
        try:
            self.con.cwd( _remote_path( f ) )
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

class ssh( remote ):
    def connect( self ):
        self.sshcli = paramiko.SSHClient()
        self.sshcli.set_missing_host_key_policy( paramiko.AutoAddPolicy() )
        self.sshcli.connect( self.url.hostname, port = self.url.port )
        self.con = self.sshcli.open_sftp()

        try:
            self.con.chdir( self.url.path )
        except IOError:
            self.mkdirs( self.url.path )
            self.con.chdir( self.url.path )

    def source( self, base_path = '', recursive = False ):
        if not self.con:
            self.connect()

        cur_path = os.path.join( self.url.path, base_path )

        for file_attr in self.con.listdir_attr( cur_path ):
            rel_path = os.path.join( base_path, file_attr.filename )
            full_path = os.path.join( cur_path, file_attr.filename )

            if stat.S_ISDIR( file_attr.st_mode ) and recursive:
                for f in self.source( rel_path, recursive ):
                    yield f
            else:
                yield self.get( full_path ).rename( rel_path )

    def get( self, path ):
        p = pipe( path )

        self.con.getfo( path, p, callback = self.report_progress )
        p.reset()

        return p

    def put( self, f ):
        print '%s:%s' % ( self.url.hostname, f.name )
        try:
            self.con.putfo( f, f.name, callback = self.report_progress )
        except IOError:
            # Most likely that dir does not exist, create and retry
            # TODO: Causes infinite recursion on permission denied
            self.mkdirs( os.path.dirname( f.name ) )
            self.put( f )

    def report_progress( self, a, b ):
        print a, b

    def rm( self, f ):
        print '%s DELETE %s' % ( self.url.hostname, f.name )
        try:
            self.con.remove( f.name )
        except IOError:
            # Most likely file does not exist, no need to remove it then
            pass

    def mkdirs( self, path ):
        cur_path = ''
        last_existed = True

        for p in path.split( os.sep ):
            cur_path = os.path.join( cur_path, p )
            
            if last_existed:
                try:
                    self.con.stat( cur_path )
                    continue
                except IOError:
                    pass
            
            print 'creating', cur_path
            self.con.mkdir( cur_path )

class git( local ):
    def __init__( self, url = '' ):
        super( git, self ).__init__( url )

    def get_ref_commit( self, ref = 'HEAD' ):
        return str( sh.git( 'rev-parse', ref ) ).strip()

    def source( self, from_commit = None, to_commit = None ):
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

class tar( location ):
    def __init__( self, f ):
        self.f = f

    def source( self ):
        tar = tarfile.open( fileobj = self.f, mode = 'r|*' )

        for tarinfo in tar:
            yield tar.extractfile( tarinfo )

    def destination( self, files ):
        tar = tarfile.open( fileobj = self.f, mode = 'w|gz' )

        for f in files:
            f.read(0)
            tarinfo = tarfile.TarInfo( f.name )
            tarinfo.size = f.size
            tar.addfile( tarinfo, f )

class zip( location ):
    # Use zip
    # https://docs.python.org/2/library/zip.html
    pass
