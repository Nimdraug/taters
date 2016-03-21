import os.path
import StringIO
import sh
import sys

def null_dest( files ):
    for f in files:
        pass

def debug_dest( files ):
    for f in files:
        print f.name
        if hasattr( f, 'mode' ):
            print 'Mode: ', f.mode
        print '-' * len( f.name )
        print f.read()
        print

def debug_pipe( files ):
    for f in files:
        print '+', f.name

        yield f

class lazy_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self._name = name
        self.file = None
        self.size = 0
        self.a = a
        self.kw = kw
        self.delete = False

    def open( self ):
        self.file = open( self._name, *self.a, **self.kw )
        self.size = os.stat( self._name ).st_size

    def read( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.read( *a, **kw )

    def write( self, data, *a, **kw ):
        if not self.file:
            self.open()

        self.size += len( data )

        return self.file.write( data, *a, **kw )

    def seek( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.seek( *a, **kw )

    def tell( self, *a, **kw ):
        if not self.file:
            self.open()

        return self.file.tell( *a, **kw )

    def rename( self, name ):
        print '>', name
        self.name = name

        return self

class pipe( StringIO.StringIO ):
    def __init__( self, name, *a, **kw ):
        StringIO.StringIO.__init__( self, *a, **kw )
        self.name = name
        self.size = 0
        self.delete = False

    def write( self, data, *a, **kw ):
        super( pipe, self ).write( data, *a, **kw )
        self.size += len( data )

    def reset( self ):
        self.seek( 0 )

    def rename( self, name ):
        print '>', name
        self.name = name

        return self

def example_splitter( files ):
    for f in files:
        if f.delete:
            yield f

        if f.name in [ __file__, 'targets.py' ] or f.name.endswith( '.pyc' ):
            pass
        elif f.name.endswith( '.txt' ):
            yield uppercase( f )
        elif f.name.endswith( '.less' ):
            yield lessc( f ).rename( f.name.replace( '.less', '.css' ) )
        else:
            yield f

def dest_select( files, targets ):
    if len( sys.argv ) > 1:
        return getattr( targets, sys.argv[1] )( files )
    else:
        return targets.default( files )

def uppercase( f ):
    p = pipe( f.name )
    # todo: run in thread to allow concurrency
    p.write( f.read().upper() )
    p.reset()
    return p

def lessc( f ):
    p = pipe( f.name )
    sh.lessc( '-', _in = f, _out = p )
    p.reset()
    return p

def uglifyjs( file_paths ):
    p = pipe( '' )
    sh.uglifyjs( file_paths, _out = p )
    p.reset()
    return p
