import os.path
import StringIO

def a( files ):
    for f in files:
        print f.name
        print '-' * len( f.name )
        print f.read()
        print


def b( files ):
    for f in files:
        if f.name.endswith( '.txt' ):
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


def c():
    for f in os.listdir( '.' ):
        if os.path.isfile( f ):
            yield open( f )

a( b( c() ) )