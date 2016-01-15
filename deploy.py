import os.path
import StringIO
import sh
import sys

def debug_dest( files ):
    for f in files:
        print f.name
        if hasattr( f, 'mode' ):
            print 'Mode: ', f.mode
        print '-' * len( f.name )
        print f.read()
        print

class lazy_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self.file = None
        self.a = a
        self.kw = kw

    def open( self ):
        self.file = open( self.name, *self.a, **self.kw )

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

class queue_file( object ):
    def __init__( self, name, *a, **kw ):
        self.name = name
        self.q = []
        self.pos = 0

    def write( self, data ):
        self.q.append( data )
        self.pos += len( data )

    def read( self ):
        if len( self.q ):
            return self.q.pop( 0 )

    def tell( self ):
        return self.pos

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

def dest_select( files, targets ):
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

class git_source( object ):
    def __init__( self, path = '.' ):
        self.path = path

    def get_ref_commit( self, ref = 'HEAD' ):
        return str( sh.git( 'rev-parse', ref ) )

    def __call__( self, from_commit = None, to_commit = None ):
        if from_commit is not None:
            if to_commit is not None:
                files = sh.git.diff( '--name-status', '--no-renames', '--color=never', from_commit, to_commit, _iter = True, _tty_out = False )
            else:
                files = sh.git.diff( '--name-status', '--no-renames', '--color=never', from_commit, _iter = True, _tty_out = False )

            all_files = False
        else:
            files = sh.git( "ls-files", _iter = True, _tty_out = False )
            all_files = True

        for l in files:
            if not all_files:
                mode, fname = l.strip().split( '\t' )
            else:
                mode = 'A'
                fname = l.strip()

            f = lazy_file( fname )
            f.mode = mode

            yield f
