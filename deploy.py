import os.path
import StringIO
import sh
import sys
import threading

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

def read_all( f, to, chunk_size = None ):
    while True:
        chunk = f.read( *( [ chunk_size ] if chunk_size else [] ) )

        if chunk:
            to( chunk )
        else:
            break

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

class pipe:
    class _reader( object ):
        def __init__( self, pipe ):
            self.pipe = pipe
            self.pos = 0
            self.delete = False

        def read( self, *a, **kw ):
            self.pipe.need_data.set()
            self.pipe.has_data.wait()
            with self.pipe.chunks_lock:
                chunk = self.pipe.chunks.pop( 0 )

                if chunk:
                    self.pos += len( chunk )

                if not len( self.pipe.chunks ):
                    self.pipe.has_data.clear()

                return chunk

        @property
        def name(self):
            return self.pipe.name

        def rename( self, name ):
            self.pipe.rename( name )
            return self

    class _writer( object ):
        def __init__( self, pipe ):
            self.pipe = pipe
            self.pos = 0
            self.delete = False

        def write( self, chunk ):
            with self.pipe.chunks_lock:
                self.pipe.chunks.append( chunk )

                if chunk:
                    self.pos += len( chunk )

                self.pipe.has_data.set()

        def close( self ):
            self.write( None )

        @property
        def name(self):
            return self.pipe.name

        def rename( self, name ):
            self.pipe.rename( name )
            return self

    def __init__( self, name ):
        self.chunks = []
        self.chunks_lock = threading.Lock()
        self.need_data = threading.Event()
        self.has_data = threading.Event()
        self.r = self._reader( self )
        self.w = self._writer( self )
        self.name = name
        self.delete = False

    def rename( self, name ):
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

    def run():
        while True:
            chunk = f.read().upper()

            if chunk:
                p.w.write( chunk )
            else:
                break

        p.w.close()

    threading.Thread( target = run ).start()

    return p.r

def lessc( f ):
    p = pipe( f.name )
    sh.lessc( '-', _in = f, _out = p.w.write, _bg = True )
    return p.r

def uglifyjs( file_paths ):
    p = pipe( '' )
    sh.uglifyjs( file_paths, _out = p.w.write, _bg = True )
    return p.r
