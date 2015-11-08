import os.path
import StringIO

def a( files ):
    for f in files:
        print f.read()

def b( files ):
    for f in files:
        if f.name.endswith( '.txt' ):
            pipe = StringIO.StringIO()
            # todo: run in thread to allow concurrency
            pipe.write( f.read().upper() )
            pipe.seek( 0 )
            pipe.name = f.name
            yield pipe
        else:
            yield f

def c():
    for f in os.listdir( '.' ):
        if os.path.isfile( f ):
            yield open( f )

a( b( c() ) )