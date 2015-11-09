import os.path
import StringIO

def debug_dest( files ):
    for f in files:
        print f.name
        print '-' * len( f.name )
        print f.read()
        print

def test_splitter( files ):
    for f in files:
        if f.name == __file__:
            pass
        elif f.name.endswith( '.txt' ):
            yield uppercase( f )
        else:
            yield f

def uppercase( f ):
    pipe = StringIO.StringIO()
    # todo: run in thread to allow concurrency
    pipe.write( f.read().upper() )
    pipe.seek( 0 )
    pipe.name = f.name
    return pipe

def dirlist_source():
    for f in os.listdir( '.' ):
        if os.path.isfile( f ):
            yield open( f )

debug_dest( test_splitter( dirlist_source() ) )
