from deploy import lazy_file
import ftplib
import os
import paramiko
import urllib
import urlparse

class location( object ):
    def __init__( self, url ):
        self.url = url

    def source( self ):
        pass

    def destination( self, files ):
        pass

class local_location( location ):
    def source( self, recursive = False ):
        for fpath in os.listdir( self.url ):
            fpath = os.path.relpath( os.path.join( self.url, fpath ) )
            if os.path.isfile( fpath ):
                yield lazy_file( fpath )
            elif os.path.isdir( fpath ) and recursive:
                for f in local_location( fpath ).source( True ):
                    yield f

    def destination( self, files ):
        for f in files:
            dfn = os.path.join( self.url, f.name )

            # Ensure dest paths exist
            dpath = os.path.dirname( dfn )
            if not os.path.exists( dpath ):
                os.makedirs( dpath )

            if not f.delete:
                print 'local:%s' % dfn
                open( dfn, 'wb' ).write( f.read() )
            else:
                print 'local DELETE', dfn
                os.remove( dfn )

class remote_location( location ):
    def __init__( self, url ):
        self.con = None

        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )
        self.url = url

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

class ftp_location( remote_location ):
    def destination( self, files ):
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
                        self.put( f )
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

class ssh_location( remote_location ):
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

    def put( self, f ):
        print '%s:%s' % ( self.url.hostname, f.name )
        try:
            self.con.putfo( f, f.name, callback = self.report_progress )
        except IOError:
            # Most likely that dir does not exist, create and retry
            self.mkdirs( os.path.dirname( f.name ) )
            self.put( f )

    def report_progress( self, a, b ):
        print a, b

    def rm( self, f ):
        print '%s DELETE %s' % ( self.url.hostname, f.name )
        self.con.remove( f.name )

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
