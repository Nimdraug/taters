import os.path

def a( files ):
    for f in files:
        print f.read()

def b( files ):
    for f in files:
        if f.name.endswith( '.txt' ):
            pipe = object()
            # todo: run in thread to allow concurrency
            pipe.write( f.read().upper() )
            yield pipe

def c():
    for f in os.listdir( '.' ):
        if os.path.isfile( f ):
            yield open( f )

a( b( c() ) )