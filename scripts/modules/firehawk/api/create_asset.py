# firehawk.api: This plugin creates an asset from a work item

import os
import re
import traceback

import firehawk_plugin_loader
import firehawk.plugins
import firehawk.api
plugin_modules, api_modules=firehawk_plugin_loader.load_plugins(module_name='submit_logging') # load modules in the firehawk.api namespace
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=0)

firehawk_logger.timed_info(label='create_asset plugin loaded')
firehawk_logger.debug('test debug logger')

from os.path import sep, join
def pjoin(*args, **kwargs):
    return join(*args, **kwargs).replace(sep, '/') # for windows compatibility.

def add_dependency(path, ancestor_path): # this is an asset dependency db hook, not execution dependency
    return

def rebuild_tags(tags): # A method that can be customised to rebuild / alter tags used for asset creation.  For example, and output type of 'rendering', may require an extension tag to be customised.  This method can be patched to do so.
    return tags

def get_tags_for_submission_hip(hip_name, element='pdg_setup', variant='', parent_top_net=None):
    if parent_top_net is None:
        raise Exception('ERROR: parent_top_net not provided: get_tags_for_submission_hip()')

    job_value = parent_top_net.parm('job').evalAsString()
    seq_value = parent_top_net.parm('seq').evalAsString()
    shot_value = parent_top_net.parm('shot').evalAsString()

    if False in [ len(x)>0 for x in [ job_value, seq_value, shot_value ] ]:
        raise Exception('ERROR: job, seq, shot parm not set on topnet: get_tags_for_submission_hip()')
        # msg += '\n\nEnsure the env vars JOB / SEQ / SHOT are defined before running houdini.\nThis allows the asset handler to save a root timestamped version of the hip file for the submission.'
        # hou.ui.displayMessage(msg)

    tags = {
        'job': job_value,
        'seq': seq_value,
        'shot': shot_value,
        'element': element,
        'variant': variant,
        'asset_type': 'setup',
        'format': 'hip',
        'version': -1, # When -1, the asset function will auto increment the version.
        'volatile': False,
        'pdg_dir': os.path.dirname( hip_name ) # pdg_dir is used by default for asset creation, but can be ignored if you create a custom asset method.
    }
    return tags

def returnExtension(**tags): # some formats are not literal extensions, so we extract those here.
    if tags['format'] == 'vdbpoints': 
        tags['extension'] = 'vdb' # path creation for vdb points needs to be remapped
    else:
        tags['extension'] = tags['format']
    return tags['extension']

def returnFileName(**tags): # format's the provided tags and version into a file name.  The extension is also a subfolder under the asset path.
    if 'dir_name' not in tags.keys(): tags['dir_name'] = None
    tags['extension'] = returnExtension(**tags)
    
    if 'format' in tags.keys() and 'dir_name' in tags.keys(): # append the format into the path if it is known
        tags['dir_name'] = pjoin(tags['dir_name'], tags['extension'])

    if tags['asset_type']=='setup':
        tags['file_name'] = '{}_{}_{}_{}_{}_{}.{}'.format(tags['job'], tags['seq'], tags['shot'], tags['element'], tags['variant'], tags['version_str'], tags['extension'])
    elif 'animating_frames' in tags.keys() and 'format' in tags.keys(): # if format and animating_frames ('single' or '$F4') are provided, then a file name can also be returned'
        tags['file_name'] = '{}_{}_{}_{}_{}_{}.{}.{}'.format(tags['job'], tags['seq'], tags['shot'], tags['element'], tags['variant'], tags['version_str'], tags['animating_frames'], tags['extension'])
    else:
        tags['file_name'] = None

    firehawk_logger.debug( "tags['dir_name'] : {}, tags['file_name'] {}".format( tags['dir_name'], tags['file_name'] ) )

    return tags['dir_name'], tags['file_name']

def _ensure_dir_exists(dir_name):
    if not os.path.exists(dir_name):
        try:
            os.makedirs(dir_name)
        except:
            firehawk_logger.warning('Could not create path: {} Check permissions.'.format( dir_name ) )
            return

def _create_asset(tags, auto_version=True, version_str=None, create_dirs=True): # This example function creates an asset by simply making a new directory, but it is also possible to replace this with the ability to request a new asset from a db/server.  The method can also return a path without creating a directory.  This method should not be referenced externally. 
    firehawk_logger.debug('_create_asset:')

    if 'pdg_dir' not in tags: # if PDG_DIR was not resolved, we will not be creating an asset.
        create_dirs = False
        pdg_dir = '__PDG_DIR__'
    else:
        pdg_dir = tags['pdg_dir']
    
    default_prod_root= pjoin( os.path.normpath( pdg_dir ) , 'output' ) # if pdg dir is not in tags, resolve standard houdini placeholder

    prod_root = os.getenv('PROD_ROOT', default_prod_root) # the env var PROD_ROOT can override an absolute output path.

    dir_name = pjoin(prod_root, tags['job'], tags['seq'], tags['shot'], tags['element'], tags['variant'], tags['asset_type']) # the base path before the version folder
    firehawk_logger.debug('_create_asset: {}'.format(dir_name))
    if create_dirs: _ensure_dir_exists(dir_name)

    if auto_version: # aquire the next version for output and create the directory.

        contained_dirs = os.listdir(dir_name)

        firehawk_logger.debug('contained_dirs: {}'.format( contained_dirs ))
        version_int_list = [ version_str_to_int(x, silent=True) for x in contained_dirs if version_str_to_int(x, silent=True) is not None ] # get all versions in dir
        if len( version_int_list ) > 0:
            latest_current_version = max( version_int_list )
        else:
            latest_current_version = 0
        version_str = 'v'+str( latest_current_version+1 ).zfill(3)

    elif version_str is None:
        raise Exception('ERROR: auto_version is false but no version_str provided.')

    dir_name = pjoin(dir_name, version_str) # the full path with the version
    if create_dirs: _ensure_dir_exists(dir_name)

    return dir_name, version_str

def getAssetPath(**tags): # This function should return a path and filename for an asset with the tags dict input provided.
    requirements = ['job', 'seq', 'shot', 'element', 'variant', 'asset_type', 'volatile' ]
    
    for key in requirements:
        if key not in tags:
            firehawk_logger.warning( 'Error: Missing key: {}'.format(key) )
        elif tags[key] is None:
            firehawk_logger.warning( 'Error: Key: {} Value is: {}'.format(key, value) )

    tags['dir_name'], tags['file_name'] = None, None
    if tags['volatile']=='on': tags['volatile']=True
    if tags['volatile']=='off': tags['volatile']=False

    firehawk_logger.debug( 'getAssetPath with tags: {}'.format(tags) )
    
    if 'version_str' in tags and tags['version_str'] is not None:
        firehawk_logger.debug( 'getAssetPath with specified version - createAssetsFromArguments' )
        tags['dir_name'], tags['version_str'] = _create_asset( tags, auto_version=False, version_str=tags['version_str'], create_dirs=False )
    else:
        firehawk_logger.debug( 'getAssetPath default first version - createAssetsFromArguments' )
        tags['dir_name'], tags['version_str'] = _create_asset( tags, auto_version=False, version_str='v001', create_dirs=False )
    
    tags['dir_name'], tags['file_name'] = returnFileName(**tags) # Join the resulting file name onto the asset dir path.
    
    firehawk_logger.debug( 'getAssetPath returned dir_name: {} file_name: {}'.format( tags['dir_name'], tags['file_name'] ) )
    return tags['dir_name'], tags['file_name']



def createAssetPath(**tags): # This method should create an asset if version_str (eg 'v005') is provided, or increment an asset if version_str is 'None'.  It can be patched with whatever method you wish, so long as it returns the same output.  It must return dir_name file_name and version (as an int)
    print( 'api: create_asset tags: {}'.format(tags) )
    requirements = ['job', 'seq', 'shot', 'element', 'variant', 'asset_type', 'volatile']
    for key in requirements:
        if key not in tags:
                firehawk_logger.warning( 'ERROR: Missing key {}'.format(key) )

    tags['dir_name'], tags['file_name'] = None, None
    if tags['volatile']=='on': tags['volatile']=True
    if tags['volatile']=='off': tags['volatile']=False

    firehawk_logger.debug( 'createAssetsFromArguments with tags: {}'.format(tags) )

    try:
        if 'version_str' in tags and tags['version_str'] is not None: # When version_str is provided, use that and don't auto increment.  Otherwise, request the server to auto inc the version.
            firehawk_logger.debug( 'Create new asset with specified version_str: {}'.format(tags['version_str']) )
            tags['dir_name'], tags['version_str'] = _create_asset( tags, auto_version=False, version_str=tags['version_str'] )
        else:
            firehawk_logger.debug( 'Create new asset with incremented version from latest' )
            tags['dir_name'], tags['version_str'] = _create_asset( tags, auto_version=True )

        if 'hip' in tags:
            hip_asset_path = os.path.dirname( tags['hip'] )
            # hook to register that a hip file created an asset.

    except ( Exception ), e :
        msg = 'ERROR: During createAssetPath. Tags used: {}'.format( tags )
        print( msg )
        firehawk_logger.warning( msg )
        traceback.print_exc(e)
        traceback.print_exc(tags)
        raise e
        # return None
    
    firehawk_logger.debug( 'Created dir_name: {} asset_version_str: {}'.format( tags['dir_name'], tags['version_str'] ) )
    
    tags['version_int'] = version_str_to_int(tags['version_str'])
    tags['dir_name'], tags['file_name'] = returnFileName(**tags) # this will also update the base dir for the asset.
    tags['extension'] = returnExtension(**tags)

    return tags['dir_name'], tags['file_name'], tags['version_int']

def version_str_to_int(version_str, silent=False):
    match = re.match(r"^(v)([0-9]+)$", version_str, re.I)  

    if match is None:
        if not silent: firehawk_logger.warning( 'createAssetPath returned an invalid version' )
        return

    version_int = int(match.groups()[1])
    return version_int

def version_int_to_str(version_int):
    version_str = 'v'+str( version_int ).zfill(3)
    return version_str