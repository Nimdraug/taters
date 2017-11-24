from taters import lazy_file, pipe, read_all_to
import errno
import ftplib
import furl
import os
import paramiko
import tarfile
import urllib
import sh
import socket
import stat
import threading

def _decode_furl_path( path ):
    '''decodes furl.Path to unicode string'''
    return urllib.unquote( str( path ) ).decode( 'utf8' )

class location( object ):
    '''Base Location'''

    def __init__( self, url ):
        if isinstance( url, basestring ):
            url = furl.furl( url )
        self.url = url

    def sub_location( self, path ):
        url = self.url.copy().add( path = path )

        return self.__class__( url )

    def _full_path( self, path ):
        return _decode_furl_path( self.url.copy().path.add( path ) )

    def _listdir( self ):
        raise NotImplemented

    def isdir( self, path ):
        raise NotImplemented

    def mkdirs( self, path ):
        raise NotImplemented

    def open( self, path, *a, **kw ):
        raise NotImplemented

    def stat( self, path ):
        raise NotImplemented

    def exists( self, path ):
        raise NotImplemented

    def get( self, path ):
        raise NotImplemented

    def put( self, f ):
        raise NotImplemented

    def rm( self, f ):
        raise NotImplemented

    def source( self, recursive = False ):
        for path in self._listdir():
            if self.isdir( path ):
                if recursive:
                    for f in self.sub_location( path ).source( True ):
                        yield f.rename( os.path.join( path, f.name ) )
            else:
                yield self.get( path )

    def _overwrite( self, overwrite, f ):
        return overwrite( self, f ) if callable( overwrite ) else overwrite

    def destination( self, files, overwrite = False ):
        for f in files:
            if f.delete:
                self.rm( f )
            elif overwrite == True or not self.exists( f.name ) or self._overwrite( overwrite, f ):
                self.put( f )

class local( location ):
    '''Local Location

    Represents a location on your local filesystem'''

    def __init__( self, url = '.' ):
        super( local, self ).__init__( url )

    def _listdir( self ):
        for path in os.listdir( _decode_furl_path( self.url.path ) ):
            yield path

    def isdir( self, path ):
        return os.path.isdir( self._full_path( path ) )

    def mkdirs( self, path ):
        os.makedirs( self._full_path( path ) )

    def open( self, path, *a, **kw ):
        return open( self._full_path( path ), *a, **kw )

    def stat( self, path ):
        return os.stat( self._full_path( path ) )

    def exists( self, path ):
        return os.path.exists( self._full_path( path ) )

    def get( self, path ):
        f = lazy_file( self._full_path( path ) )
        f.name = path
        return f

    def put( self, f ):
        print 'local:%s' % f.name

        # Ensure dest paths exist
        dirpath = os.path.dirname( f.name )
        if not self.exists( dirpath ):
            self.mkdirs( dirpath )

        with open( self._full_path( f.name ), 'wb' ) as dest:
            read_all_to( f, dest.write )

    def rm( self, f ):
        print 'local DELETE', f.name
        try:
            os.remove( self._full_path( f.name ) )
        except OSError:
            pass

class remote( location ):
    '''Base Remote Location'''

    def __init__( self, url ):
        super( remote, self ).__init__( url )

        self.con = None

    def sub_location( self, path ):
        loc = super( remote, self ).sub_location( path )
        loc.con = self.con

        return loc

    def connect( self ):
        pass

class BadPassiveFTP( ftplib.FTP ):
    '''Use this instead of ftplib.FTP if the ftp server requires passive mode'''

    def makepasv(self):
        host, port = ftplib.FTP.makepasv( self )

        return socket.gethostbyname( self.host ), port

class ftp( remote ):
    '''FTP Location

    Represents a location on an FTP server'''

    def __init__( self, url, passive = True, bad_passive_server = False, timeout = socket._GLOBAL_DEFAULT_TIMEOUT, retries = 3 ):
        super( ftp, self ).__init__( url )
        self.bad_passive_server = bad_passive_server
        self.passive = passive
        self.timeout = timeout
        self.retries = retries

    def connect( self ):
        print 'C', self.url.url
        if self.bad_passive_server:
            self.con = ftplib.FTP( timeout = self.timeout )
        else:
            self.con = BadPassiveFTP( timeout = self.timeout )

        self.con.connect( self.url.host, self.url.port )
        self.con.login( urllib.unquote( self.url.username ), urllib.unquote( self.url.password ) )
        self.con.set_pasv( self.passive )

    def _remote_path( self, f ):
        return os.path.join( self.url.path, os.path.dirname( f.name ) )

    def _listdir( self ):
        if not self.con:
            self.connect()

        for path in self.con.nlst( _decode_furl_path( self.url.path ) ):
            if path in [ '.', '..' ]:
                continue

            yield path

    def isdir( self, path ):
        if not self.con:
            self.connect()

        full_path = self._full_path( path )

        try:
            self.con.cwd( full_path )
        except ftplib.error_perm, e:
            if e.message.endswith( 'Not a directory' ):
                return False
            raise e

        return True

    def _retry( self, func, *a, **kw ):
        for t in range( self.retries ):
            try:
                func( *a, **kw )
            except socket.timeout:
                if t < self.retries:
                    print 'Timedout! Retrying (%s of %s)' % ( t + 1, self.retries - 1 )
                    continue
                else:
                    print 'Timedout! Out of retries!'
                    raise
            else:
                break

    def exists( self, path ):
        if not self.con:
            self.connect()

        try:
            self.con.size( self._full_path( path ) )
        except:
            return False

        return True

    def get( self, path ):
        if not self.con:
            self.connect()

        print 'G', path
        p = pipe( path )
        full_path = self._full_path( path )

        def run():
            p.need_data.wait()
            try:
                self.con.cwd( os.path.dirname( full_path ) )
                self._retry( self.con.retrbinary, 'RETR %s' % os.path.basename( full_path ), p.w.write )
            except Exception as e:
                p.w.write( e )

            p.w.close()

        threading.Thread( target = run ).start()

        return p.r

    def put( self, f ):
        if not self.con:
            self.connect()

        print 'P', f.name

        dir_path = os.path.dirname( self._full_path( f.name ) )

        try:
            self.con.cwd( dir_path )
        except ftplib.error_perm as e:
            if e.message.startswith( '550' ):
                self.mkdirs( os.path.dirname( f.name ) )
                self.con.cwd( dir_path )

        print '%s:%s' % ( self.url.host, f.name )
        self._retry( self.con.storbinary, 'STOR %s' % os.path.basename( f.name ), f )

    def rm( self, f ):
        if not self.con:
            self.connect()

        print 'R', f.name

        dir_path = os.path.dirname( self._full_path( f.name ) )

        try:
            self.con.cwd( dir_path )
        except Exception, e:
            print 'FTP-ERROR: Could not change directory to', os.path.dirname( f.name )
            print e
            print 'FTP-ERROR: Could not delete', f.name
            return

        try:
            print '%s DELETE %s' % ( self.url.host, f.name )
            self.con.delete( os.path.basename( f.name ) )
        except Exception, e:
            print 'FTP-ERROR: Could not delete', f.name
            print e

    def mkdirs( self, path ):
        if not self.con:
            self.connect()

        full_path = self._full_path( path )

        if full_path.startswith( '/' ):
            full_path = full_path[1:]

        if not full_path:
            return

        self.con.cwd( '/' )

        last_existed = True
        for segment in full_path.split( os.sep ):
            if not last_existed or segment not in self.con.nlst():
                print '+D', segment
                self._retry( self.con.mkd, segment )
                last_existed = False
            self.con.cwd( segment )

class ssh( remote ):
    '''SSH Location

    Represents a location on an SSH server'''

    def connect( self ):
        print 'C', self.url.url
        self.con = paramiko.SSHClient()
        self.con.set_missing_host_key_policy( paramiko.AutoAddPolicy() )

        args = {}
        if self.url.port:
            args['port'] = self.url.port
        if self.url.username:
            args['username'] = self.url.username
        if self.url.password:
            args['password'] = self.url.password

        self.con.connect( self.url.host, **args )

    def _listdir( self ):
        if not self.con:
            self.connect()

        for file_attrs in self.con.open_sftp().listdir_iter( _decode_furl_path( self.url.path ) ):
            yield file_attrs.filename

    def isdir( self, path ):
        if not self.con:
            self.connect()

        return stat.S_ISDIR( self.con.open_sftp().stat( self._full_path( path ) ).st_mode )

    def exists( self, path ):
        if not self.con:
            self.connect()

        sftp = self.con.open_sftp()

        full_path = self._full_path( path )

        try:
            sftp.stat( full_path )
        except IOError, e:
            if e.errno == errno.ENOENT:
                return False
            raise
        else:
            return True

    def get( self, path ):
        if not self.con:
            self.connect()

        full_path = self._full_path( path )

        print 'G', path
        p = pipe( path )

        def run():
            p.need_data.wait()

            sftp = self.con.open_sftp()

            try:
                sftp.getfo( full_path, p.w, callback = self.report_progress )
            except Exception as e:
                p.w.write( e )

            p.w.close()

        threading.Thread( target = run ).start()

        return p.r

    def put( self, f ):
        if not self.con:
            self.connect()

        print 'P', f.name

        sftp = self.con.open_sftp()

        dir_path = os.path.dirname( f.name )

        if not self.exists( dir_path ):
            self.mkdirs( dir_path )

        full_path = self._full_path( f.name )

        sftp.putfo( f, full_path, callback = self.report_progress )

    def report_progress( self, prog, of ):
        print '%s of %s\r' % ( prog, of ),

    def rm( self, f ):
        if not self.con:
            self.connect()

        print 'R', f.name
        sftp = self.con.open_sftp()

        try:
            sftp.remove( self._full_path( f.name ) )
        except IOError:
            # Most likely file does not exist, no need to remove it then
            pass

    def mkdirs( self, path ):
        if not self.con:
            self.connect()

        sftp = self.con.open_sftp()

        full_path = self._full_path( path )

        if full_path.startswith( '/' ):
            sftp.chdir( '/' )
            full_path = full_path[1:]

        cur_path = ''
        last_existed = True

        for p in full_path.split( os.sep ):
            cur_path = os.path.join( cur_path, p )
            
            if last_existed:
                try:
                    sftp.stat( cur_path )
                    continue
                except IOError:
                    pass
            
            last_existed = False
            print '+D', cur_path
            sftp.mkdir( cur_path )

class git( local ):
    '''GIT Location

    Represents a local git repository. Allows you to limit the files given in the source to files that where changed between two git revisions'''

    def __init__( self, url = '' ):
        super( git, self ).__init__( url )

        if self.url.path:
            self.git = sh.git.bake( '-C', _decode_furl_path( self.url.path ) )
        else:
            self.git = sh.git

    def get_ref_commit( self, ref = 'HEAD' ):
        return str( self.git( 'rev-parse', ref ) ).strip()

    def _listdir( self, from_commit = None, to_commit = None ):
        if from_commit is None:
            # List all files
            for f in self.git( "ls-tree", "--name-only", '-r', to_commit or 'HEAD', _iter = True, _tty_out = False ):
                yield 'A', f.strip()
        else:
            # List only changed files
            args = [ '--name-status', '--no-renames', '--color=never', from_commit ]
            if to_commit:
                args.append( to_commit )

            for f in self.git.diff( *args, _iter = True, _tty_out = False ):
                yield f.strip().split( '\t' )

    def source( self, from_commit = None, to_commit = None, recursive = False ):
        for mode, fname in self._listdir( from_commit, to_commit ):
            if mode != 'D' and recursive and self.isdir( fname ):
                # Encountered a submodule in recursive mode
                # Work out its from and to commits and yield the changed files

                if not self.exists( os.path.join( fname, '.git' ) ):
                    raise Exception, 'Submodule %s not checked out!' % fname

                sub_from = self.git( 'ls-tree', from_commit, fname ) if from_commit else None
                sub_from = sub_from.split()[2] if sub_from else None

                sub_to = self.git( 'ls-tree', to_commit, fname ).split()[2] if to_commit else None

                for f in self.sub_location( fname ).source( sub_from, sub_to, recursive ):
                    yield f.rename( os.path.join( fname, f.name ) )

                continue

            f = self.get( fname )

            if mode == 'D':
                f.delete = True

            yield f

class tar( location ):
    '''Tar file Location

    Represents the files inside a tar archive as a location, allowing files to be extracted or zipped up.

    TODO: Fix me!'''

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
    '''Zip file Location

    Represents the files inside a zip archive as a location, allowing files to be extracted or zipped up.

    TODO: Implement me!'''
    # Use zip
    # https://docs.python.org/2/library/zip.html
    pass
