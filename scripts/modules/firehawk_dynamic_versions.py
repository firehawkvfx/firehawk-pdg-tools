# This library is responsible for dynamically updating output versions and multiparms during submission and execution time.

import os, sys
import re
import json
import time
import collections
import traceback

from functools import partial

import pdg
import hou

if hou.isUIAvailable():
    # callbacks
    import hdefereval

import firehawk_read
reload(firehawk_read)

debug_default = int( os.getenv('DEBUG_PDG', 10) )
delimeter = '.' # the delimeter used to seperate keys for versioning

class versions():
    def __init__( self, node=None, debug=debug_default, logger_object=None, start_time=None ):
        self.node = node
        self.selected_nodes = []
        self.debug = debug

        if start_time is None:
            self.start_time = time.time()
        else:
            self.start_time = start_time # Start time is used to continue tracking of a log time

        self.last_time = None

        self.logger_object = logger_object

        self.parm_template_version = '0.2.0'
        self.output_types = { # Defines valid node types that will inherit the version_db multiparm tab.
            'alembic': {
                'output': 'sop_path', 'extension': 'abc', 'type_path': 'cache', 'static_expression': True
            },
            'opengl': {
                'output': 'picture', 'extension': 'jpg', 'type_path': 'flipbook/frames', 'static_expression': False
            },
            'rop_geometry': {
                'output': 'sopoutput', 'extension': 'bgeo.sc', 'type_path': 'cache', 'static_expression': True
            },
            'vellumio': {
                'output': 'file', 'extension': 'bgeo.sc', 'type_path': 'cache', 'static_expression': False
            },
            'rop_alembic': {
                'output': 'filename', 'extension': 'abc', 'type_path': 'cache', 'static_expression': True
            },
            'file': {
                'output': 'file', 'extension': 'bgeo.sc', 'type_path': 'cache', 'static_expression': True
            },
            'ropcomposite': {
                'output': 'copoutput', 'extension': 'exr', 'type_path': 'flipbook/frames', 'static_expression': True
            },
            'ropmantra': {
                'output': 'vm_picture',
                'extension': 'exr',
                'type_path': 'render/frames',
                'static_expression': True,
                'overrides': {
                    'frame': "import hou"+'\n'+"value = '$F4'"+'\n'+"return value"
                }
            },
            'ifd': {
                'output': 'vm_picture',
                'extension': 'exr',
                'type_path': 'render/frames',
                'static_expression': True,
                'overrides': {
                    'frame': "import hou"+'\n'+"value = '$F4'"+'\n'+"return value"
                }
            },
            'arnold': {
                'output': 'ar_picture',
                'extension': 'exr',
                'type_path': 'render/frames',
                'static_expression': True,
                'overrides': {
                    'frame': "import hou"+'\n'+"value = '$F4'"+'\n'+"return value"
                }
            },
            'renderarnold': {
                'output': 'output_path',
                'extension': 'exr',
                'type_path': 'render/frames',
                'static_expression': True,
            },
            'pythonscript': {
                'output': 'output_path',
                'extension': 'exr',
                'type_path': 'render/frames',
                'static_expression': True,
            },
            'houdiniserver': {
                'output': 'output_path',
                'extension': 'hip',
                'type_path': 'render/frames',
                'static_expression': True,
            },
            'ffmpegencodevideo': {
                'output': 'outputfilepath',
                'extension': 'mp4',
                'type_path': 'flipbook/videos',
                'static_expression': False,
                # 'file_template': "`chs('shot_path')`/`chs('output_type')`/`chs('element_name')`/`chs('version_str')`/`chs('shot')`.`chs('element_name')`.`chs('version_str')`.`chs('wedge_string')`.`chs('file_type')`",
                # 'overrides': {
                #     'expr': '"{ffmpeg}" -y -r {frames_per_sec}/1 -f concat -safe 0 -apply_trc iec61966_2_1 -i "{frame_list_file}" -c:v libx264 -b:v 10M -vf "fps={frames_per_sec},format=yuv420p" -movflags faststart "{output_file}"'
                # }
            },
            'auto_shots': {
                'output': 'sopoutput', 'extension': 'hip', 'type_path': 'scene', 'static_expression': True
            }
        }
        
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

    def pull_versions_to_multiparm(self, hou_node_path, exec_in_main_thread=False, return_index_keys=False, read_json_file=False): # Update the multiparm on the hou_node_path rop output from the user data dict. if return_index_keys is true, no parm updates will occur, but the list of available index keys will be returned.
        self.debugLog( 'pull versions to multiparm' )
        version_db_hou_node_path = firehawk_read.get_version_db_hou_node_path( hou_node_path=hou_node_path )
        self.debugLog( 'version_db_hou_node_path: {}'.format(version_db_hou_node_path) )

        version_prefix = firehawk_read.get_version_prefix() # version_prefix='version_'

        if read_json_file: # by default, we update the multiparm from user data and we do not read in the json file here.  That operation is normally performed post cook / on hip load.
            json_object = self.get_sidecar_json_object()
            if version_db_hou_node_path in json_object:
                self.debugLog( 'pull: get keys from file and update user data: {}'.format(json_object) )
                for key in json_object[version_db_hou_node_path]:
                    if key.startswith( version_prefix ):
                        value = json_object[version_db_hou_node_path][key]
                        if not value.isdigit():
                            self.warningLog( 'ERROR: couldn\'t retrieve a version from key: {}'.format(key) )
                            return
                        
                        self.debugLog( 'pull: get keys from file and update user data key: {} value: {}'.format(key, value) )
                        hou.node(version_db_hou_node_path).setUserData( key, value )
            else:
                self.debugLog( 'version_db_hou_node_path: {} not found in json_object: {}'.format( version_db_hou_node_path, json_object ) )

        version_user_data_dict = hou.node(version_db_hou_node_path).userDataDict()
        
        self.debugLog( 'pull: get keys' )
        version_db_index_keys = [ x[len(version_prefix): ] for x in version_user_data_dict if x.startswith(version_prefix) ]
        
        if return_index_keys: # optionally retrieve the valid list of index keys.
            return version_db_index_keys
        else:
            for index_key in version_db_index_keys: # use the keys to update the multiparm iteratively
                version=int( version_user_data_dict[version_prefix+index_key] )
                self.update_multiparm(hou_node_path, index_key, version=version, exec_in_main_thread=exec_in_main_thread, debug=10)


    def push_multiparm_versions_to_version_db(self, hou_node_path, replace_existing_versions=False): # Update the versiondb relative to the the hou_node_path of the rop output from the user data dict.
        hou_node = hou.node( hou_node_path )
        
        version_db_hou_node_path = firehawk_read.get_version_db_hou_node_path( hou_node_path=hou_node_path )
        version_db_hou_node = hou.node(version_db_hou_node_path)

        index_user_data_dict = hou_node.userDataDict() # the values on the multiparm node dict point to the parm index to get the data from, it is not the version, but the index as an int.
        prefix='verdb_'
        index_keys = [ x[len(prefix): ] for x in index_user_data_dict if x.startswith(prefix) ]
        version_prefix = 'version_'
        if replace_existing_versions:
            self.debugLog('replace_existing_versions:')
            
            version_user_data_dict = hou.node(version_db_hou_node_path).userDataDict()
            existing_data = [ x[len(version_prefix): ] for x in version_user_data_dict if x.startswith(version_prefix) ]
            
            # destroy existing user data matching the prefix
            for index_key in existing_data:
                key = version_prefix + index_key
                self.debugLog( 'destroy: {}'.format( key ) )
                version_db_hou_node.destroyUserData( key )

        update_count = 0
        for index_key in index_keys:
            multiparm_index = index_user_data_dict[ prefix + index_key ]

            multiparm_name = 'version_{}'.format( str(multiparm_index) )
            parm = hou_node.parm( multiparm_name )
            version = str( parm.evalAsInt() )

            version_db_hou_node.setUserData( 'version_' + index_key, version ) # Update the version on the db node.
            update_count += 1

        self.debugLog('Updated entries on versiondb node: {}'.format( update_count ))
        if update_count == 0:
            self.debugLog('user data:')
            self.debugLog( json.dumps( hou.node(version_db_hou_node_path).userDataDict(), indent=4, sort_keys=True) )


    def uses_version_db(self, node): # determine if this node type is acceptable for the version_db parameter tab to be applied
        if not node:
            self.warningLog( "No node found" )
            return False

        node_type_name = node.type().nameComponents()[-2]
        # If target matches node typ in dict, then apply versioning
        self.debugLog( 'uses_version_db() check node_type_name: {}'.format( node_type_name ) )

        if node_type_name not in self.output_types:
            self.debugLog( 'node_type_name: {} not in output_types: {}'.format( node_type_name, self.output_types  ) )
            return False

        return True

    def update_rop_output_paths_for_selected_nodes(self, kwargs={}, version_db=False):
        self.debugLog( "Update Rop Output Paths for Selected SOP/TOP Nodes." )
        self.selected_nodes = kwargs['items']

        for node in self.selected_nodes:
            node_type_name = node.type().nameComponents()[-2]
            self.debugLog( 'Name: {}'.format( node.name() ) )
            if node_type_name == 'ropfetch':
                node = node.node(node.parm('roppath').eval())
                node_type_name = node.type().nameComponents()[-2]

            if not node:
                self.warningLog( "No node found" )
                return

            if not self.uses_version_db(node):
                return

            self.debugLog( 'Set path: {}'.format( node.path() )  )
            hou.cd(node.path())

            bake_names = True
            self.debugLog( "evaluate env vars" )
            if bake_names:
                node_name = node.name()

            else:
                node_name = "${OS}"

                show_var = "${SHOW}"
                seq_var = "${SEQ}"
                shot_var = "${SHOT}"

                shot_var = "${SHOW}.${SEQ}.${SHOT}"
                shotpath_var = "${SHOTPATH}"
                scene_name = "${SCENENAME}"

            file_template_default = ""


            # if node_type_name not in self.output_types:
            #     self.debugLog( 'node_type_name: {} not in output_types: {}'.format( node_type_name, self.output_types  ) )
            #     return

            # Determine if the parm template doesn't exist or is using an old version
            parm_group = node.parmTemplateGroup()
            found_versioning_folder = parm_group.findFolder( "Versioning" ) # find folder by label
            utilised_version = None
            if found_versioning_folder:
                utilised_version = found_versioning_folder.tags()['version_db']
            if utilised_version and ( utilised_version == self.parm_template_version ):
                self.debugLog( "Version DB Template already matches current v{}. Not updating parameters".format( utilised_version ) )
                return

            lookup = self.output_types[node_type_name]
            extension = lookup['extension']
            self.debugLog( 'extension: {}'.format( extension ) )
            static_expression = lookup['static_expression']
            out_parm_name = lookup['output']
            # check if overide for default
            file_template = file_template_default

            try:
                parm_folder = hou.FolderParmTemplate("versioning", "Versioning")
                parm_folder = self.append_version_db_tags(parm_folder)

                if not version_db:
                    parm_template = hou.IntParmTemplate("version", "Version", 1)
                    parm_template.setJoinWithNext(True)
                    parm_folder.addParmTemplate(parm_template)

                    parm_template = hou.StringParmTemplate("version_str", "Version String", 1, [""])
                    parm_template.setJoinWithNext(True)
                    parm_folder.addParmTemplate(parm_template)

                    
                self.debugLog( 'Append or replace folder. version_db: {} node: {} folder: {}'.format( version_db, node, parm_folder ) )
                parm_group = self.appendOrReplaceFolder(node, parm_folder)
                self.debugLog( 'Appended folder' )
                passed = node.setParmTemplateGroup(parm_group)
                self.debugLog( 'Set PTG' )

                if version_db:
                    # self.add_multi_parm_dict(node=node, db_name='path_db', key_prefix='pathdb', key_name='folder', value_name='value', value_type='string')
                    extra_parm_dict = collections.OrderedDict()
                    extra_parm_dict['version'] = {'type':'int','join':False,'disable':False,'db':True,'auto_inherit':True}
                    # extra_parm_dict['job'] = {'type':'string','hide':True}
                    extra_parm_dict['seq'] = {'type':'string','db':False,'auto_inherit':True}
                    extra_parm_dict['shot'] = {'type':'string','db':False,'auto_inherit':True}
                    extra_parm_dict['element'] = {'type':'string','db':False,'auto_inherit':True}
                    extra_parm_dict['variant'] = {'type':'string','join':False,'db':False,'auto_inherit':True}
                    extra_parm_dict['pull_versions'] = {'type':'button','join':True,'db':False,'auto_inherit':False,'lookup_db_values':False,'script':'import firehawk_dynamic_versions; firehawk_dynamic_versions.versions().pull_versions_to_multiparm(hou.pwd().path())'}
                    extra_parm_dict['push_versions'] = {'type':'button','join':True,'db':False,'auto_inherit':False,'lookup_db_values':False,'script':'import firehawk_dynamic_versions; firehawk_dynamic_versions.versions().push_multiparm_versions_to_version_db(hou.pwd().path(), replace_existing_versions=False)'}
                    extra_parm_dict['erase_and_push_versions'] = {'type':'button','join':False,'db':False,'auto_inherit':False,'lookup_db_values':False,'script':'import firehawk_dynamic_versions; firehawk_dynamic_versions.versions().push_multiparm_versions_to_version_db(hou.pwd().path(), replace_existing_versions=True)'}
                    self.add_multi_parm_dict(node=node, extra_parm_dict=extra_parm_dict, db_name='version_db', key_prefix='verdb', key_name='index_key_', disable_key_parm=False, value_name='version_', extra_parms=True)
                    self.ensure_version_db_node_exists( node.path() )
                    self.debugLog( 'Done' )
                else:
                    parm_group.append(parm_folder)
                    node.setParmTemplateGroup(parm_group)

                    hou_parm = node.parm("version")
                    self.debugLog( "int hou_parm: {}".format( hou_parm ) )
                    hou_parm.lock(False)
                    hou_parm.setAutoscope(False)

                hou_parm = node.parm("version_str")
                hou_parm.lock(False)
                hou_parm.setAutoscope(False)
                hou_keyframe = hou.StringKeyframe()
                hou_keyframe.setTime(0)
                py_expr = \
                        """
# This returns the version as a padded string.
import hou
version = 'v'+str(hou.pwd().parm('version').eval()).zfill(3)
return version
"""
                hou_keyframe.setExpression(
                    py_expr, hou.exprLanguage.Python)
                hou_parm.setKeyframe(hou_keyframe)

                expr = \
                    """
# When multiple sites (cloud) are mounted over vpn, this allows tops to recognise if data exists in a particulr location.
# It means data can be submitted for generation or deleted from multiple locaitons,
# However generation should normally be executed by render nodes that exist at the same site through via a scheduler.
import hou
node = hou.pwd()
lookup = {'submission_location':'$PROD_ROOT', 'cloud':'$PROD_CLOUD_ROOT', 'onsite':'$PROD_ONSITE_ROOT'}
location = node.parm('location').evalAsString()
root = lookup[location]

template = root+'/$SHOW/$SEQ/$SHOT'
return template
"""

                # hou_parm = node.parm("shot_path_template")
                # hou_parm.lock(False)
                # hou_parm.setAutoscope(False)
                # hou_keyframe = hou.StringKeyframe()
                # hou_keyframe.setTime(0)
                # hou_keyframe.setExpression(
                #     expr, hou.exprLanguage.Python)
                # hou_parm.setKeyframe(hou_keyframe)

                parms_added = True
            # except:
            #     parms_added = False
            #     traceback.print_exc()
            #     sys.stderr.flush()
            except ( Exception, hou.Error ), e :
                import traceback
                parms_added = False
                print( 'Exception: {}'.format(e) )
                traceback.print_exc(e)
                raise e
            # if parms_added:
                # if static_expression:
                #     hou_parm = node.parm("frame")
                #     hou_parm.lock(False)
                #     hou_parm.setAutoscope(False)
                #     hou_keyframe = hou.StringKeyframe()
                #     hou_keyframe.setTime(0)

                #     if 'overrides' in lookup and 'frame' in lookup['overrides']:
                #         self.debugLog( 'has override for static_expression' )
                #         hou_keyframe.setExpression(
                #             lookup['overrides']['frame'], hou.exprLanguage.Python)
                #     else:
                #         hou_keyframe.setExpression("import hou"+'\n'+"node = hou.pwd()"+'\n'+"step = node.parm('f3').eval()"+'\n'+"if node.parm('trange').evalAsString() == 'off':" +
                #                                 '\n'+"    value = 'static'"+'\n'+"elif step != 1:"+'\n'+"    value = '$FF'"+'\n'+"else:"+'\n'+"    value = '$F4'"+'\n'+"return value", hou.exprLanguage.Python)
                #     # if node.parm('framegeneration').evalAsString() == '0':
                #     hou_parm.setKeyframe(hou_keyframe)

                # element_name_template = node.parm(
                #     "element_name_template").evalAsString()

                # node.parm('element_name').set(element_name_template)

                # bake_template = False
                # replace_env_vars_for_tops = True

    def ensure_version_db_node_exists(self, hou_node_path): # ensures the version db node exists for the  hou  node path.  It may be the same node itself, but can be a null.
        hou_node = hou.node( hou_node_path )
        version_db_hou_node_path = firehawk_read.get_version_db_hou_node_path( hou_node_path=hou_node_path )
        version_db_hou_node = hou.node( version_db_hou_node_path )
        if version_db_hou_node is None: # Create the version db node next to the node with the multiparm on it, and give it the expected name provided by get_version_db_hou_node_path
            version_db_hou_node = hou_node.parent().createNode( 'null', version_db_hou_node_path.split('/')[-1] )
            pos = hou_node.position() + hou.Vector2( (4.0, 0.0) )
            version_db_hou_node.setPosition( pos )
            version_db_hou_node.setColor( hou.Color(1.0, 0.725, 0) )

    def underscores_to_title(self, string=None): 
        acronyms = ['DB']
        result = []
        for word in string.split('_'):
            if len(word) > 0:
                word = word.capitalize()
            if word.upper() in acronyms:
                word = word.upper()
            result.append(word)
        output = ' '.join(result)
        return output

    def add_multi_parm_dict(self, node=None, extra_parm_dict={}, parent_folder_label='Versioning', db_name='version_db', key_prefix='verdb', key_name='index_key', disable_key_parm=False, value_name='version', value_type='int', extra_parms=False):
        # extra_parm_dict is optional - will create a lookup on the attrib value based on parm
        try:
            label = self.underscores_to_title(db_name)
            instance_name = db_name+"0"
            # if parent_folder_label is None:
            #     # if no par folderm is passed, then create one.
            #     parent_folder_label = hou.FolderParmTemplate(label, label)
            self.debugLog( 'find folder: {}'.format( parent_folder_label ) )
            # get the group
            parm_group = node.parmTemplateGroup()
            parm_folder = parm_group.findFolder(parent_folder_label)
            
            self.debugLog( 'Add multiparm dict to node: {} {}'.format( node, db_name  ) )
            sepparm_name = "{}_sepparm".format(db_name)
            parm_template = hou.SeparatorParmTemplate( sepparm_name )
            parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, parm_template )
            node.setParmTemplateGroup(parm_group)
            self.debugLog( 'Added sep parm' )

            # Code for string keys template defaults
            index_template_parm_name = '{}_index_key'.format(db_name)
            parm_template = hou.StringParmTemplate(index_template_parm_name, self.underscores_to_title(index_template_parm_name), 1, default_value=(["`@{}`".format(key_name.strip('_'))]), naming_scheme=hou.parmNamingScheme.Base1, string_type=hou.stringParmType.Regular, menu_items=([]), menu_labels=([]), icon_names=([]), item_generator_script="", item_generator_script_language=hou.scriptLanguage.Python, menu_type=hou.menuType.Normal)
            # parm_group.appendToFolder(parm_group.findIndicesForFolder(parent_folder_label), parm_template)
            if extra_parms:
                parm_template.setJoinWithNext(True)

            parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, parm_template )
            node.setParmTemplateGroup(parm_group)

            if extra_parms:
                parm_template = hou.StringParmTemplate("version_str", "Version String", 1, [""])
                parm_template.setJoinWithNext(True)

                parm_folder.addParmTemplate(parm_template)
                parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, parm_template )
                node.setParmTemplateGroup(parm_group)

                for parm_name,properties in extra_parm_dict.items():
                    self.debugLog( 'adding:'.format( parm_name ) )
                    if properties['type']=='int':
                        parm_template = hou.IntParmTemplate(parm_name, self.underscores_to_title(parm_name), 1)
                    elif properties['type']=='string':
                        parm_template = hou.StringParmTemplate(parm_name, self.underscores_to_title(parm_name), 1, [""])
                    elif properties['type']=='toggle':
                        parm_template = hou.ToggleParmTemplate(parm_name, self.underscores_to_title(parm_name), default_value=False)
                    elif properties['type']=='button':
                        parm_template = hou.ButtonParmTemplate(parm_name, self.underscores_to_title(parm_name), script_callback=properties['script'], script_callback_language=hou.scriptLanguage.Python )
                        
                        # parm_template.hide(True)
                    else:
                        self.warningLog( "ERROR, invalid/missing type for extra parm dict" )
                        return
                    if 'hide' in properties:
                        parm_template.hide( properties['hide'] )
                    if 'join' in properties:
                        parm_template.setJoinWithNext(properties['join'])
                    else:
                        # join by default.
                        parm_template.setJoinWithNext(True)
                    
                    if 'auto_inherit' in properties and properties['auto_inherit']==True:
                        parm_template.setTags({"auto_inherit": "@"+parm_name})
                    
                    parm_folder.addParmTemplate(parm_template)
                    parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, parm_template )
                    node.setParmTemplateGroup(parm_group)
            sepparm_name = "{}_sepparm2".format(db_name)
            parm_template = hou.SeparatorParmTemplate( sepparm_name )
            parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, parm_template )
            node.setParmTemplateGroup(parm_group)
                
            
            # if a folder parm already exists, use it, else define it.
            self.debugLog( "findInFolderOrTemplateGroup: {}".format( instance_name ) )
            folder_parm_template = self.findInFolderOrTemplateGroup( parm_folder, label=instance_name )
            self.debugLog( 'found folder parm template: {}'.format( folder_parm_template ) )
            if folder_parm_template is None:
                folder_parm_template = hou.FolderParmTemplate(instance_name, label, folder_type=hou.folderType.MultiparmBlock, default_value=0, ends_tab_group=False)
            self.debugLog( 'result:'.format( folder_parm_template ) )
            # callback for when counter changes to do housecleaning
            self.debugLog( 'add callback: {} {} {}'.format( db_name, key_prefix, key_name ) )
            callback_expr = \
                """
# This allows versioning to be inherited by the multi parm db
import hou, sys, os
import firehawk_dynamic_versions
node = hou.pwd()
parm = node.parm('{}0')
multiparm_count = parm.eval()
firehawk_dynamic_versions.versions(node).multiparm_housecleaning( node, multiparm_count, '{}', '{}' )
""".format( db_name, key_prefix, key_name )
            folder_parm_template.setScriptCallbackLanguage(hou.scriptLanguage.Python)
            folder_parm_template.setScriptCallback(callback_expr)
            self.debugLog( 'Added housecleaning callback for count change.' )
            
            parm_group = self.appendToFolderOrReplace(parm_group, parent_folder_label, folder_parm_template )
            self.debugLog( 'Setting {} on {}'.format( parm_group, node.path() ) )
            passed = node.setParmTemplateGroup(parm_group)

            # Code for parameter template - index key parm per wedge
            parm_template = hou.StringParmTemplate("{}#".format(key_name), self.underscores_to_title(key_name), 1, default_value=([""]), naming_scheme=hou.parmNamingScheme.Base1, string_type=hou.stringParmType.Regular, menu_items=([]), menu_labels=([]), icon_names=([]), item_generator_script="", item_generator_script_language=hou.scriptLanguage.Python, menu_type=hou.menuType.Normal)                            
            if disable_key_parm:
                parm_template.setConditional(hou.parmCondType.DisableWhen, "{ 0 != 1 }")
            parm_template.setJoinWithNext(True)
            parm_template.setScriptCallbackLanguage(hou.scriptLanguage.Python)
            callback_expr = \
                """
print 'callback'
import re, hou
import firehawk_dynamic_versions
index_int = next(re.finditer(r'\d+$', kwargs['parm_name'])).group(0)
node=kwargs['node']
parm = node.parm('{}0')
key_prefix='{}'
key_name='{}'
firehawk_dynamic_versions.versions(node).update_index(node, key_prefix=key_prefix, key_name=key_name, index_int=index_int)
multiparm_count = parm.eval()
firehawk_dynamic_versions.versions(node).multiparm_housecleaning(node, multiparm_count, key_prefix, key_name )
""".format(db_name, key_prefix, key_name)
            parm_template.setScriptCallback(callback_expr)
            self.debugLog( 'get folder' )
            versioning_folder_parm_template = self.findInFolderOrTemplateGroup( parm_group, label=parent_folder_label )
            self.debugLog( 'versioning_folder_parm_template: {}'.format( versioning_folder_parm_template ) )
            self.debugLog( '...updating parent with text fields for keynames' )
            
            parm_group = node.parmTemplateGroup()
            versioning_folder_parm_template = self.appendToFolderOrReplace( versioning_folder_parm_template, label, parm_template )
            parm_group.replace( parm_group.findIndicesForFolder(parent_folder_label) , versioning_folder_parm_template )
            passed = node.setParmTemplateGroup( parm_group )
            
            # Add the extra parms nested in the multiparm folder
            if extra_parms:
                parm_group = node.parmTemplateGroup()
                for parm_name,properties in extra_parm_dict.items():
                    if properties['db']==True:
                        if properties['type']=='int':
                            parm_template = hou.IntParmTemplate(parm_name+"_#", self.underscores_to_title(parm_name), 1)
                        elif properties['type']=='string':
                            parm_template = hou.StringParmTemplate(parm_name+"_#", self.underscores_to_title(parm_name), 1, [""])
                        elif properties['type']=='toggle':
                            parm_template = hou.ToggleParmTemplate(parm_name+"_#", self.underscores_to_title(parm_name), default_value=False)
                            # parm_template.hide(True)
                        else:
                            self.warningLog( "ERROR, invalid/missing type for extra parm dict" )
                            return

                        if 'hide' in properties:
                            parm_template.hide( properties['hide'] )

                        parm_template.setConditional(hou.parmCondType.DisableWhen, "") # parms are enabled by default, not intended for editing.
                        if 'disable' in properties:
                            if properties['disable']:
                                parm_template.setConditional(hou.parmCondType.DisableWhen, "{ 0 != 1 }")
                            else:
                                parm_template.setConditional(hou.parmCondType.DisableWhen, "")
                        
                        if 'help' in properties:
                            parm_template.setHelp(properties['help'])

                        # parm_template.setTags({"auto_inherit": "@"+parm_name})

                        if 'join' in properties:
                            parm_template.setJoinWithNext(properties['join'])
                        else:
                            # join by default.
                            parm_template.setJoinWithNext(True)
                        # append to the folder
                        versioning_folder_parm_template = self.appendToFolderOrReplace( versioning_folder_parm_template, label, parm_template )
                parm_group.replace( parm_group.findIndicesForFolder(parent_folder_label) , versioning_folder_parm_template )
                passed = node.setParmTemplateGroup( parm_group )

            # Lastly perform housecleaning since data may have changed
            multiparm_count = node.parm(instance_name).eval()
            self.multiparm_housecleaning( node, multiparm_count, key_prefix, key_name )
            
            # Add the value parms into the multi parm

            self.debugLog( '...Set passed: {}'.format( passed ) )
            
            if len(extra_parm_dict) > 0:
                for hou_parm_name,properties in extra_parm_dict.items():
                    if 'lookup_db_values' in properties and properties['lookup_db_values']==False:
                        continue
                    # If a parm name is passed, that parm will update automatically based on the index_template_parm_name value
                    hou_parm = node.parm(hou_parm_name)
                    hou_parm.lock(False)
                    hou_parm.setAutoscope(False)

                    # set expression for version to look up db if enabled
                    if hou_parm.parmTemplate().type() == hou.parmTemplateType.String:
                        hou_keyframe = hou.StringKeyframe()
                    elif hou_parm.parmTemplate().type() == hou.parmTemplateType.Int:
                        hou_keyframe = hou.Keyframe()
                    elif hou_parm.parmTemplate().type() == hou.parmTemplateType.Toggle:
                        hou_keyframe = hou.Keyframe()
                    else:
                        self.warningLog( "ERROR no matching type for parm: {}".format( hou_parm ) )
                    hou_keyframe.setTime(0)
                    py_expr = \
                        """
# This allows values from the dict to be inherited by the multi parm db
import hou
import re

node = hou.pwd()
parm = hou.evaluatingParm()
name = parm.name()

select = None
if name == 'seq':
    select = 0
elif name == 'shot':
    select = 1
elif name == 'element':
    select = 2
elif name == 'variant':
    select = 3

index_key = node.parm('{}').eval()
multiparm_index = node.userData('{}_'+index_key)

if parm.parmTemplate().type() == hou.parmTemplateType.String:
    value = ''
else:
    value = -1

if multiparm_index is not None:
    multiparm_index = str(multiparm_index)
    if select is not None: # select will take a part of the index key for the parm.
        value_parm = node.parm('index_key_'+multiparm_index)
        if value_parm is not None:
            value = value_parm.eval().split('{}')[select]
    else:
        value_parm = node.parm( name+'_'+multiparm_index )
        if value_parm is not None:
            value = value_parm.eval()

return value
""".format( index_template_parm_name, key_prefix, delimeter )
                    hou_keyframe.setExpression( py_expr, hou.exprLanguage.Python )
                    self.debugLog( 'set keyframe on: {}'.format( hou_parm.name() )  )
                    hou_parm.setKeyframe(hou_keyframe)
        except ( Exception, hou.Error ), e :
            import traceback
            self.warningLog( 'exception' )
            traceback.print_exc(e)
            raise e

    def appendOrReplace( self, node, parm_template ):
        parm_group = node.parmTemplateGroup()
        pt_name = parm_template.name()
        if parm_group.find( pt_name ):
            parm_group.replace( pt_name, parm_template )
        else:
            parm_group.append( parm_template )
        return parm_group

    def appendOrReplaceFolder( self, node, parm_template ):
        parm_group = node.parmTemplateGroup()
        pt_label = parm_template.label()
        found_folder = parm_group.findFolder( pt_label )
        if found_folder:
            pt_name = found_folder.name()
            parm_group.replace( pt_name, parm_template )
        else:
            parm_group.append( parm_template )
        return parm_group

    def appendToFolderOrReplace( self, parm_template_group_or_folder, folder_label, parm_template ):
        # NOTE if operating on a folder instead of a parm template group, you will still have to update the template group
        # parm_template_group_or_folder can be from node.parmTemplateGroup or a folder parm template, should be whatever the parent of the folder containing parm template is.
        # parm_template_group_or_folder = node.parmTemplateGroup()
        self.debugLog( '...Find folder to append or replace in: {} in ptg: {}'.format( folder_label, parm_template_group_or_folder ) )
        found_folder = self.findInFolderOrTemplateGroup( parm_template_group_or_folder, label=folder_label )
        self.debugLog( 'found: {}'.format( found_folder ) )

        if hasattr(parm_template, 'label') and parm_template.label():
            self.debugLog( "{} has label {}".format( parm_template, parm_template.label() ) )
            search_result_in_folder = self.findInFolderOrTemplateGroup( found_folder, label=parm_template.label() )
            replace_by = 'label'
        elif hasattr(parm_template, 'name') and parm_template.name():
            self.debugLog( "{} Has name: {}".format( parm_template, parm_template.name() ) )
            search_result_in_folder = self.findInFolderOrTemplateGroup( found_folder, name=parm_template.name() )
            replace_by = 'name'
        else:
            self.debugLog( "Error: couldn't find label or name matching parm template label or name" )
        self.debugLog( 'Search result: {}'.format( search_result_in_folder ) )
        
        if search_result_in_folder:
            self.debugLog( "Replace in folder" )
            folder_parm_templates = self.replaceInParmTemplates( found_folder.parmTemplates(), parm_template=parm_template, replace_by=replace_by )
            self.debugLog( 'replaced' )
        else:
            self.debugLog(  'No match in folder, appending to folder' )
            # parm_template_group_or_folder.appendToFolder( parm_template_group_or_folder.findIndicesForFolder(folder_label), parm_template )
            folder_parm_templates = self.appendToParmTemplates( found_folder.parmTemplates(), parm_template=parm_template )
            self.debugLog( 'appended' )
        self.debugLog( 'update template for found_folder: {}'.format( found_folder ) )
        found_folder.setParmTemplates( folder_parm_templates )
        self.debugLog( 'replace' )
        if hasattr(parm_template_group_or_folder, 'type') and parm_template_group_or_folder.type() == hou.parmTemplateType.Folder:
            # if its a folder, then set the templates from the tuple
            self.debugLog( 'is a folder' )
            parent_parm_templates = self.replaceInParmTemplates( parm_template_group_or_folder.parmTemplates(), parm_template=found_folder, replace_by=replace_by )
            parm_template_group_or_folder.setParmTemplates( parent_parm_templates )
        else:
            #must be a parm template group then.
            self.debugLog( 'is ptg, replace using alternate method {}'.format( found_folder ) )
            self.debugLog( 'update ptg with updated found folder' )
            parm_template_group_or_folder.replace( found_folder.name() , found_folder )
            # indices = parm_template_group_or_folder.findIndicesForFolder( folder_label )
            # print 'indices', indices
            # parm_template_group_or_folder.replace( indices , parm_template )
            # parm_group.replace( parm_group.findIndicesForFolder(parent_folder_label) , versioning_folder_parm_template )
        self.debugLog( 'done append or replace in folder' )
        # if its a ptg, replace.  if its a folder, set parm templates.
        return parm_template_group_or_folder

    def findInFolderOrTemplateGroup( self, parm_folder_or_template_group, label=None, name=None ):
        # Folder can also be a parm template group (whole node) since both folders and parm template groups can have .parmTemplates()
        if hasattr(parm_folder_or_template_group, 'parmTemplates'):
            parm_templates = parm_folder_or_template_group.parmTemplates()
        else:
            self.warningLog( "Error, cannot find anything since no parmTemplates (tuple) on: {}".format( parm_folder_or_template_group ) )
            return
        if label:
            search = [x for x in parm_templates if x.label() == label]
        elif name:
            search = [x for x in parm_templates if x.name() == name]
        else:
            self.warningLog( "Error: no label or name to search:" )
            self.warningLog( parm_folder_or_template_group )
            return
        if len(search) > 0:
            parm_template = search[0]
        else:
            parm_template = None
        return parm_template

    def replaceInParmTemplates( self, parm_templates, parm_template=None, replace_by='label' ):
        # Folder can also be a parm template group (whole node) since both folders and parm template groups can have .parmTemplates()
        if replace_by=='label':
            label = parm_template.label()
        else:
            name = parm_template.name()
        parm_templates_list = []
        replaced = False
        for x in parm_templates:
            if replace_by=='label':
                match = ( x.label() == label )
            else:
                match = ( x.name() == name )

            if match and not replaced:
                parm_templates_list.append(parm_template)
                replaced = True
            else:
                parm_templates_list.append(x)
        result = tuple(parm_templates_list)
        if not replaced:
            return
        # Return the new parm template tuple if found.
        return result

    def appendToParmTemplates( self, parm_templates, parm_template=None ):
        # Folder can also be a parm template group (whole node) since both folders and parm template groups can have .parmTemplates()
        parm_templates_list = list(parm_templates)
        parm_templates_list.append(parm_template)
        result = tuple(parm_templates_list)
        return result

    def append_version_db_tags(self, parm_template): # parm templates are tagged and versioned.  this provides a means to know if they should be replaced in the future
        self.debugLog( 'Aquire tags on' )
        self.debugLog( parm_template )
        tags = parm_template.tags()
        tags['version_db'] = self.parm_template_version
        self.debugLog( 'tags update: {}'.format( tags ) )
        parm_template.setTags(tags)
        self.debugLog( 'Updated versiondb tags' )
        return parm_template

    def ensure_db_exists( self, **kwargs ):
        #kwargs['items'] = kwargs['item_path']
        self.debugLog( 'ensure_db_exists kwargs: {}'.format( kwargs ) )
        node = hou.node( kwargs['item_path'] )
        kwargs['items'] = [ node ]    
        parm_template_version = self.parm_template_version
        self.debugLog( 'Check parm_template_version in parm template: {} node: {}'.format( parm_template_version, node.path() ) )
        parms_are_current = [ ( x.name()=='versioning' and ( 'version_db' in x.tags() ) and ( parm_template_version==x.tags()['version_db'] ) ) for x in node.parmTemplateGroup().parmTemplates() ]
        self.debugLog( 'List Acquired: {}'.format( parms_are_current ) )
        if any(parms_are_current) == False :
            # if the versioning folder doesn't exist on the node or is not tagged as current version, replace it
            self.debugLog( '...Adding Version DB Folder to node with kwargs: {}'.format(kwargs) )
            self.node = node
            self.update_rop_output_paths_for_selected_nodes(kwargs, version_db=True)
            # need to provide a method to preserve settings.
        else:
            self.debugLog( '...No need to update versioning parm template, is current.')

    # Be extremely careful with this.  Any changes will reuquire heavy testing!
    def pull_all_versions_to_all_multiparms( self, check_hip_matches_submit=False, force_pull=False, exec_in_main_thread=False, work_item=None, use_json_file=False, verbose=True, debug=False ):
        # intended for use on hip load of work items, and after graph cooks finish

        print('Pull versions: pull_all_versions_to_all_multiparms()')
        import pdg

        this_hip_file = hou.hipFile.name()
        last_submitted_hip_file = hou.node('/').userData('self.debug')

        if check_hip_matches_submit and last_submitted_hip_file is not None and this_hip_file != last_submitted_hip_file: # ensure we are using a hip file intended for the farm.
            print( 'Check matching filename for last submit.' )
            print( 'last_submitted_hip_file: {}'.format(last_submitted_hip_file) )
            print( 'this_hip_file: {}'.format(this_hip_file) )
            if self.debug: # this is used to debug standard file loading for a user
                print( 'Pull versions: Ignoring pull versions since hip name is not for farm use: {}'.format( hou.hipFile.name() ) )
                print('return')
                return None

        json_object = None

        if work_item is None:
            work_item = pdg.workItem()
        
        if work_item is not None and work_item.batchParent is not None:
            work_item = work_item.batchParent # We obtain data from the batch parent for a work item if provided.  if we already have the batch parent we just use the present work item.

        # if work_item is not None: # if we are cooking a work item, ensure the side care file is never used.  This may result in errors due to read/write lock issues
        #     use_json_file = False

        # conditions:
        # loading hip file without a work item - use json file
        # farm loading hip file with work item
        
        print('work_item: {}'.format(work_item))
        
        if work_item is not None and work_item.pyObjectAttribValue('versiondb') is not None and use_json_file == False: # for a cook process, we aquire the json data from the work item to avoid file lock issues / race conditions.
            print( 'Pull versions: get keys from json object attribute: versiondb' )
            json_object = work_item.pyObjectAttribValue('versiondb')

        if json_object is None and use_json_file: # the json blob can be loaded from a file, this should only be done for a UI, not for multiple running farm tasks, since we dont know if the file is still being written to.
            print( 'Pull versions: get keys from json file:' )
            file_path = self.get_sidecar_json_file_path()
            print( 'file_path: {}'.format(file_path) )
            json_object = self.get_sidecar_json_object(file_path=file_path)
        
        if json_object is None or len(json_object)==0 or not isinstance(json_object, dict):
            print( 'Pull versions: no json object exists. Skipping pull versions to parms.' )
            return None

        # get MD5 checksum on json_object to record what was set
        import hashlib
        last_loaded_md5 = str( hou.node('/').userData( 'last_loaded_md5' ) )
        new_md5 = str( hashlib.md5( str(json_object) ).hexdigest() )
        match = ( last_loaded_md5 == new_md5 )

        # Finally compare original MD5 with freshly calculated
        if force_pull:
            print("\n### MD5 verification ignored: Force Pulling versions... MATCH: {} LAST MD5: {} MD5: {}\n".format( match, last_loaded_md5, new_md5))
        else:
            if match:
                print("\n### MD5 verified to be previously loaded. Skipping pull versions. MATCH: {} LAST MD5: {} MD5: {}\n".format( match, last_loaded_md5, new_md5))
                return None
            else:
                print("\n### MD5 verification no match: Pulling versions... MATCH: {} LAST MD5: {} MD5: {}\n".format( match, last_loaded_md5, new_md5))
        
        print( json.dumps( json_object, indent=4, sort_keys=True) )

        version_prefix='version_'

        if exec_in_main_thread:
            print( '...Exec inmain thread' )
        else:
            print( '...Already in main thread')

        for version_db_hou_node_path in json_object:
            print( 'version_db_hou_node_path: {} '.format( version_db_hou_node_path ) )

            hou_node_path = self.get_hou_node_path_from_version_db_hou_node_path( version_db_hou_node_path ) # hou node can be different to the version db node.  this could be removed in future once pdg pilot submission works, this was a placeholder for stability.  to diagnose hangs due to parm.set, we needed to isolate nodes with user data, and nodes with the multiparm
            hou_node = hou.node(hou_node_path)

            if self.uses_version_db( hou_node ):
                kwargs = {}
                kwargs['item_path'] = hou_node_path
                self.debugLog( 'ensure_db_exists for kwargs: {}'.format(kwargs) )
                if exec_in_main_thread:
                    hdefereval.executeInMainThreadWithResult(self.ensure_db_exists, **kwargs) # add the version db to the target
                else:
                    self.ensure_db_exists( **kwargs )

            self.debugLog( '...End Prep node in list: {}'.format( hou_node_path ) )

            for key in json_object[version_db_hou_node_path]:
                value = json_object[version_db_hou_node_path][key]
                
                if key.startswith( version_prefix ) and not value.isdigit():
                    self.warningLog( 'ERROR: couldn\'t retrieve a version from key: {}'.format(key) )
                    return None

                print( 'pull: update user data key: {} value: {}'.format(key, value) )
                if exec_in_main_thread:
                    hdefereval.executeInMainThreadWithResult(hou.node(version_db_hou_node_path).setUserData, key, value)
                else:
                    hou.node(version_db_hou_node_path).setUserData( key, value )

            user_data_dict = hou.node(version_db_hou_node_path).userDataDict()
            
            print( 'pull: get versions' )
            version_db_index_keys = [ x[len(version_prefix): ] for x in user_data_dict if x.startswith(version_prefix) ]

            for index_key in version_db_index_keys: # use the keys to update the multiparm iteratively for versions.
                version=int( user_data_dict[version_prefix+index_key] )
                self.update_multiparm(hou_node_path, index_key, version=version, exec_in_main_thread=exec_in_main_thread, debug=0)

            parm_prefix = 'parm_'
            parm_names = [ x[len(parm_prefix):] for x in user_data_dict if x.startswith(parm_prefix) ]
            print( 'pull: get parms ' + str(parm_names) )
            # hou_node_path = self.get_hou_node_path_from_version_db_hou_node_path( version_db_hou_node_path )

            for parm_name in parm_names: # use the keys to update the multiparm iteratively for parm names
                if hou_node is not None and hou_node.parm(parm_name) is not None:
                    hou_parm = hou_node.parm(parm_name)
                    value = user_data_dict[ parm_prefix + parm_name ]

                    value = firehawk_read.resolve_pdg_vars(value, node_path=version_db_hou_node_path) # if no __ tokens exist in the string, this function will not alter the output

                    if exec_in_main_thread:
                        print( 'exec_in_main_thread... set parm {}: {}'.format( hou_parm.name(), value ) ) 
                        hdefereval.executeInMainThreadWithResult( hou_parm.set, value ) # this can cause crashing if run by pdg scehduler thread at the time of writing
                    else:
                        print( 'set parm {}: {}'.format( hou_parm.name(), value ) )
                        hou_parm.set(value)
                else:
                    print( '...Skipping invalid parm: ' + str( parm_name ) )

            def update_cache(dependent):
                dependent.parm('resetcookpass').pressButton()

            for dependent in hou_node.dependents(): # reset readers
                if dependent.type().nameComponents()[-2] == 'read_wedges':
                    if exec_in_main_thread:
                        print( 'exec_in_main_thread... Reset read_wedges: {}'.format( dependent.path() ))
                        hdefereval.executeInMainThreadWithResult( update_cache, dependent )
                    else:
                        print( 'Reset read_wedges: {}'.format( dependent.path() ))
                        update_cache(dependent)

        if exec_in_main_thread:
            hdefereval.executeInMainThreadWithResult(hou.node('/').setUserData, 'last_loaded_md5', new_md5)
        else:
            hou.node('/').setUserData( 'last_loaded_md5', new_md5 )
        print('\n### MD5 updated on cached user data at "/"  MD5: {}\n'.format(new_md5))


    def update_index(self, node, key_prefix=None, key_name=None, index_int=None, set_value=None):
        if ( index_int is None ) or ( key_prefix is None ) or ( key_name is None ):
            self.warningLog( 'Failed: update to index without variable' )
            return
        
        parm_name = key_name + str(index_int)
        self.debugLog( '...Update index name: {}'.format( parm_name ) )
        if set_value:
            def set_parm(value, node, parm_name):
                import hou
                if parm_name and value:
                    parm = node.parm( parm_name )
                    self.debugLog( '...Update index at path: {}'.format( parm.path() ) )
                    self.debugLog( 'to value: {}'.format( value ) )
                    if parm:
                        parm.set(value)
                        
                    else:
                        self.warningLog( "ERROR: Parm didn't exist when attempting to set for update index" )
                else:
                    self.warningLog( "ERROR: parm and or value not defined for parm.set for update index. path: {} parm: {} value: {}".format( node.path(), parm_name, value ) )

            # set_partial_parm_as_value = partial( set_parm, set_value, node )
            # set_partial_parm_as_value( parm_name )
            set_parm( set_value, node, parm_name )
            index_key = set_value
        else:
            index_key_parm = node.parm( parm_name )
            index_key = index_key_parm.eval()

        # if set_value and ( index_key != set_value ):
            # print "ERROR eval parm and dict will not match for these values", index_key, set_value
        dict_key = '{}_{}'.format( key_prefix, index_key )
        self.debugLog( 'set dict: {} to: {}'.format( dict_key, str(index_int) ) )
        node.setUserData( dict_key , str(index_int) )

    def multiparm_housecleaning(self, node, multiparm_count, key_prefix, key_name):
        self.debugLog( "Validate and clean out old dict. total parms: {}".format( multiparm_count ) )
        index_keys = []
        for index_int in range(1, int(multiparm_count)+1):
            # first update the index key dict
            index_key = node.parm( key_name + str(index_int) ).eval()
            index_keys.append( '{}_{}'.format( key_prefix, index_key ) )
            self.update_index(node, key_prefix=key_prefix, key_name=key_name, index_int=index_int)
            self.debugLog( 'update index: {} node: {}'.format( index_int, node ) )

            # then update the id dict # need to fix id updates - may not be working.
            # id_key_prefix = key_prefix + '_id'
            # id_key_name = 'id_'
            # index_key = node.parm( id_key_name + str(index_int) ).eval()
            # index_keys.append( '{}_{}'.format( id_key_prefix, index_key ) )
            # self.update_index(node, key_prefix=id_key_prefix, key_name=id_key_name, index_int=index_int)

        self.debugLog( 'keys to preserve: {}'.format( index_keys ) )
        # first all items in dict will be checked for existance on node.  if they dont exist they will be destroyed on the dict.
        user_data_total = 0

        keys_to_destroy = []
        for index_key, value in node.userDataDict().items():
            if index_key not in index_keys and '{}_'.format(key_prefix) in index_key:
                self.debugLog( "node missing key: {} : {} will remove".format( index_key, value ) )
                keys_to_destroy.append(index_key)
            else:
                user_data_total += 1

        # keys must be destroyed after they are known in the last operation or lookup will fail mid loop.
        if len(keys_to_destroy) > 0:
            for index_key in keys_to_destroy:
                node.destroyUserData(index_key)
                self.debugLog( "destroyed key: {}".format( index_key ) )

    def get_sorted_verdb_list( self, hou_node_path ):
        hou_node_path = firehawk_read.get_version_db_hou_node_path( hou_node_path=hou_node_path ) # the node containing the version db data can be different to the node we are interested in.
        
        hou_node = hou.node( hou_node_path )
        verdb = hou_node.userDataDict()
        # sort list by value indices
        verdb_list = sorted(verdb, key=verdb.get)
        # clean list if not verdb
        verdb_prefix='verdb_'
        verdb_list = [ x for x in verdb_list if verdb_prefix in x ]
        # self.debugLog( 'sorted indexes by current multiparm indices {}'.format( verdb_list ) )

        # if new entry isn't last, then insert#
        verdb_sorted = self.sorted_nicely( verdb_list )

        return verdb_sorted

    def get_sorted_index_keys( self, hou_node_path ):
        verdb_prefix='verdb_'
        verdb_sorted = self.get_sorted_verdb_list( hou_node_path )
        version_db_index_keys = [ x[len(verdb_prefix): ] for x in verdb_sorted if x.startswith(verdb_prefix) ]
        return version_db_index_keys

    def sorted_nicely( self, l ): 
        convert = lambda text: int(text) if text.isdigit() else text 
        alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ] 
        return sorted(l, key = alphanum_key)

    def update_multiparm(self, hou_node_path, index_key, version=None, exec_in_main_thread=True, debug=0):
        if debug: print( 'update multiparm' )
        hou_node = hou.node( hou_node_path )
        multiparm_index = hou_node.userData('verdb_'+index_key)
        index_key_multiparm = hou_node.parm('index_key_' + str(multiparm_index))
        # if the parm exists, but the key doesn't match, its possible the user deleted the entry but an error occured in the callback.
        # this really shouldn't ever happen, but if it were to occur housecleaning should happen.

        # multiparm index is the string to append to parm names to retrive the correct multiparm instance

        def multiparm_housecleaning_func( hou_node_path ):
            import firehawk_dynamic_versions
            hou_node = hou.node(hou_node_path)
            version_count_parm = hou_node.parm('version_db0')
            multiparm_count = version_count_parm.eval()
            firehawk_dynamic_versions.versions(hou_node).multiparm_housecleaning( hou_node, multiparm_count, key_prefix='verdb', key_name='index_key_' )

        if debug: print( 'update multiparm: housecleaning init' )
        # partial_multiparm_housecleaning = partial( multiparm_housecleaning_func, hou_node_path )

        if index_key_multiparm and index_key_multiparm.eval() != index_key:
            self.warningLog( "WARNING: HOUSECLEANING IN A SCENARIO WHERE IT PROBABLY SHOULDN'T, THE PARM EXISTED BUT DIDN'T MATCH THE DICTIONARY" )
            version_count_parm = hou_node.parm('version_db0')
            multiparm_count = version_count_parm.eval()
            # self.multiparm_housecleaning( hou_node, multiparm_count, key_prefix='verdb', key_name='index_key_' )
            if exec_in_main_thread:
                if debug: print( 'update multiparm: housecleaning in main thread' )
                hdefereval.executeInMainThreadWithResult( multiparm_housecleaning_func, hou_node_path )
            else:
                if debug: print( 'update multiparm: housecleaning' )
                # partial_multiparm_housecleaning()
                multiparm_housecleaning_func( hou_node_path )
            multiparm_index = hou_node.userData('verdb_'+index_key)

        if debug: print( 'update multiparm: end housecleaning' )
        # if the index doesn't exist in the userDataDict, or the parm, then a new parm instance must be created in the live hip file. userData should be updated by the parameter callback.
        if multiparm_index is None or index_key_multiparm is None:
            verdb = hou_node.userDataDict()
            new_index_key = 'verdb_'+index_key
            # sort list by value indices, and add current item
            verdb_list = sorted(verdb, key=verdb.get) + [new_index_key]
            # clean list if not verdb
            verdb_list = [ x for x in verdb_list if 'verdb_' in x ]
            self.debugLog( 'sorted indexes by current multiparm indices {}'.format( verdb_list ) )

            # if new entry isn't last, then insert#
            verdb_sorted = self.sorted_nicely( verdb_list )
            append = True

            version_count_parm = hou_node.parm('version_db0')

            if version_count_parm is None:
                raise Exception( 'Parm version_db0 missing at hou_node: {}'.format(hou_node.path()) )

            def insert_multi_parm_instance(hou_node_path, index):
                import hou
                hou_node = hou.node(hou_node_path)
                parm = hou_node.parm('version_db0')
                parm.insertMultiParmInstance(index)
                self.debugLog( '...new multiparm instance at: {} to:'.format( parm.path(), index ) )
                return

            if debug: print( 'update multiparm: defin partial insert' )
            partial_insert_multi_parm_instance = partial( insert_multi_parm_instance, hou_node_path )
            
            # determine if insertion is needed
            for idx, val in enumerate( verdb_sorted ):
                # find entry in list to match, then get index for next item, since current item has no index
                if val == new_index_key and idx < len(verdb_sorted)-1:
                    next_index_key = verdb_sorted[idx+1]
                    next_index_int = hou_node.userData(next_index_key)
                    if next_index_int is not None: # validate a dicitonary entry exists for the next item
                        next_index_int = int(next_index_int)
                    else:
                        hou.ui.displayMessage('no dict entry for next index: '+next_index_key)
                    
                    self.debugLog( '...Inserting a multiparm instance' )
                    if exec_in_main_thread:
                        if debug: print( 'update multiparm: insert inmain thread' )
                        hdefereval.executeInMainThreadWithResult( partial_insert_multi_parm_instance, int(next_index_int)-1 )
                    else:
                        if debug: print( 'update multiparm: insert inmain thread' )
                        partial_insert_multi_parm_instance( int(next_index_int)-1 )
                    self.debugLog( 'Inserted.  update index' )
                    multiparm_index = int(next_index_int)
                    append = False
                    break
            self.debugLog( 'check if append' )
            if append:
                self.debugLog( '...Appending a multiparm instance at path: {}'.format( hou_node_path ) )
                multiparm_index = int(version_count_parm.eval()+1) # new index # increment count
                if exec_in_main_thread:
                    if debug: print( 'update multiparm: insert append in main thread' )
                    hdefereval.executeInMainThreadWithResult( partial_insert_multi_parm_instance, int(multiparm_index-1) ) # set key string on parm
                else:
                    if debug: print( 'update multiparm: insert append' )
                    partial_insert_multi_parm_instance( int(multiparm_index-1) )
                self.debugLog( 'Appended' )
                
            if multiparm_index is not None:
                self.debugLog( 'update_index_func' )
                
                def update_index_func(hou_node_path, multiparm_index, index_key):
                    import firehawk_dynamic_versions
                    hou_node = hou.node(hou_node_path)
                    self.debugLog( 'update node {}'.format( hou_node ) )
                    firehawk_dynamic_versions.versions(hou_node).update_index(hou_node, key_prefix='verdb', key_name='index_key_', index_int=multiparm_index, set_value=index_key) # since a new space is inserted, that must be set, the dict entry must be updated, and we do housecleaning aynway since the others will be wrong # could consider just using the housecleaning op and may just be fine
                    return
                # self.update_index(hou_node, key_prefix='verdb', key_name='index_key_', index_int=multiparm_index, set_value=index_key) # since a new space is inserted, that must be set, the dict entry must be updated, and we do housecleaning aynway since the others will be wrong # could consider just using the housecleaning op and may just be fine

                self.debugLog( 'use values: {} {} {}'.format( hou_node_path, multiparm_index, index_key ) )
                # partial_update_index_func = partial( update_index_func, hou_node_path, multiparm_index, index_key )
                
                # self.debugLog( 'partial_update_index_func' )
                if exec_in_main_thread:
                    if debug: print( 'update multiparm: defer update index in main thread' )
                    hdefereval.executeInMainThreadWithResult( update_index_func, hou_node_path, multiparm_index, index_key )
                    # hdefereval.executeInMainThreadWithResult( firehawk_dynamic_versions.versions(hou_node).update_index )
                else:
                    if debug: print( 'update multiparm: defer update index' )
                    # partial_update_index_func()
                    update_index_func( hou_node_path, multiparm_index, index_key )
                
                self.debugLog( 'housecleaning' )
                if exec_in_main_thread:
                    if debug: print( 'update multiparm: post housecleaning in main thread' )
                    hdefereval.executeInMainThreadWithResult( multiparm_housecleaning_func, hou_node_path )
                else:
                    if debug: print( 'update multiparm: post housecleaning' )
                    # partial_multiparm_housecleaning()
                    multiparm_housecleaning_func( hou_node_path )
                self.debugLog( 'end housecleaning' )
        else:
            # if multiparm_index exists, ensure it is an int
            multiparm_index = int(multiparm_index)

        if debug: print( 'update multiparm: end update keys' )

        if version is not None:
            multiparm_name = 'version_{}'.format( str(multiparm_index) )
            parm = hou_node.parm( multiparm_name )

            self.debugLog( "Setting dynamic override and value on multiparm: {} {}".format( multiparm_name, version ) )
            # self.timeLog( label='Dynamic versioning: Prepare to set Multiparm: {}'.format( multiparm_name ) )            
            
            if parm.eval() != version:
                if exec_in_main_thread:
                    if debug: print( 'update multiparm: update version in main thread' )
                    hdefereval.executeInMainThreadWithResult( parm.set, version ) # values in the db multiparm (UI) are updated for the index_key.  
                else:
                    if debug: print( 'update multiparm: update version' )
                    parm.set(version)

    def get_sidecar_json_file_path( self, work_item=None, debug=debug_default ):
        if work_item is None:
            hip_path = hou.node('/').userData('last_submitted_hip_file')
        else:
            hip_path = str( work_item.data.stringData('hip', 0) )

        sidecar_file_path = None
        if hip_path is not None:
            sidecar_file_path = '.'.join( hip_path.split('.')[:-1] ) + '.json'

            if debug: print('sidecar_file_path: {}'.format( sidecar_file_path ) )
            return sidecar_file_path

        if debug: print('No sidecar file at: {} from hip: {}'.format(sidecar_file_path, hip_path))

    def get_sidecar_json_object( self, file_path=None ):
        if file_path is not None:
            sidecar_file_path = file_path
        else:
            sidecar_file_path = self.get_sidecar_json_file_path()

        self.debugLog( 'sidecar_file_path: {}'.format(sidecar_file_path) )
        
        json_object = {}
        if sidecar_file_path is not None and os.path.isfile( sidecar_file_path ):
            with open(sidecar_file_path, 'r') as versiondb_file:
                # versiondb_file = open(sidecar_file_path, 'r')
                json_object = json.load(versiondb_file)
                # versiondb_file.close()
                if not isinstance( json_object, dict ):
                    json_object = {}
                else:
                    self.debugLog( 'Loaded existing JSON data: {}'.format(json_object) )

        return json_object

    def get_hou_node_path_from_version_db_hou_node_path(self, version_db_hou_node_path): # optionally the version db could be stored on a different node.  thie method allows us to aquire the original node
        version_db_hou_node = hou.node( version_db_hou_node_path )

        name = version_db_hou_node.name()
        prefix='versiondb_'
        if name.startswith(prefix): name = name[len(prefix):] # remove prefix if present
        hou_node_path = version_db_hou_node.parent().path() + '/' + name

        return hou_node_path

    def log_environ(): # sort and log env vars, outputting to a file in pdgtemp.  Usefull for diffing to determine comparisons between farm and local processes.
        print('Redirect stdout')
        original_stdout = sys.stdout # Save a reference to the original standard output
        script_dir=os.getenv('PDG_SCRIPTDIR', None)

        if script_dir is not None:
            file_path=os.path.join( script_dir, 'pdgenv.json' )
            
            print( "\nPDG ENV: {}\n".format( file_path ) )
            
            with file( file_path , 'w' ) as db_file:
            
                sys.stdout = db_file # Change the standard output to the file we created.
                print( json.dumps( dict(os.environ), indent=4, sort_keys=True) )
                
                sys.stdout = original_stdout 

        else:
            print( "/nPDG ENV:/n")
            print( json.dumps( dict(os.environ), indent=4, sort_keys=True) )