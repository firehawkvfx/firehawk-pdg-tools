import os
import time

def resolve_debug_default():
    if os.getenv('FH_VAR_DEBUG_PDG', '0') in tuple( [str(x) for x in range(11)] ):
        debug_default = int( os.getenv('FH_VAR_DEBUG_PDG', '0') ) # if numeric, then use number up to 10.
    else:
        debug_default = int( (os.getenv('FH_VAR_DEBUG_PDG', 'false').lower() in ('true', 'yes')) ) # resolve env var as int
    return debug_default

debug_default = resolve_debug_default()

class FirehawkLogger():
    def __init__(self, debug=debug_default, logger_object=None, start_time=None):
        self.debug_verbosity = debug

        if start_time is None:
            start_time = time.time()
        
        self.start_time = start_time # Start time is used to continue tracking of a log time
        self.last_time = None

        self.logger_object = logger_object # allows you to pass a custom logger object

    def initLogger(self, logger=None, log_level=None):
        """
        optional user method to init logger
        """
        return

    def set_verbosity(self, debug):
        self.debug_verbosity = debug

    def timed_info(self, start_time=None, label=''): # provides time passed since start time and time since last running of this method.
        if start_time is not None:
            self.start_time = start_time
        else:
            start_time = self.start_time
        if self.last_time is None:
            self.last_time = start_time
        
        message = "--- {} seconds --- Passed during Pre Submit --- {} seconds --- {}".format( '%.4f' % (time.time() - start_time),  '%.4f' % (time.time() - self.last_time), label )
        self.info( message )
        self.last_time = time.time()

    def timed_debug(self, message, start_time=None): # provides time passed since start time and time since last running of this method.
        if start_time is not None:
            self.start_time = start_time
        else:
            start_time = self.start_time
        if self.last_time is None:
            self.last_time = start_time
        
        message = "--- {} seconds --- Passed during Pre Submit --- {} seconds --- {}".format( '%.4f' % (time.time() - start_time),  '%.4f' % (time.time() - self.last_time), message )
        self.info( message )
        self.last_time = time.time()

    def debug(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'debug' ):
            self.logger_object.debug( message )
        else:
            if self.debug_verbosity>=10: print( message )

    def info(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'info' ):
            self.logger_object.info( message )
        else:
            if self.debug_verbosity>=5: print( message )

    def warning(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'warning' ):
            self.logger_object.warning( message )
        else:
            print( message )