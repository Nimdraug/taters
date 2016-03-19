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
                for f in dirlist_source( fpath, True )():
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
