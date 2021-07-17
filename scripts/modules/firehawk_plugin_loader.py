# import firehawk.api and firehawk.plugins.  if user has defined custom asset creation it will be preffered.
import os
import importlib
import pkgutil
import sys
import firehawk.plugins
import firehawk.api

def resolve_debug_default():
    if os.getenv('FH_VAR_DEBUG_PDG', '0') in tuple( [str(x) for x in range(12)] ):
        debug_default = int( os.getenv('FH_VAR_DEBUG_PDG', '0') ) # if numeric, then use number up to 10.
    else:
        debug_default = int( (os.getenv('FH_VAR_DEBUG_PDG', 'false').lower() in ('true', 'yes')) ) # resolve env var as int
    return debug_default

debug_default = resolve_debug_default()

skip_plugins = int(( os.getenv('FH_SKIP_PLUGINS', 'false').lower() in ('true', 'yes', '1') )) # if FH_SKIP_PLUGINS is TRUE, only the api base will be used.

enforce_only=None
if skip_plugins:
    print('WARNING: FH_SKIP_PLUGINS is TRUE.  Will not load any user firehawk plugins.') # this env var is provided to test default behaviour.
    enforce_only='api'

def iter_namespace(ns_pkg):
    return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")
    
def load_namespace(namespace, module_name=None, verbose=debug_default, reload_module=False): # loads the contents of a namespace ie firehawk.plugins or firehawk.api and returns a list of the contained modules
    plugin_modules=[]
    for _, name, _ in iter_namespace(namespace):
        if module_name == None: # import all
            module = importlib.import_module(name)
            if verbose: print( 'import module: {}'.format( module ) )
            if reload_module and module is not None:
                reload(module)
            pkgpath = os.path.dirname(namespace.__file__)
            plugin_modules.extend( [ name for _, name, _ in pkgutil.iter_modules([pkgpath])] )
        else: # determine if single module can be imported
            pkgpath = os.path.dirname(namespace.__file__)
            module_name_list = [ mname for _, mname, _ in pkgutil.iter_modules([pkgpath])]
            if module_name in module_name_list and module_name in name:
                if verbose: print( 'importing single module: {} from namespace: {} module_name_list: {}'.format( name, namespace.__name__, module_name_list ) )
                module = importlib.import_module(name)
                if verbose: print( 'import module: {}'.format( module ) )
                if reload_module and module is not None: # reload method needs replacement in py3 with importlib.reload.  current method does not work
                    reload(module)
                pkgpath = os.path.dirname(namespace.__file__)
                plugin_modules.extend( [ name for _, name, _ in pkgutil.iter_modules([pkgpath])] )
    if verbose: print('namespace: {} module names: {}'.format( namespace.__name__, plugin_modules ) )
    return plugin_modules

def load_plugins(module_name=None, verbose=debug_default, reload_module=False): # Load all plugins and returns the list of user plugins. if module_name is provided only loads a specific module
    plugin_modules=load_namespace(firehawk.plugins, module_name=module_name, verbose=verbose, reload_module=reload_module)
    api_modules=load_namespace(firehawk.api, module_name=module_name, verbose=verbose, reload_module=reload_module)
    return plugin_modules, api_modules

def module_package(module_name, verbose=debug_default, prefer='plugin', only=None): # returns the package that contains a module, prefering a plugin if it exists over an api module.  you can enforce loading an api module with only='api'
    if enforce_only is not None: # An environment variable FH_SKIP_PLUGINS can be used to disable all plugins and test default behaviour.
        only = enforce_only
        no_ref, api_modules = load_plugins(module_name=module_name, verbose=verbose)
    else:
        plugin_modules, api_modules = load_plugins(module_name=module_name, verbose=verbose)
    package = None
    if only is None:
        if prefer == 'plugin':
            if module_name in plugin_modules:
                if verbose: print('...firehawk.plugins contains: {}.'.format( module_name ))
                package = firehawk.plugins
            elif module_name in api_modules:
                if verbose: print('...firehawk.api contains: {}.'.format( module_name ))
                package = firehawk.api
        elif prefer == 'api':
            if module_name in api_modules:
                if verbose: print('...firehawk.api contains: {}.'.format( module_name ))
                package = firehawk.api
            elif module_name in plugin_modules:
                if verbose: print('...firehawk.plugins contains: {}.'.format( module_name ))
                package = firehawk.plugins
    elif only == 'api' and module_name in api_modules:
        if verbose: print('...firehawk.api contains: {}.'.format( module_name ))
        package = firehawk.api
    elif only == 'plugin' and module_name in plugin_modules:
        if verbose: print('...firehawk.plugins contains: {}.'.format( module_name ))
        package = firehawk.plugins

    if package is None:
        print( 'ERROR aquiring package for module: {} prefer:{} only: {}'.format(module_name, prefer, only) )
    
    return package