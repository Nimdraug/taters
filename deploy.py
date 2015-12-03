import os.path
import StringIO
import sh
import targets
import sys

def debug_dest( files ):
    for f in files:
        print f.name
        print '-' * len( f.name )
        print f.read()
        print

class lazy_file( object ):
    def __init__( self, fname, *a, **kw ):
        self.fname = fname
        self.file = None
        self.a = a
        self.kw = kw

    def open( self ):
        self.file = open( self.fname, *self.a, **self.kw )

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

class ftp_dest( object ):
    def __init__( self, url ):
        self.url = url
        self.con = None

    def __call__( files ):
        for f in files:
            if not self.con:
                self.connect()

            if f.delete:
                self.rm( f )
            else:
                self.put( f )

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

def dest_select( files ):
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

def dirlist_source():
    for f in os.listdir( '.' ):
        if os.path.isfile( f ):
            yield open( f )

if __name__ == '__main__':
    dest_select( test_splitter( dirlist_source() ) )
