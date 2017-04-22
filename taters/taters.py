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

def debug_filter( files ):
    for f in files:
        print '+', f.name

        yield f

def read_all_to( f, to, chunk_size = None ):
    while True:
        chunk = f.read( *( [ chunk_size ] if chunk_size else [] ) )

        if chunk:
            to( chunk )
        else:
            break

def read_all( f, chunk_size = None ):
    ret = ''
    while True:
        chunk = f.read( *( [ chunk_size ] if chunk_size else [] ) )

        if chunk:
            ret += chunk
        else:
            return ret

def tee( f ):
    p1 = pipe( f.name )
    p2 = pipe( f.name )

    def run():
        def write( chunk ):
            p1.w.write( chunk )
            p2.w.write( chunk )

        read_all_to( f, write )

        p1.w.close()
        p2.w.close()

    threading.Thread( target = run ).start()

    return p1.r, p2.r

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

                if isinstance( chunk, Exception ):
                    raise chunk
                elif chunk:
                    self.pos += len( chunk )
                    self.pipe.chunk_size -= len( chunk )

                    if self.pipe.chunk_size < self.pipe.chunk_max:
                        self.pipe.not_full.set()

                if not len( self.pipe.chunks ):
                    self.pipe.has_data.clear()

                return chunk

        @property
        def name(self):
            return self.pipe.name

        def rename( self, name ):
            self.pipe.rename( name )
            return self

        def flush( self ):
            pass

    class _writer( object ):
        def __init__( self, pipe ):
            self.pipe = pipe
            self.pos = 0
            self.delete = False

        def write( self, chunk ):
            self.pipe.not_full.wait()
            with self.pipe.chunks_lock:
                self.pipe.chunks.append( chunk )

                if isinstance( chunk, Exception ):
                    pass
                elif chunk:
                    self.pos += len( chunk )
                    self.pipe.chunk_size += len( chunk )

                    if self.pipe.chunk_size >= self.pipe.chunk_max:
                        print 'full!'
                        self.pipe.not_full.clear()

                self.pipe.has_data.set()

        def close( self ):
            self.write( '' )

        @property
        def name(self):
            return self.pipe.name

        def rename( self, name ):
            self.pipe.rename( name )
            return self

        def flush( self ):
            pass

    def __init__( self, name, chunk_max = 8 * 1024 * 1024 ):
        self.chunks = []
        self.chunks_lock = threading.Lock()
        self.chunk_size = 0
        self.chunk_max = chunk_max
        self.need_data = threading.Event()
        self.has_data = threading.Event()
        self.not_full = threading.Event()
        self.not_full.set()
        self.r = self._reader( self )
        self.w = self._writer( self )
        self.name = name
        self.delete = False

    def rename( self, name ):
        print '>', name
        self.name = name

        return self

def dest_select( files, targets ):
    if len( sys.argv ) > 1:
        return getattr( targets, sys.argv[1] )( files )
    else:
        return targets.default( files )

def uppercase( f ):
    p = pipe( f.name )

    def run():
        read_all( f, lambda chunk: p.w.write( chunk.upper() ) )
        p.w.close()

    threading.Thread( target = run ).start()

    return p.r

def lessc( f, *a, **kw ):
    print 'B', f.name
    p = pipe( f.name )

    def run():
        sh.lessc( '-', *a, _in = f, _out = p.w, **kw )
        p.w.close()

    threading.Thread( target = run ).start()

    return p.r

def uglifyjs( file_paths, *a, **kw ):
    print 'B', ' + '.join( file_paths )
    p = pipe( '' )

    def run():
        sh.uglifyjs( file_paths, *a, _out = p.w, **kw )
        p.w.close()

    threading.Thread( target = run ).start()

    return p.r
