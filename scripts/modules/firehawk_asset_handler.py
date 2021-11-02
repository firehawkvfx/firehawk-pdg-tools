# This python file provides ability to patch different methods for asset creation when cooking.

# We should avoid any references to hou (even PDG potentially), to provide compatibility with out of process and in process work items.  We want to enable use in other platforms.

# Originally this was the purpose of firehawk_submit and the origins of the code base but depending on the environment may need to be customised.

# Because PDG doesn't know if it needs to request new asset paths until evaluation of a graph (using cache handlers per work item), asset creation is even less of a trivial excercise that can just occur before submission.
# This outlines the steps that occur in this flow and what we now have a need to consider in PDG land:

# Hip files should be saved once for submission, custom values for the submission must be updated on subsequent loads in a render queue.  
# On submit, we timestamp a saved file, stash it on user data at '/' and ensure the hip attrib on any work item will use this.  When a file loads, in 456.py we can tell if it was intended for farm use and it should check if any dynamic values will need to be updated.  This is also applied if a user manually loads that file, since its state would still not be current.  Wedge override attribs, while meant to help with this efficiency problem, are too ephemeral to be useful by themselves in this scenario.  We must track the data more persistently for production between hip loads.  Top graphs can't be trusted to preserve data from previous cooks easily on hip load, and we also want sop nets to be able to read files independent of tops - we use a combo of multiparms and JSON sidecar files.
# Before a cook, output parms on nodes (defining file paths) should be defined by expressions that can resolve to real paths if possible from prior cooks.  The expressions must be set before evaluation of any related work item, since if files exist at a resolved path, cooking should be skipped because the item is regarded as cached.  an exception in if a cook occurs upstream, then we should regard what is downstream as requiring updating and cook it.
# If a cook will occur, we may need to request an asset is created, either with a specific version the user has set, or a version provided back to us from an asset server / other method - that could be as simple as incrementing a number from an existing dir tree.  Consider as well the asset may already be created, but the dir is empty. Not fun!
# When any new asset / version is retrieved, the path has changed, so we track that update by writing a side car JSON file which will be used to override a value later when the hip file is loaded.
# Finally the work item is submitted to the queue!
# When the timestamped hip file is loaded on a render node, we use a 456.py file to check for any sidecar JSON files in the same path with the same basename.
# If any JSON files are found, we update our multiparms accordingly with version data as current as possible for the entire submission tree (we need versions upstream of the current node too).  This allows a loaded hip file to always at least have the current wedge version, and if dependencies are mananged appropriately, it is also possible for the loaded hip file to have access to all submitted wedge versions in instances where all that data must be merged.

import os
import time
import re
import traceback

import firehawk_plugin_loader
create_asset_module = firehawk_plugin_loader.module_package('create_asset').create_asset

debug_default = firehawk_plugin_loader.resolve_debug_default()

from os.path import sep, join
def pjoin(*args, **kwargs):
    return join(*args, **kwargs).replace(sep, '/') # for windows compatibility.

class asset():
    def __init__(   self, 
                    debug=debug_default,
                    logger_object=firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(), 
                    start_time=None
                ):
        self.debug = debug
        self.dynamic_input_keys = ['seq','shot','element','variant','version_str'] # see custom_create_new_asset_version for more info on how to use these for asset creation.

        self.start_time = start_time # Start time is used to continue tracking of a log time
        self.last_time = None

        self.logger_object = logger_object

        
    def timeLog(self, start_time=None, label=''): # provides time passed since start time and time since last running of this method.
        if start_time is not None:
            self.start_time = start_time
        else:
            start_time = self.start_time
        if self.last_time is None:
            self.last_time = start_time
        
        message = "--- {} seconds --- Passed during Pre Submit --- {} seconds --- {}".format( '%.4f' % (time.time() - start_time),  '%.4f' % (time.time() - self.last_time), label )
        self.infoLog( message )
        
        self.last_time = time.time()

    def debugLog(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'debug' ):
            self.logger_object.debug( message )
        else:
            if self.debug>=10: print( message )

    def infoLog(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'info' ):
            self.logger_object.info( message )
        else:
            if self.debug>=5: print( message )

    def warningLog(self, message):
        if self.logger_object is not None and hasattr( self.logger_object, 'warning' ):
            self.logger_object.warning( message )
        else:
            print( message )

    def getAssetPath(self, **tags): # This method should return a path and filename for an asset with the tags dict input provided.
        dir_name, file_name = create_asset_module.getAssetPath(**tags)
        return dir_name, file_name

    def custom_create_new_asset_version( self, tags, silent_errors=False, show_times=False, register_hip=True ):
        # This method should be able to:
        # - produce an expression for rop outputs (these use channel refs).  This is an output path expression that will be applied to a node.
        # - request creation of new asset versions when tags have explicit values.
        # When both are evaluated in a houdini session they should be able to resolve to the same path on disk for a work item.

        self.debugLog('custom_create_new_asset_version()')

        if tags['format'] == 'ip': # If format is set to ip (interactive), then we set it on the output of the rop to load images directly into mplay.  We shouldn't be creating any asset in this instance
            tags['asset_path'] = 'ip'
        
        tags = create_asset_module.rebuild_tags( tags ) # This custom method can be used to rebuild tags with reasonable defualt.

        if tags is None:
            self.warningLog( 'ERROR: No tags defined:'.format( tags ) )
            return None
        self.debugLog('tags: {}'.format( tags ))

        # getting all required parms

        self.debugLog( "create_asset disabled for this workitem in tags: {}".format( tags ) )

        create_asset = tags.get('create_asset', True)
        if not isinstance( create_asset, bool ):
            raise Exception('create_asset tag value is not type bool')
        if create_asset != True:
            self.debugLog( "create_asset disabled for this workitem in tags: {}".format( tags ) )

        scheduled = True # reutrn failed if this is occuring within a scheduler
        if 'scheduled' in tags: scheduled = tags['scheduled'] # scheduled assets only upversion once.

        version = None
        version_int = None
        version_str = None

        # dynamic_input_keys defined on init are the components of the expression that may change on cook of a work item and can be patched if required.  That would commonly be the sequence, shot, element name, the wedge number or some other variant in the path, and the version.
        # We usually need to convert these to an expression on the node that channel refs the parm (varying by the wedge). tags['use_inputs_as'] == 'channels'
        # We also may need to pass through a preevaluated value to construct a path as a string. tags['use_inputs_as'] == 'tags'
        # self.dynamic_input_keys can be customised by setting it on the object.

        def update_tags( tags, formatstr ):
            for key in self.dynamic_input_keys:
                tags[key] = formatstr.format(key)

        if 'use_inputs_as' not in tags: # be default, evaluate path output based on tag values.
            tags['use_inputs_as'] = 'tags'

        literal_path = False
        if tags['use_inputs_as'] == 'attributes': # PDG attributes will be used to define output paths, generally not a good idea, since these attributes are global.
            update_tags( tags, '`@{}`' )
        elif tags['use_inputs_as'] == 'channels': # Unexpanded strings can be evaluated later by the rop itself useing its own channels
            update_tags( tags, '`chs("{}")`' )
        elif tags['use_inputs_as'] == 'expressions': # Expressions can be evaluated later by the rop itself using its own channels
            update_tags( tags, ' + chs("{}") + ' )
        elif tags['use_inputs_as'] == 'tags':  # These are using tags as literal values to resolve an actual string / asset name.
            literal_path = True
            version_int = int( tags['version'] ) # version as an int should be provided and resolves to a triple padded string - version_str will be output
            if version_int == -1: # when version is set to -1, it will increment.  Otherwise, the input will be used.
                tags['version_str'] = None # when version is None, asset will be created with new version.
            else:
                tags['version_str'] = 'v'+str( version_int ).zfill(3)

        asset_path = ''
        try :
            self.debugLog( "Check if version_str is defined: {}".format( tags.get('version_str', None) ) )
            if show_times: self.timeLog(label='Dynamic versioning: Prep tags to query asset path')

            asset_dir, asset_filename = None, None
            if create_asset:
                self.debugLog( "Ensure Asset exists" )
                asset_already_exists = False # Assume we need a new asset.

                if 'version_str' in tags and tags['version_str'] is not None: # (auto version was disabled since a version was provided) we must be creating an asset with a specific version, but check it isn't already present on disk.
                    self.debugLog('...Using asset with specific version.  Check if it exists' )
                    asset_dir, asset_filename = create_asset_module.getAssetPath( **tags ) # retrieve the theoretical asset path, it may or may not exist, but this is used to test its existence.
                    asset_already_exists = os.path.isdir(asset_dir) # Check existance
                
                self.debugLog( "Ensure Asset exists.  asset_already_exists: {}".format(asset_already_exists) )
                if not asset_already_exists: # create the asset if it doesn't exist, else use the existing path.
                    self.debugLog('...Create New Version:' )
                    asset_dir, asset_filename, version_int = create_asset_module.createAssetPath( **tags )
                    if show_times: self.timeLog(label='Dynamic versioning: Created new asset path')
                else:
                    if show_times: self.timeLog(label='Dynamic versioning: Skipping asset creation.  Already Exists')
            else: # We must not be wanting to create a new version, just want an existing path.
                self.debugLog( "Using an existing path.  No new assets need to be created. value for create_asset: {}".format( create_asset ) )
                asset_dir, asset_filename = create_asset_module.getAssetPath( **tags )
                self.debugLog( "asset_dir: {}".format( asset_dir ) )
            
            if None not in [ asset_dir, asset_filename ]:
                asset_path = pjoin( asset_dir, asset_filename )
            else:
                self.debugLog('...Asset create did not return either of file name or dir' )

        except ( Exception ), e :
            if silent_errors == False:
                import traceback
                self.warningLog( 'ERROR: During aquiring path / creation of asset. Tags used:'.format( tags ) )
                traceback.print_exc(e)
                traceback.print_exc(tags)
                raise e
            return None

        if literal_path:
            create_dir = os.path.dirname(asset_path) # the asset path exists, we just create a sub dir in there.
            if not os.path.isdir(create_dir): os.makedirs(create_dir)

        return asset_path, version_int