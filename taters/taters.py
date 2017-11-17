import os.path
import StringIO
import sys
import threading
import subprocess

try:
    import sh
    IS_PBS = False
except:
    import pbs as sh
    IS_PBS = True

def null_dest( files ):
    '''Null destination

    Iterates through the given source and does nothing with the resulting files'''

    for f in files:
        pass

def debug_dest( files ):
    '''Debug destination

    Outputs the name and data of each file from the given source'''

    for f in files:
        print f.name
        print '-' * len( f.name )
        if not f.delete:
            print f.read()
        else:
            print '* DELETE *'
        print

def debug_filter( files ):
    '''Debug filter

    Outputs the name of each of the files from the given source'''

    for f in files:
        print '+', f.name

        yield f

def read_all_to( f, to, chunk_size = None ):
    '''Reads all the data from the given file and passes each chunk to the given callback function'''

    while True:
        chunk = f.read( *( [ chunk_size ] if chunk_size else [] ) )

        if chunk:
            to( chunk )
        else:
            break

def read_all( f, chunk_size = None ):
    '''Reads and returns all data from the given file'''

    ret = ''
    while True:
        chunk = f.read( *( [ chunk_size ] if chunk_size else [] ) )

        if chunk:
            ret += chunk
        else:
            return ret

def tee( f ):
    '''Takes a file and returns two pipes that both give the files data'''


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
    '''Lazy file

    A file-like object which only gets opened when it is required (at read or write for instance).'''

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
        self.name = name
        return self

class pipe:
    '''Pipe

    A thread-safe pipe object which allows data to be transferred between threads.
    It provides two file-like endpoints for reading and writing with blocking when
    no data is available or when the pipe is full.'''

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
        self.name = name
        return self

def uppercase( f ):
    '''Uppercase Builder

    Takes a file and returns its data in uppercase'''

    p = pipe( f.name )

    def run():
        read_all( f, lambda chunk: p.w.write( chunk.upper() ) )
        p.w.close()

    threading.Thread( target = run ).start()

    return p.r

def _compile_args( args, kwargs ):
    processed_args = []

    # aggregate positional args
    for arg in args:
        if isinstance(arg, (list, tuple)):
            for sub_arg in arg: processed_args.append(sub_arg)
        else: processed_args.append(arg)

    # aggregate the keyword arguments
    for k,v in kwargs.items():
        # we're passing a short arg as a kwarg, example:
        # cut(d="\t")
        if len(k) == 1:
            processed_args.append("-"+k)
            if v is not True: processed_args.append(v)

        # we're doing a long arg
        else:
            k = k.replace("_", "-")

            if v is True: processed_args.append("--"+k)
            else: processed_args.append('--%s=%s' % (k, v))

    return processed_args

def _pipe_cmd( inf, outf, *cmd ):
    proc = subprocess.Popen( cmd, stdin = subprocess.PIPE, stdout = subprocess.PIPE )

    if inf:
        proc.stdin.write( read_all( inf ) )
        proc.stdin.close()
    outf.write( proc.stdout.read() )
    outf.close()

def lessc( f, *a, **kw ):
    '''less Builder

    Takes a less file and runs it through the lessc compiler and returns the resulting css file.
    Any arguments passed to the function will be passed straight to the sh command'''

    print 'B', f.name
    p = pipe( f.name )

    def run():
        _pipe_cmd( f, p.w, sh.which( 'lessc' ), '-', *_compile_args( a, kw ) )

    threading.Thread( target = run ).start()

    return p.r

def sass( f, *a, **kw ):
    '''sass/scss Builder

    Takes a sass/scss file and runs it through the sass compiler and returns the resulting css file.
    Any arguments passed to the function will be passed straight to the sh command.
    Note: to compile scss code you will need to pass the --scss flag'''

    print 'B', f.name
    p = pipe( f.name )

    def run():
        _pipe_cmd( f, p.w, sh.which( 'sass' ), '--stdin', *_compile_args( a, kw ) )

    threading.Thread( target = run ).start()

    return p.r

def uglifyjs( file_paths, *a, **kw ):
    '''JavaScript Builder

    Takes a list of js filenames and passes them to the uglifyjs compiler and returns the resulting css file
    Any arguments passed to the function will be passed straight to the sh command'''

    print 'B', ' + '.join( file_paths )
    p = pipe( '' )

    def run():
        _pipe_cmd( None, p.w, sh.which( 'uglifyjs' ), *_compile_args( [ file_paths, a ], kw ) )

    threading.Thread( target = run ).start()

    return p.r
