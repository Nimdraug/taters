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
