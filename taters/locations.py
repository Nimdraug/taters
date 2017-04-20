from taters import lazy_file, pipe, read_all_to
import errno
import ftplib
import os
import paramiko
import tarfile
import urllib
import urlparse
import sh
import socket
import stat
import threading

class location( object ):
    def __init__( self, url ):
        if isinstance( url, basestring ):
            url = urlparse.urlparse( url )
        self.url = url

    def source( self ):
        pass

    def _overwrite( self, overwrite, f, path ):
        return overwrite( f, path ) if callable( overwrite ) else overwrite

    def destination( self, files, overwrite = False ):
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

    def destination( self, files, overwrite = False ):
        for f in files:
            dfn = os.path.join( self.url.path, f.name )

            # Ensure dest paths exist
            dpath = os.path.dirname( dfn )
            if not os.path.exists( dpath ):
                os.makedirs( dpath )

            if not f.delete and ( overwrite == True or not os.path.exists( dfn ) or self._overwrite( overwrite, f, dfn ) ):
                print 'local:%s' % dfn
                with open( dfn, 'wb' ) as dest:
                    read_all_to( f, dest.write )
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

    def destination( self, files, overwrite = False ):
        for f in files:
            if not self.con:
                self.connect()

            if f.delete:
                self.rm( f )
            elif overwrite == True or not self.exists( f ) or self._overwrite( overwrite, f, f.name ):
                self.put( f )

class BadPassiveFTP( ftplib.FTP ):
    def makepasv(self):
        host, port = ftplib.FTP.makepasv( self )

        return socket.gethostbyname( self.host ), port

class ftp( remote ):
    def __init__( self, url, bad_passive_server = False, timeout = socket._GLOBAL_DEFAULT_TIMEOUT, retries = 3 ):
        super( ftp, self ).__init__( url )
        self.bad_passive_server = bad_passive_server
        self.timeout = timeout
        self.retries = retries

    def connect( self ):
        print 'C', urlparse.urlunparse( self.url )
        if self.bad_passive_server:
            self.con = ftplib.FTP( timeout = self.timeout )
        else:
            self.con = BadPassiveFTP( timeout = self.timeout )

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

        cur_path = os.path.join( self.url.path, path )

        try:
            self.con.size( cur_path )
        except:
            return False

        return True

    def get( self, path ):
        print 'G', path
        p = pipe( path )

        def run():
            p.need_data.wait()
            try:
                self.con.cwd( self._remote_path( p ) )
                self._retry( self.con.retrbinary, 'RETR %s' % os.path.basename( path ), p.w.write )
            except Exception as e:
                p.w.write( e )

            p.w.close()

        threading.Thread( target = run ).start()

        return p.r

    def put( self, f ):
        print 'P', f.name

        fpath = self._remote_path( f )

        try:
            self.con.cwd( fpath )
        except ftplib.error_perm as e:
            if e.message.startswith( '550' ):
                self.mkdirs( fpath )
                self.con.cwd( fpath )

        print '%s:%s' % ( self.url.hostname, f.name )
        self._retry( self.con.storbinary, 'STOR %s' % os.path.basename( f.name ), f )

    def rm( self, f ):
        print 'R', f.name
        try:
            self.con.cwd( self._remote_path( f ) )
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
                print '+D', p
                self._retry( self.con.mkd, p )
                last_existed = False
            self.con.cwd( p )

class ssh( remote ):
    def connect( self ):
        print 'C', urlparse.urlunparse( self.url )
        self.con = paramiko.SSHClient()
        self.con.set_missing_host_key_policy( paramiko.AutoAddPolicy() )

        args = {}
        if self.url.port:
            args['port'] = self.url.port
        if self.url.username:
            args['username'] = self.url.username
        if self.url.password:
            args['password'] = self.url.password

        self.con.connect( self.url.hostname, **args )

        # Ensure base dir exists
        sftp = self.con.open_sftp()
        try:
            sftp.chdir( self.url.path )
        except IOError:
            self.mkdirs( self.url.path )

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

    def exists( self, path ):
        if not self.con:
            self.connect()

        sftp = self.con.open_sftp()

        try:
            sftp.chdir( self.url.path )
            sftp.stat( path )
        except IOError, e:
            if e.errno == errno.ENOENT:
                return False
            raise
        else:
            return True

    def get( self, path ):
        print 'G', path
        p = pipe( path )

        def run():
            p.need_data.wait()

            sftp = self.con.open_sftp()

            try:
                sftp.chdir( self.url.path )
                sftp.getfo( path, p.w, callback = self.report_progress )
            except Exception as e:
                p.w.write( e )

            p.w.close()

        threading.Thread( target = run ).start()

        return p.r

    def put( self, f ):
        print 'P', f.name

        sftp = self.con.open_sftp()
        sftp.chdir( self.url.path )

        try:
            sftp.putfo( f, f.name, callback = self.report_progress )
        except IOError:
            # Most likely that dir does not exist, create and retry
            # TODO: Causes infinite recursion on permission denied
            self.mkdirs( os.path.dirname( f.name ) )
            self.put( f )

    def report_progress( self, prog, of ):
        print '%s of %s\r' % ( prog, of ),

    def rm( self, f ):
        print 'R', f.name
        sftp = self.con.open_sftp()
        sftp.chdir( self.url.path )
        try:
            sftp.remove( f.name )
        except IOError:
            # Most likely file does not exist, no need to remove it then
            pass

    def mkdirs( self, path ):
        sftp = self.con.open_sftp()

        if path.startswith( '/' ):
            sftp.chdir( '/' )
            path = path[1:]
        else:
            sftp.chdir( self.url.path )

        cur_path = ''
        last_existed = True

        for p in path.split( os.sep ):
            cur_path = os.path.join( cur_path, p )
            
            if last_existed:
                try:
                    sftp.stat( cur_path )
                    continue
                except IOError:
                    pass
            
            print '+D', cur_path
            sftp.mkdir( cur_path )

class git( local ):
    def __init__( self, url = '' ):
        super( git, self ).__init__( url )

    def git( self, base_path = '' ):
        path = os.path.join( self.url.path, base_path )

        if path:
            return sh.git.bake( '-C', path )
        else:
            return sh.git

    def get_ref_commit( self, ref = 'HEAD', base_path = '' ):
        return str( self.git( base_path )( 'rev-parse', ref ) ).strip()

    def source( self, from_commit = None, to_commit = None, base_path = '', recursive = False ):
        git = self.git( base_path )

        if from_commit is None:
            def get_all_files():
                for f in git( "ls-tree", "--name-only", '-r', to_commit or 'HEAD', _iter = True, _tty_out = False ):
                    yield 'A', f.strip()

            files = get_all_files()
        else:
            def get_changed_files():
                args = [ '--name-status', '--no-renames', '--color=never', from_commit ]
                if to_commit:
                    args.append( to_commit )

                for f in git.diff( *args, _iter = True, _tty_out = False ):
                    yield f.strip().split( '\t' )

            files = get_changed_files()

        for mode, fname in files:
            if mode != 'D' and recursive and os.path.isdir( os.path.join( self.url.path, base_path, fname ) ):
                # Encountered a submodule in recursive mode
                # Work out its from and to commits and yield the changed files

                if not os.path.exists( os.path.join( self.url.path, base_path, fname, '.git' ) ):
                    raise Exception, 'Submodule %s not checked out!' % os.path.join( base_path, fname )

                sub_from = git( 'ls-tree', from_commit, fname ) if from_commit else None
                sub_from = sub_from.split()[2] if sub_from else None

                sub_to = git( 'ls-tree', to_commit, fname ).split()[2] if to_commit else None

                for f in self.source( sub_from, sub_to, os.path.join( base_path, fname ), recursive ):
                    yield f

                continue

            f = lazy_file( os.path.join( self.url.path, base_path, fname ) )

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
