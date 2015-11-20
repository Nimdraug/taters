import os.path
import StringIO
import sh

def debug_dest( files ):
    for f in files:
        print f.name
        print '-' * len( f.name )
        print f.read()
        print

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
        if f.name == __file__:
            pass
        elif f.name.endswith( '.txt' ):
            yield uppercase( f )
        elif f.name.endswith( '.less' ):
            yield lessc( f, f.name.replace( '.less', '.css' ) )
        else:
            yield f

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

debug_dest( test_splitter( dirlist_source() ) )
