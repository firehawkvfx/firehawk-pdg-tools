#!/usr/bin/python

# pdg dependencies

import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections import namedtuple
from distutils.spawn import find_executable
from multiprocessing import cpu_count

# firehawk versioning

import hou # Try to put this only in the modules that need it.  attempt to remove it completely in the future.  We observed one hang in 17.5.460 when setting a parm and importing hou , though so it might not be possible.
import pdg
import sys
import subprocess
import os
import errno
import numpy as np
import datetime as dt
# from functools import partial

import collections

if hou.isUIAvailable():
    # callbacks
    import hdefereval

from shutil import copyfile

print("Using firehawk_submit: {}".format(__file__))
import firehawk_asset_handler
reload(firehawk_asset_handler)
import firehawk_read
reload(firehawk_read)
import firehawk_dynamic_versions
reload(firehawk_dynamic_versions)

versions_object = firehawk_dynamic_versions.versions()

houdini_version = float( '.'.join( os.environ['HOUDINI_VERSION'].split('.')[0:2] ) )
houdini_minor_version = os.environ['HOUDINI_VERSION'].split('.')[2]
update_method = 'user_data' # options: [ 'parms', 'user_data']. The method to store versions that are submitted.

#####

import firehawk_plugin_loader
import firehawk.plugins
import firehawk.api
plugin_modules, api_modules=firehawk_plugin_loader.load_plugins() # load modules in the firehawk.api namespace
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=10)
create_asset = firehawk_plugin_loader.module_package('create_asset').create_asset

# It's possible to customize work item attributes that will be attached to a submission object ordered dict.
submission_attributes = firehawk_plugin_loader.module_package('submission_attributes').submission_attributes.get_submission_attributes()
timestamp_submit = firehawk_plugin_loader.module_package('timestamp_submit').timestamp_submit

debug_default = int( os.getenv('DEBUG_PDG', 0) )

class submit():
    def __init__(self, node=None, debug=debug_default, logger_object=None):
        self.node = node
        self.selected_nodes = []
        self.pdg_node = ''
        self.debug = debug
        self.start_time = time.time()
        self.last_time = None

        self.logger_object = None
        if logger_object is not None:
            self.logger_object = logger_object

        if hasattr(self.node, 'parent'):
            self.parent = self.node.parent()
        else:
            self.parent = None
        
        self.top_net = None
        self.preflight_node = None
        self.preflight_path = None
        self.post_target = None
        self.post_target_path = None
        self.parm_group = None
        self.found_folder = None
        self.handler = None
        self.preflight_pdg_node = None
        self.preflight_pdg_node_path = None
        self.preflight_pdg_node_name = None

        self.preflight_status = None

        self.format = None

        self.hip_path = hou.hipFile.path()
        self.hip_dirname = os.path.split(self.hip_path)[0]
        self.hip_basename = re.sub('\.hip$', '', hou.hipFile.basename())
        self.hip_path_submission = None

        self.source_top_nodes = []
        self.added_workitems = []
        self.added_dependencies = []

        self.parmprefix = 'submit'
        self._verbose = True # this should inherit a var / parm from a scheduler/ default scheduler
        if self._verbose:
            self.debug = 10
        # firehawk_logger.initLogger(logger, logging.ERROR)
        firehawk_logger.initLogger()
        self.spacer = '' # Allows offsetting of text for readbility in blocks

    # def initLogger(self, logger, log_level):
    #     """
    #     Initialize the logger to write out to stdout
    #     with minimum log level.
    #     """
    #     logger.setLevel(log_level)
    #     handler = logging.StreamHandler(sys.stdout)
    #     handler.setLevel(log_level)
    #     logger.addHandler(handler)

    def _verboseLog(self, args): # This is taken from scheduler.py
        if self._verbose:
            print('{}: {}: {}{}'.format( time.strftime('%H:%M:%S', time.localtime()), self.parmprefix, self.spacer, args))
            # print(*args)
            sys.stdout.flush()

    # def _verboseLog(self, *args):
    #     if self._verbose:
    #         print('{}: {}: '.format(
    #             time.strftime('%H:%M:%S', time.localtime()),
    #             self.parmprefix), end='')
    #         print(*args)
    #         sys.stdout.flush()


    def timeLog(self, start_time=None, label=''): # provides time passed since start time and time since last running of this method.
        if start_time is not None:
            self.start_time = start_time
        else:
            start_time = self.start_time
        if self.last_time is None:
            self.last_time = start_time
        
        message = "--- {} seconds --- Passed during Pre Submit --- {} seconds --- {}".format( '%.4f' % (time.time() - start_time),  '%.4f' % (time.time() - self.last_time), label )
        self._verboseLog( message )
        
        self.last_time = time.time()

    def debugLog(self, message):
        if self.debug>=10: self._verboseLog( message )
        # if self.logger_object and hasattr( self.logger_object, 'debug' ):
        #     self.logger_object.debug( message )
        # else:
        #     if self.debug>=10: print( message )

    def infoLog(self, message):
        if self.debug>=5: self._verboseLog( message )
        # if self.logger_object and hasattr( self.logger_object, 'info' ):
        #     self.logger_object.info( message )
        # else:
        #     if self.debug>=5: print( message )

    def warningLog(self, message):
        self._verboseLog( message )
        # if self.logger_object and hasattr( self.logger_object, 'warning' ):
        #     self.logger_object.warning( message )
        # else:
        #     print( message )

    def assign_preflight(self):
        self.preflight_node = self.node
        self.debugLog( "assign preflight node; {} on topnet: {}".format( self.preflight_node.path(), self.parent ) )

        # get the template group for the parent top node.
        self.parm_group = self.parent.parmTemplateGroup()
        self.debugLog(  "Create folder parm template" )

        self.parm_folder = hou.FolderParmTemplate("folder", "Firehawk")
        self.parm_folder.addParmTemplate(hou.StringParmTemplate(
            "preflight_node", "Preflight Node", 1, [""], string_type=hou.stringParmType.NodeReference))

        # Search for the template folder.  if it already exists it will be replaced in order to ensure parms are current.
        self.found_folder = self.parm_group.findFolder("Firehawk")

        self.debugLog( "self.found_folder: {}".format( self.found_folder ) )
        # If a folder already exists on the node, remove it and add it again.  This deals with any changes to the parm layout if they occur.
        if self.found_folder:
            self.parm_group.remove(self.found_folder)

        # re add the folder to the template group.
        self.parm_group.append(self.parm_folder)

        # update the parm template on the parent node.
        self.parent.setParmTemplateGroup(self.parm_group)

        # set values for path to preflight node.

        self.parent.parm("preflight_node").set(self.preflight_node.path())

    def _runInUIThread(self, func):
        """This decorator ensures that the function runs in the UI thread."""
        def decorator(*args, **kwargs):
            # We assume that the main thread is the UI thread.
            # If this ever changes then the code below needs to be updated.

            import threading
            is_ui_thread = \
                isinstance(threading.current_thread(), threading._MainThread)
            if is_ui_thread:
                return func(*args, **kwargs)

            # If the Houdini UI is not available then there is no UI thread
            # so just run the code in the current thread.
            import hou
            if not hou.isUIAvailable():
                return func(*args, **kwargs)

            # If this thread has the HOM lock we cannot defer calling the target
            # function in the main thread or else we will hit a deadlock.
            # Therefore we take our chances and run the target function in this
            # thread.
            if hou._isCurrentThreadHoldingHOMLock():
                return func(*args, **kwargs)

            # Check if we can import the hdefereval module.
            # If we can then we can use the module to execute the function in the
            # UI thread.
            is_hdefereval_available = False
            try:
                import hdefereval
                is_hdefereval_available = True
            except:
                is_hdefereval_available = False

            if is_hdefereval_available:
                return hdefereval.executeInMainThreadWithResult(
                    func, *args, **kwargs)

            # If we reached this point then hdefereval is not available
            # so as a last resort just run the function in this thread.
            return func(*args, **kwargs)

        decorator.__name__ = func.__name__
        if hasattr(func, "func_doc"):
            decorator.__doc__ = func.__doc__
        return decorator

    ### Warning temp disable timestamped submission to debug ###

    def save_hip_for_submission(self, \
                                hip_name=None, \
                                timestamp_submission=(os.getenv('FHVAR_timestamp_submission','true').lower() in ('true', 'yes', '1')), \
                                set_user_data=False, \
                                preflight=True, \
                                exec_in_main_thread=True \
                                ): 
                                # this will duplicate the save to a target folder used for achival and rendering of submissions.
        self.debugLog( 'get parent' )
        self.debugLog( self.node )
        taskgraph = None
        parent_top_net = self.get_parent_top_net( self.node )

        if preflight: # it possible to execute another node prior to the main graph.
            self.preflight_path = parent_top_net.parm("preflight_node").eval()
            self.preflight_node = parent_top_net.node( self.preflight_path )
        else:
            self.preflight_path = None
            self.preflight_node = None

        if parent_top_net.parm('regenerationtype').evalAsInt() != 1:
            self.debugLog( "...Setting 'Update Work Items Only' on TOP Net for On Node Recook to ensure work items dont always cook after saving hip." )
            parent_top_net.parm('regenerationtype').set(1)
        
        self.debugLog( "self.preflight_node: {}".format( self.preflight_node ) )

        hip_name = self.hip_path

        datetime_object, datetime_object_str = timestamp_submit.update_timestamp()
        
        if timestamp_submission:
            self.debugLog( "Will Save an alternate hip file for submission" )
            timestamp_str = timestamp_submit.timestamp_submission_str(datetime_object, self.hip_dirname, self.hip_basename)    
            self.debugLog('Current Timestamp: {}'.format( timestamp_str ) )

            # construct asset for timestamped hip
            asset_creator = firehawk_asset_handler.asset( debug=self.debug, logger_object=None, start_time=time.time() ) # An instance of the asset handler with passed through logging. TODO: starndardise the root time / logging, shouldn't need to pass it through.
            tags = create_asset.get_tags_for_submission_hip(hip_name, variant=timestamp_str, parent_top_net=parent_top_net) # tags are passed to the asset creator to construct a path
            # create asset for hip file
            hip_name, version = asset_creator.custom_create_new_asset_version( tags, show_times=True, register_hip=False )
            self.infoLog( "Created asset_path: {}".format( hip_name ) )

        if hip_name is None:
            self.warningLog( "Failed: you must enable timestamp submission or define a hip name" )
            return

        if preflight and self.preflight_node is None:
            self.warningLog(  "Failed to aquire preflight node" )
            return
        
        if set_user_data:
            self.debugLog( "Set last_submitted_hip_file on node '/' hip_name: {}".format( hip_name ) )
            if exec_in_main_thread:
                hdefereval.executeInMainThreadWithResult( hou.node('/').setUserData, 'last_submitted_hip_file', hip_name ) # ...And stash as user data since it doesn't have to be search for through the tree.
                hdefereval.executeInMainThreadWithResult( hou.node('/').setUserData, 'last_submitted_time', datetime_object_str )
            else:
                hou.node('/').setUserData( 'last_submitted_hip_file', hip_name )
                hou.node('/').setUserData( 'last_submitted_time', datetime_object_str )

        self.infoLog( "Saving: {}".format( self.hip_path ) )
        hou.hipFile.save(self.hip_path)

        taskgraph = os.path.splitext(hip_name)[0] + '.taskgraph.py'
        self.infoLog( "Copy {} to {}".format(self.hip_path, hip_name) )
        copyfile(self.hip_path, hip_name)
        self.debugLog( "Finished Copy for Farm." )
        self.infoLog( "hip_name: {}".format( hip_name ) )
        return hip_name, taskgraph

    def get_upstream_workitems(self):
        # this will generate the selected workitems
        self.pdg_node = self.node.getPDGNode()
        self.node.executeGraph(False, False, False, True)
        
        added_workitems = []

        added_nodes = []
        added_node_dependencies = []

        def append_node_dependencies(node):
            added_node_dependencies.append(node)
            if len(node.inputs) > 0:
                for input in node.inputs:
                    input_connections = input.connections
                    self.debugLog( "input_connections: {}".format( input_connections ) )
                    if len(input_connections) > 0:
                        for connection in input_connections:
                            dependency = connection.node
                            if dependency not in added_nodes:
                                added_nodes.append(dependency)

        
        added_nodes.append(self.pdg_node)
        for node in added_nodes:
            append_node_dependencies(node)
        diff_list = np.setdiff1d(added_nodes, added_node_dependencies)
        
        while len(diff_list) > 0:
            for node in diff_list:
                append_node_dependencies(node)
            diff_list = np.setdiff1d(
                added_nodes, added_node_dependencies)

        self.debugLog( "added_nodes: {}".format( added_nodes ) )

        for node in added_nodes:
            for workitem in node.workItems:
                added_workitems.append(workitem)

        return added_workitems

    def protect_upstream_workitem_directories(self):
        added_workitems = self.get_upstream_workitems()
        # nodes - inputs[0].connections[0].node.inputs[0].connections[0].node

        def touch(path):
            with open(path, 'a'):
                os.utime(path, None)

        def get_size(start_path = None):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(start_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    # skip if it is symbolic link
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
            return total_size

        def sizeof_fmt(num, suffix='B'):
            for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
                if abs(num) < 1024.0:
                    return "%3.1f%s%s" % (num, unit, suffix)
                num /= 1024.0
            return "%.1f%s%s" % (num, 'Yi', suffix)
        
        protect_dirs = []
        sizes = []

        for work_item in added_workitems:
            result_data_list = work_item.resultData
            expected_result_data_list = work_item.expectedResultData

            for result_data in result_data_list:
                path = result_data[0]
                path_dir = os.path.split(path)[0]
                if path_dir not in protect_dirs:
                    protect_dirs.append(path_dir)
                    protect_file = os.path.join(path_dir, '.protect')
                    touch(protect_file)
                    size = get_size(path_dir)
                    self.debugLog( "add .protect file into protect_dir: {} {}".format( path_dir, sizeof_fmt(size) ) )
                    sizes.append( size )
            
            for result_data in expected_result_data_list:
                path = result_data[0]
                path_dir = os.path.split(path)[0]
                if path_dir not in protect_dirs:
                    protect_dirs.append(path_dir)
                    protect_file = os.path.join(path_dir, '.protect')
                    touch(protect_file)
                    size = get_size(path_dir)
                    self.debugLog( "add .protect file into protect_dir: {} {}".format( path_dir, sizeof_fmt(size) ) )
                    sizes.append( size )

        total_size = sizeof_fmt(sum(sizes))
        self.debugLog( "total_size: {}".format( total_size ) )

    def dirty_upstream_source_nodes(self):
        # this will generate the selected workitems
        self.debugLog( "Dirty Upstream Source Nodes" )

        added_workitems = self.get_upstream_workitems()

        source_top_nodes = []
        for workitem in added_workitems:
            if len(workitem.dependencies) == 0:
                if workitem.node not in source_top_nodes:
                    source_top_nodes.append(workitem.node)

        for source_top_node in source_top_nodes:
            source_top_node.dirty(False)
            self.debugLog( "Dirtied source_top_node: {}".format( source_top_node.name ) )

    def get_major_version_from_name(self, name):
        # print 'get version from name', name
        regex_result = re.search(r"_v([0-9][0-9][0-9]).[0-9]?[0-9]?[0-9]?", name)
        if regex_result.groups >= 1:
            version = int(regex_result.group(1))
            self.debugLog( 'version: {}'.format( version ) )
            return version
        else:
            self.warningLog( 'Error getting version from hip name' )

    def overrideHipPath(self, work_item=None, hip_path=None, item_command=None):
        # if item_command is None: item_command=work_item.command
        
        if work_item and hip_path:
            # work_item.data.setString('hip', hip_path, 0)
            work_item.setFileAttrib('hip', pdg.File(hip_path, 'file/hip', 0, False), 0)
            self.debugLog( 'hip attrib result: {}'.format( work_item.fileAttribValue('hip').path ) )

        if work_item and hip_path and item_command:
            # old_hip_path = work_item.data.stringData('hip', 0)
            # hip_path = work_item.data.stringData('hip', 0)
            self.debugLog( 'item_command: {}'.format( item_command ) )
            # split item command into groups
            regex = re.search(r'(.*")(\S*hip)("?.*)', item_command)
            command_list = []
            replaced = False
            # replace only one hip path in the group.
            for item in regex.groups():
                if '.hip' in item and not replaced:
                    item = hip_path
                    replaced = True
                command_list.append(item)
            item_command = ''.join(command_list)

            work_item.setCommand(item_command)

            self.debugLog( '...Updated item_command: {}'.format( item_command ) )
            
            return item_command

    def get_parent_top_net(self, parent): # first parent, will recurse from here until top net is found
        top_net = firehawk_read.get_parent_top_net(parent)
        return top_net

    def onPreSubmitItem(self, work_item, job_env, item_command, logger_object=None):
        try:
            # this can be used in place of the on presubmit item code to insert functionality during onscheduled callback.
            print('onpresubmit.')
            
            # print('job_env:')
            # print( json.dumps( job_env, indent=4, sort_keys=True) )

            if 'disable_update_versions' in job_env: # by default, in houdini sessions the multiparms will update from whatever changes are declared in the json blob after it is written to disk.  this can also be used for recovery of the scene state after partial or full completion.  Updating parms will not occur in Pilot PDG, it will just write the declaritive json blob to disk so that the next time the scene is loaded everything can update.  work items themselves must not refer to the json blob on disk - that is reserved solely for the interactive scene / loading.  work items instead refer to the blob as a python object as a provided work item attribute.  during the 456.py load if the object is found it will update al the parms.
                self.disable_update_versions = int(job_env['disable_update_versions'])
            else:
                self.disable_update_versions = 0

            if logger_object is not None:
                self.logger_object = logger_object

            self.start_time = time.time()

            self.infoLog( "\n...onPreSubmitItem running" )

            if item_command is None:
                item_command = work_item.command
            
            self.infoLog( "\nCheck roppath in node parameters" )

            rop_node = None
            if 'roppath' not in work_item.node.parameterNames:
                self.infoLog( "Checking accepted output types: No roppath in parms for workitem." )
                top_node = work_item.node.topNode()
                top_node_type_name = top_node.type().nameComponents()[-2]
                
                if top_node_type_name not in versions_object.output_types:
                    self.infoLog( "Bypassing onScheduleVersioning(): Top Node: {} not in accepted output types: {}".format( top_node_type_name, versions_object.output_types ) )
                    return item_command

                self.infoLog( "{} found in output_types.  Continuing...".format(top_node_type_name) )
                # rop_node = top_node
                rop_node = True
            else:
                self.infoLog( "rop_node = True" )
                # rop_node = hou.node( str( work_item.node['roppath'].evaluate() ) )
                rop_node = True
            
            self.debugLog( "__init__" )
            # self.__init__( rop_node, debug=self.debug, logger_object=self.logger_object ) # can we try and remove this? difficult to debug

            self.debugLog( "Get top node" )
            node = work_item.node.topNode()

            parent = node.parent()

            self.top_net = self.get_parent_top_net( parent )

            if not self.top_net:
                self.warningLog( "ERROR: Couldn\'t evaluate top net for work item." )
                return None

            # preflight_parm = self.top_net.parm('preflight_node')

            print('...Checking if hip file must be replaced for submission')
            self.debugLog( '...Checking if hip file must be replaced for submission' )
            if rop_node:
                # preflight_top = self.top_net.node(self.top_net.parm('preflight_node').eval())
                # preflight_hip_path_parm = preflight_top.parm('hip_path')
                exec_hip = hou.node('/').userData( 'last_submitted_hip_file' )
                if exec_hip is not None and exec_hip != '':
                    self.exec_hip = exec_hip
                    ### Override the hip file used in the command to use an abolute path and archived hip file for rendering
                    if ( '.hip' in self.exec_hip ) and ( '.hip' in work_item.command ):
                        self.debugLog( '...Overidding HIP file in command to: {}'.format( self.exec_hip ) )
                        item_command = self.overrideHipPath( work_item=work_item, hip_path=self.exec_hip, item_command=work_item.command )
                        if self.exec_hip not in work_item.command:
                            self.warningLog( "ERROR: hip file wasn't correctly updated in work_item.command" )
                    elif ( '.hip' in self.exec_hip ):
                        self.overrideHipPath( work_item=work_item, hip_path=self.exec_hip )
                        self.debugLog( '...Overided HIP attrib to: {}'.format( work_item.fileAttribValue('hip').path ) )
                        if self.exec_hip != work_item.fileAttribValue('hip').path:
                            msg="ERROR: hip file wasn't correctly updated on work_item attrib"
                            self.warningLog( msg )
                            raise pdg.CookError( msg )
                            return None
                    else:
                        self.debugLog( '...Skipping Overide HIP file in command. self.exec_hip: {} work_item.command: {}'.format( self.exec_hip, work_item.command ) )
                else:
                    self.warningLog( 'ERROR: couldn\'t evaluate the hip file being used for the job accurately from the preflight node' )
                    return None
            else:
                msg = "ERROR: did not correctly set hip file for workitem"
                self.warningLog( msg )
                raise pdg.CookError( msg )
                return None

            self.infoLog( "Get index_key" )
            self.index_key = firehawk_read.getLiveParmOrAttribValue(work_item, 'index_key')

            self.debugLog( "index_key: {}".format( self.index_key ) )
            version = None
            if self.index_key is not None:
                ### If an self.index_key is provided, we assume that onschedule dynamic versioning per wedge will be used, so there must be an output on disk
                ### dynamic versioning also only applies to houdini cooks presently, but support can be added for other types (nuke / katana) so long as they resolve the dynamic versioning json output.
                self.debugLog( "on schedule version handling: {}".format( work_item ) )
                self.timeLog(label='Dynamic versioning: Prep')

                if firehawk_read.get_is_exempt_from_hou_node_path(work_item): # some items wont need an asset, but it may need ord_dict for customisation of command formatting. a tracker is one example of this.
                    self.onScheduleVersioning( work_item, job_env['PDG_DIR'] )
                    self.timeLog( label='Dynamic versioning. No version required.' )
                elif firehawk_read.get_hou_node_path(work_item) is not None and work_item.intAttribValue('disable_output', 0) != 1 : # These work items must have assets / versions on disk.
                    version = self.onScheduleVersioning( work_item, job_env['PDG_DIR'] )
                    self.timeLog( label='Dynamic versioning. version: {}'.format(version) )
                    
                    if version is None:
                        msg = 'FAILED: versioning. work item output version: {}'.format( version )
                        raise pdg.CookError( msg )
                        return None
            else:
                self.debugLog( "Skipping versioning: no index_key or resolved hou node path for work item" )
            
            self.infoLog( "item_command: {}".format( item_command) )
            self.timeLog(label='Up to end')
            self.infoLog( "...onPreSubmitItem complete for work_item: {} command: {}\n".format(work_item.name, item_command) )

            return item_command

        except ( Exception ), e :
            import traceback
            msg = 'ERROR: During onPreSubmitItem: {}'.format( e )
            self.warningLog( msg )
            traceback.print_exc( msg )
            raise pdg.CookError( msg )

    # def debugLog(self, message):
    #     if self.logger_object is not None and hasattr( self.logger_object, 'debug' ):
    #         self.logger_object.debug( message )
    #     else:
    #         if self.debug>=10: print( message )

    # def infoLog(self, message):
    #     if self.logger_object is not None and hasattr( self.logger_object, 'info' ):
    #         self.logger_object.info( message )
    #     else:
    #         if self.debug>=5: print( message )

    # def warningLog(self, message):
    #     if self.logger_object is not None and hasattr( self.logger_object, 'warning' ):
    #         self.logger_object.warning( message )
    #     else:
    #         print( message )

    def dynamic_override(self, work_item, parm_name, value, type, set_parm_on_node=None):

        hou_node_path = firehawk_read.get_hou_node_path(work_item)

        # def set_parm(value, hou_node, parm_name):
        #     import hou
        #     parm = hou_node.parm( parm_name )
        #     if parm and value:
        #         parm.set(value)
        #     else:
        #         print "ERROR: parm and or value not defined for parm set with dynamic override. path: {} parm: {} value: {}".format( hou_node.path(), parm_name, value )

        if set_parm_on_node: # optionally update the parm value in the ui.
            hou_node = hou.node(hou_node_path)
            # set_partial_parm_as_value = partial( set_parm, value, hou_node )
            # hdefereval.executeInMainThreadWithResult( set_partial_parm_as_value, parm_name )
            if hou_node:
                parm = hou_node.parm( parm_name )
                if parm:
                    if hasattr( parm, 'unexpandedString') and parm.unexpandedString() != value:
                        # print 'parm.unexpandedString():', parm.unexpandedString()
                        # print 'value', value
                        hdefereval.executeInMainThreadWithResult( parm.set, value )
                        self.timeLog(label= 'Set parm: {} {} value: {}'.format( hou_node_path, parm_name, value ))
                    else:
                        self.timeLog(label='Dynamic versioning: Dynamic override: skip parm: {} already set or no attr unexpanded string'.format( parm_name ))
                    # self.debugLog( 'Set parm: {} {} value: {}'.format( hou_node_path, parm_name, value ) )
                else:
                    self.debugLog( 'Parm doesn\'t exist on: {} wont\'t set parm {} value: {}'.format( hou_node_path, parm_name, value ) )
            else:
                self.debugLog( 'Node doesn\'t exist: {} wont\'t set parm {} value: {}'.format( hou_node_path, parm_name, value ) )

        
        parm_path = hou_node_path+'/'+parm_name
        # By setting the parm name to the path, we have a unique override by full path allowing preservation downstream
        parm_name = parm_path.strip('/').replace('/', '_')

        self.debugLog( '...Add dynamic override for parm: {} at path: {} value: {} work_item.name: {}'.format( parm_name, parm_path, value, work_item.name ) )

        attrib_targets = [ work_item ]
        if hasattr( work_item, 'batchParent' ) and work_item.batchParent: # In a batch, the batch parent python object must have the attributes set on it, as it is the driver of those downstream.  we set attribs on both the work itm and batch parent for good measure.
           attrib_targets.append(work_item.batchParent)
           self.debugLog( 'appending batch parent to set data' )

        self.debugLog( 'on: {} items including batchParent and batchItems'.format( len(attrib_targets) ) )

        if type=='int':
            for item in attrib_targets:
                if houdini_version >= 18.0:
                    item.setIntAttrib(parm_name, value, 0)
                else:
                    if hasattr( item, 'data' ) and hasattr( item.data, 'setInt' ):
                        self.debugLog( 'Set item: {} attrib: {} value: {}'.format( item.name, parm_name, value ) )
                        item.data.setInt(parm_name, value, 0) # in h17.5 batchitems may not be able to have data attached

            self.debugLog('Dynamic versioning: Dynamic override: Checkpoint Int') # inspecting crashes TODO remove this
        elif type=='string':
            for item in attrib_targets:
                if houdini_version >= 18.0:
                    item.setStringAttrib(parm_name, value)
                else:
                    if hasattr( item, 'data' ) and hasattr( item.data, 'setString' ):
                        self.debugLog( 'Set item: {} attrib: {} value: {}'.format( item.name, parm_name, value ) )
                        item.data.setString(parm_name, value, 0) # in h17.5 batchitems may not be able to have data attached
        else:
            self.warningLog( "ERROR: No type specified for dynamic_override" )
            return

        self.debugLog('Dynamic versioning: Dynamic override: Checkpoint string' ) # inspecting crashes TODO remove this

        if 'wedgeattribs' not in work_item.data.stringDataMap:
            self.warningLog( "...wedgeattribs: none: Error is likely if you try to continue adding wedges in a scenario were they never existed prior to scheduling." )
            all_wedge_attribs = []
        else:
            # all_wedge_attribs = work_item.data.stringDataArray('wedgeattribs')
            if houdini_version >= 18.0:
                all_wedge_attribs = work_item.attribArray('wedgeattribs')
                attrib_names = work_item.attribNames()
            else:
                all_wedge_attribs = work_item.data.stringDataArray('wedgeattribs')
                
                attrib_names = []
                if hasattr(work_item, 'data') and hasattr(work_item.data, 'allDataMap'):
                    attrib_names = [x for x in work_item.data.allDataMap]
            
            channel_attribs = [re.sub('\channel$', '', i) for i in attrib_names if i.endswith('channel') ]
            missing_wedge_attribs = [i for i in channel_attribs if ( i not in all_wedge_attribs ) ]
            
            # if self.debug>=11: print 'DEBUG 11:', '...wedgeattribs: found:', all_wedge_attribs
            
            if len(missing_wedge_attribs) > 0:
                self.warningLog( "\nMISSING WEDGE ATTRIBS WERE REPAIRED DUE TO A BUG WHERE WEDGES DURING ON SCHEDULE ARE NOT PRESERVED" )
                self.warningLog( 'missing_wedge_attribs: {}'.format( missing_wedge_attribs ) )

            all_wedge_attribs += missing_wedge_attribs

        self.debugLog('Dynamic versioning: Dynamic override: Checkpoint wedgeattribs') # inspecting crashes TODO remove this

        if parm_name not in all_wedge_attribs:
            all_wedge_attribs.append(parm_name)
        # Specify a parameter override
        # work_item.data.setStringArray('wedgeattribs', sorted(all_wedge_attribs))
        for item in attrib_targets:
            if houdini_version >= 18.0:
                item.setStringAttrib('wedgeattribs', all_wedge_attribs)
            else:
                if hasattr( item, 'data' ) and hasattr( item.data, 'setStringArray' ):
                    item.data.setStringArray('wedgeattribs', all_wedge_attribs)
        
        self.debugLog('Dynamic versioning: wedge attribs passed')
        for item in attrib_targets:
            if houdini_version >= 18.0:
                item.setIntAttrib("{}valuetype".format(parm_name), 1)
                item.setStringAttrib("{}channel".format(parm_name), parm_path)
            else:
                if hasattr( item, 'data' ) and hasattr( item.data, 'setInt' ):
                    item.data.setInt("{}valuetype".format(parm_name), 1, 0)

                if hasattr( item, 'data' ) and hasattr( item.data, 'setString' ): 
                    item.data.setString("{}channel".format(parm_name), parm_path, 0)

        self.debugLog('Dynamic versioning: Dynamic override: Checkpoint') # inspecting crashes TODO remove this
        self.timeLog(label='Dynamic versioning: Dynamic override: Done')
        self.debugLog( '...Completed dynamic override for parm_name: {} at parm_path: {}\n'.format( parm_name, parm_path ) )

    def ensure_dir_exists(self, directory ):
        if not os.path.isdir( directory ):
            ### Need to create dir here
            self.debugLog( "Creating Directory: {}".format( directory ) )
            os.makedirs( directory )
            if not os.path.isdir( directory ): # check that it actually got created
                self.debugLog( "Error creating dir: {}".format( directory ) )
                return

    def get_rop_hou_node_path(self, top_node_path=None, work_item=None):
        if top_node_path is not None:
            rop_hou_node_path = hou.node(top_node_path).parm('roppath').evalAsNode().path()
        elif work_item is not None:
            rop_hou_node_path = work_item.data.stringData('rop', 0)
        return rop_hou_node_path

    # def get_version_db_hou_node_path(self, work_item=None, hou_node_path=None):
    #     if work_item is not None:
    #         hou_node_path = firehawk_read.get_hou_node_path( work_item )
    #     hou_node = hou.node( hou_node_path )

    #     # Optionally the version db can be located on another node to isolate any callbacks that we may not want to trigger.  Do not remove.
    #     # version_db_hou_node_path = hou_node.parent().path() + '/versiondb_' + hou_node.name()

    #     version_db_hou_node_path = hou_node.path()

    #     return version_db_hou_node_path

    def set_output(self, hou_node, work_item=None, output_parm_name=None, set_output=None, validate=False ):
        # The output path parm must be set.  we dont actually have to set the parm in this session, it can be a persistent_override

        self.debugLog('set_output()')
        try:
            if set_output is None:
                self.debugLog('set_output is none. try getLiveParmOrAttribValue for set_output')
                set_output = firehawk_read.getLiveParmOrAttribValue(work_item, 'set_output')
                self.debugLog('set_output: {}'.format( set_output ))
            
            ensured_valid_result = None
            if set_output is not None:
                if output_parm_name is None:
                    self.debugLog('read output_parm_name')
                    output_parm_name = work_item.data.stringData('outputparm', 0)
                
                self.debugLog('output_parm_name: {}'.format( output_parm_name ))
                
                if houdini_version > 18.0 and houdini_minor_version <= 463:
                    print( 'Warning: this version of houdini doesn\'t  correctly handle expressions on parms with wedges' )

                hou_node_path = firehawk_read.get_hou_node_path(work_item)

                self.debugLog( 'hou_node_path: {}'.format( hou_node_path ) )
                ensured_valid_result = self.persistent_override( hou_node_path=hou_node_path, parm_name=output_parm_name, value=set_output, work_item=work_item )
                # self.dynamic_override(work_item, output_parm_name, set_output, 'string', set_parm_on_node=hou_node)
            
            if validate: # validate is disabled for the mplay node, because it is a rop bu has no output.
                if ensured_valid_result:
                    self.debugLog('set_output() Added persistent_override for output_parm_name: {} hou_node_path: {} value: {}'.format( output_parm_name, hou_node_path, set_output) )
                else:
                    self.debugLog('Warning: ensured_valid_result: {} Not adding persistent_override for output_parm_name: {} hou_node_path: {}'.format( ensured_valid_result, output_parm_name, hou_node_path ) )

        except ( Exception ), e :
            import traceback
            self.warningLog( 'ERROR: During set_output: hou_node: {} work_item: {} output_parm_name: {} set_output: {}'.format( hou_node, work_item, output_parm_name, set_output) )
            traceback.print_exc(e)
            raise e

    # def get_output(self, hou_node, work_item=None, set_output=None, output_parm_name=None):
    #     # The output path parm must be set.
    #     if set_output is None: set_output = firehawk_read.getLiveParmOrAttribValue(work_item, 'set_output')
    #     if set_output:
    #         if output_parm_name is None: output_parm_name = work_item.data.stringData('outputparm', 0)
    #         unexpanded_string = hou_node.parm(output_parm_name).unexpandedString()
    #         return unexpanded_string
    #     else:
    #         return None


    def persistent_override( self, hou_node_path=None, parm_name=None, value=None, existence_check=True, work_item=None): # used to set permanent values on parms.  Not recommended for parms that vary per wedge, use the wedge workflow for this.
        ensured_valid_result = False
        self.debugLog( 'Persistent override for: {} parm: {}'.format( hou_node_path, parm_name) )
        hou_node = hou.node( hou_node_path ) # These are used for validation but could be removed if needed
        if hou_node is None:
            self.warningLog( 'Error: Cannot add persistent override. No hou_node from: {}'.format( hou_node_path ) )
            return ensured_valid_result

        if existence_check and hou_node.parm( parm_name ) is None:
            self.warningLog( 'Error: Cannot add persistent override. No parm {} from: {}'.format( parm_name, hou_node_path ) )
            return ensured_valid_result

        sidecar_file_path = versions_object.get_sidecar_json_file_path() # update sidecar file.  the side car file allows a graph running to update versions and parms, to be later loaded for running work items, or if the hip file submitted is later loaded.
        
        if sidecar_file_path is None:
            raise Exception('ERROR: No sidecar file path resolved to persist overrides.')

        self.debugLog( 'sidecar_file_path: {}'.format(sidecar_file_path) )
        json_object = versions_object.get_sidecar_json_object()

        if hou_node.path() not in json_object: json_object[ hou_node.path() ] = {} # init the second level dict.
        
        if 'parm_'+parm_name not in json_object[ hou_node.path() ] or json_object[ hou_node.path() ][ 'parm_'+parm_name ] != value:
            # update the file only if data not already equal.
            
            json_object[ hou_node.path() ][ 'parm_'+parm_name ] = value

            if work_item is not None: # to resolve __PDG_DIR__ in the current session, we need to record the local working dir when it was scheduled.
                workingdir_local = work_item.node.scheduler.workingDir(True)
                if 'workingdir_local' not in json_object[ hou_node.path() ] and workingdir_local:
                    json_object[ hou_node.path() ][ 'workingdir_local' ] = workingdir_local

            with file( sidecar_file_path , 'w' ) as sidecar_file:
                json.dump( json_object, sidecar_file ) # TODO ensure this is an atomic operation / reading will not fail during write. NFS should cover this though anyway and older submissions should only be updating data that is not currently relevent as it applies downstream.
                self.debugLog( 'sidecar_file wrote: {} {}'.format( sidecar_file_path, json_object ) )
            ensured_valid_result = True
        else:
            ensured_valid_result = True

        return ensured_valid_result

    def onScheduleVersioning(self, work_item, pdg_dir):
        # This should only be called within the scheduler.
        ### version tracking: write version attr before json file is created.
        # requires hou
        # ensure this is located just before self.createJobDirsAndSerializeWorkItems(work_item)
        # also ensure the current index_key string exists as a top attribute, uniquely identifying wedges / distinct outputs, not versions
        try:
            self.debugLog( "onScheduleVersioning start workitem: {}".format( work_item ) )
            if work_item:
                self.debugLog( "set int version" )
                hip_path = work_item.data.stringData('hip', 0)

                self.debugLog( "Initial hip_path: {}".format( hip_path ) )

                hip_path = os.path.split(hip_path)[1]
                self.debugLog( "hip_path split: {}".format( hip_path ) )

                index_key = firehawk_read.getLiveParmOrAttribValue(work_item, 'index_key') # should be unexpanded string.

                if firehawk_read.get_is_exempt_from_hou_node_path(work_item) == False: # Trackers dont have hou nodes.
                    ### Set data on the node db multiparm, uses hou.
                    hou_node_path = firehawk_read.get_hou_node_path(work_item)
                    hou_node = hou.node(hou_node_path)

                    version_db_hou_node_path = firehawk_read.get_version_db_hou_node_path(work_item=work_item)
                    version_db_hou_node = hou.node( version_db_hou_node_path ) # This may be the same as the hou node in the future, but can be isolated to eliminate callbacks being triggered if it is a serperate node.  Better until stability is assured.
                    if version_db_hou_node is None:
                        self.warningLog( 'ERROR: invalid path for version_db_hou_node: {}'.format(version_db_hou_node_path) )
                        return None
                    
                    if not hou_node:
                        self.warningLog( "ERROR: invalid path for hou_node" )
                        return None

                    self.persistent_override( hou_node_path=hou_node_path, parm_name='version_db_index_key', value=index_key, existence_check=False ) # when the version db is added to the node, ensure it has an unexpaded index key expression on it.

                with work_item.makeActive():
                    index_key = hou.expandString( index_key )
                
                work_item.setStringAttrib('index_key', str(index_key) ) # in distributed sims, the attribute for the index key may have updated on the rop fetch, so we need to update it
                self.debugLog( "onScheduleVersioning() index_key: {}".format( index_key ) )

                multiparm_index = None # This is not used unless multiparms are being updated
                json_object = None

                requires_version_db, uses_version_db = False, False
                if firehawk_read.get_is_exempt_from_hou_node_path(work_item) == False: # If the work item is not a tracker, it probably requires a version db parm on the hou node.
                    requires_version_db = True
                    self.debugLog( "Node required versiondb" )
                    self.debugLog( "onScheduleVersioning() validate test uses_version_db" )
                    uses_version_db = versions_object.uses_version_db( hou_node )
                    self.debugLog( "onScheduleVersioning() uses_version_db: {}".format( uses_version_db ) )

                if requires_version_db and not uses_version_db:
                    self.warningLog( "\n### Skipping versioning ### since uses_version_db: {} hou_node: {}".format( uses_version_db, hou_node.path() ) )
                    self.warningLog( "  If you are trying to submit a new node type, ensure the node type is available in method uses_version_db()..." )
                else:
                    aquired_version = None

                    if uses_version_db:
                        self.debugLog( "\n### Applying versioning ### output_type: {}".format( [ x for x in versions_object.output_types if x == hou_node.type().name() ] ) )

                        # The output path parm must be set. ensure bug #105119 is addressed
                        self.set_output(hou_node, work_item=work_item) # Testing relocating this only if ver db is used.

                    dict_init = {
                        'index_key': {'var_data_type': 'string' },
                        'index_key_unexpanded': {'var_data_type': 'string' },
                        'index_key_expanded': {'var_data_type': 'string' },
                        'seq': {'var_data_type': 'string' },
                        'shot': {'var_data_type': 'string' },
                        'element': {'var_data_type': 'string' },
                        'variant': {'var_data_type': 'string' },
                        'version': {'var_data_type': 'int' },
                        'hip': {'var_data_type': 'string' }
                    }
                    parm_dict = {}
                    for k,v in dict_init.iteritems():
                        v['update_db'] = True
                        v['name'] = k
                        v['attribute'] = k
                        v['value'] = firehawk_read.getLiveParmOrAttribValue(work_item, v['attribute'], type=v['var_data_type'])
                        parm_dict[k] = v

                    # Some items will have work_items.isNoGenerate = true (eg: the distributed sim tracker).  These are special, since they are orphans and have not children. if we dont ensure that index key and work item index is unique, there may be job name conflicts.

                    dict_update = submission_attributes

                    for k,v in dict_update.iteritems():
                        v['update_db'] = None
                        v['name'] = None
                        v['attribute'] = k
                        v['value'] = firehawk_read.getLiveParmOrAttribValue(work_item, v['attribute'], type=v['var_data_type'])
                        parm_dict[k] = v

                    if firehawk_read.get_is_exempt_from_hou_node_path(work_item):
                        work_item.setStringAttrib('element', str(work_item.name) )
                        parm_dict['element']['value'] = str(work_item.name)
                        work_item.setStringAttrib('variant', str(int(work_item.index)) )
                        parm_dict['variant']['value'] = str(int(work_item.index))
                        parm_dict['format']['value'] = 'py' # wild assumption here, will have to correct it if we are proven wrong!
                        parm_dict['asset_type']['value'] = 'script'
                    
                    self.debugLog( 'parm_dict: {}'.format(parm_dict) )

                    def sort_func(x): # ensure version is last in the dictionary.  other values will determine the generated version, so it cannot be known until last.
                        value = int( x[0] == 'version' )
                        return value
                    
                    self.ord_dict = collections.OrderedDict( sorted(parm_dict.items(), key=lambda x: sort_func(x) ) )

                    if uses_version_db:
                        self.timeLog(label='Dynamic versioning: Prepare dictionary')
                        for key, value in self.ord_dict.items():
                            update_db = value['update_db']
                            if update_db is None or update_db is False: # some data on the dict may not need to be written to the db.
                                continue
                            var_data_type = value['var_data_type']
                            name = value['name']
                            attribute = value['attribute']
                            value = value['value']

                            if 'version' == attribute: # version is special, since its dynamically aquired, and potentially based on the output path defined by the other attributes.  It cannot be known until the point where it is scheduled here, and it must be the last variable to be evaluated. isNoGenerate is used so some special work items, like trackers, that may not need assets.  trackers skip the asset creation process, but the ord_dict object might still be needed for a scheduler to handle things like custom command formatting.

                                # It is difficult to know if a new asset version should be requested.  This code is hard to handle in a simple way. look to asset_created = logic at the bottom to get this idea...  We must consider if it has already been done for the relevent set of workitems in the output, we must also consider if we are resuming a cook and an aset was made in the last cook.
                                self.timeLog(label='Dynamic versioning: Prepare eval if version required')
                                auto_version = firehawk_read.getLiveParmOrAttribValue(work_item, 'auto_version', type='string')
                                self.timeLog(label='Dynamic versioning: Get Auto version setting')
                                self.debugLog( '...auto_version is set to: {}'.format( auto_version ) )
                                node_work_items = work_item.node.workItems
                                asset_created_states = [ pdg.workItemState.CookedSuccess, pdg.workItemState.CookedCache, pdg.workItemState.Cooking, pdg.workItemState.CookedFail, pdg.workItemState.Dirty ] # Any of these states indicate an asset must have already been created.  CookedFail is a little special in that we might not know, but we have to handle it as if the asset was created otherwise we might keep requesting new assets to be created.
                                scheduled_states = [ pdg.workItemState.Scheduled, pdg.workItemState.Waiting, pdg.workItemState.Uncooked ]
                                all_considered_states = asset_created_states + scheduled_states
                                
                                work_item_indexes = [ x.batchParent if x.batchParent else x for x in node_work_items ] # qualify if we should be using the batch parent instead for each work item
                                valid_work_items = [ x for x in work_item_indexes if index_key == x.data.stringData('index_key', 0) ] # consider the list of work items / wedges that match this submission.  filter remove workitems that don't share the index key,
                                # valid_work_items = [ x for x in node_work_items if index_key == firehawk_read.getLiveParmOrAttribValue(x, 'index_key') ] # This could be faster if precomputed the index key.

                                self.timeLog(label='Dynamic versioning: Valid work items for index_key: {}'.format(index_key))
                                current_states = [ x.state for x in valid_work_items ] #
                                self.timeLog(label='Dynamic versioning: Current states')
                                self.debugLog( "current_states: {}".format(current_states) )
                                work_items_with_assets = [ ( x in asset_created_states ) for x in current_states ] # if any work items match these states, they must already have assets.
                                self.timeLog(label='Dynamic versioning: Work items with assets')
                                all_items_are_just_scheduled = all( [ ( x in scheduled_states ) for x in current_states ] ) # true if all items are scheduled

                                items_with_unqualified_states = [ x for x in current_states if x not in all_considered_states ] # if any items have states that are new or not matching those considered, we should warn, because this validation logic may fail.
                                if len(items_with_unqualified_states):
                                    raise pdg.CookError('Some items have states that are not yet qualified correctly to determine if a new version is needed: {}'.format(current_states))

                                get_unique = [ x.batchParent if x.batchParent is not None else x for x in valid_work_items ] # this might be duplicate logic
                                valid_submitted_batches = []
                                for x in get_unique: # need to accelerate this.
                                    if x not in valid_submitted_batches: valid_submitted_batches.append(x)

                                # valid_submitted_batches = set( [ x.batchParent if x.batchParent else x for x in valid_work_items ] ) # submitted items will be batch parents if more than 1 item per batch.
                                self.timeLog(label='Dynamic versioning: Valid submitted batches')
                                self.debugLog( "valid_submitted_batches: {}".format( valid_submitted_batches ) )
                                work_items_with_new_assets_in_this_submission = [ ( 'onScheduleVersioned' in x.data.allDataMap and int( x.data.allDataMap['onScheduleVersioned'][0] ) ) for x in valid_submitted_batches ] # TODO this logic could be simplified in h18
                                self.timeLog(label='Dynamic versioning: Work items with assets in this submission: {}'.format( len(work_items_with_new_assets_in_this_submission) ))
                                self.debugLog( 'work_items_with_new_assets_in_this_submission: {}'.format( len(work_items_with_new_assets_in_this_submission) ) )
                                at_least_one_item_has_an_asset_already = any( work_items_with_new_assets_in_this_submission )
                                self.timeLog(label='Dynamic versioning: At least one item has an asset: {}'.format(at_least_one_item_has_an_asset_already))

                                # This logic allows us to finalise submission of work items that have had scripts cached, but no job id given yet.  It allows us to submit many items as a frame range to reduce server requests.
                                spooled_items = [ x for x in valid_submitted_batches if ( 'spooled' in x.data.allDataMap and x.data.intData('spooled', 0) == 1 ) ] # spooled items are items that will be aquiring a job id in a submission
                                scheduled_items = [ x for x in valid_submitted_batches if ( x.state == pdg.workItemState.Scheduled and x not in spooled_items ) ]
                                # items that have onScheduleVersioned attrib have been scheduled
                                submitted_items_that_can_be = [ ( 'onScheduleVersioned' in x.data.allDataMap and int( x.data.allDataMap['onScheduleVersioned'][0] ) ) for x in scheduled_items ]

                                if sum(submitted_items_that_can_be) == ( len(submitted_items_that_can_be)-1 ) or len(submitted_items_that_can_be) == 0:
                                    self.debugLog( 'submit_to_scheduler: This item is the last one detected to not have been scheduled. If using a frame list to submit a batch, that list is ready to be submitted' )
                                    self.debugLog( 'submit_to_scheduler: submitted_items_that_can_be: {}'.format( submitted_items_that_can_be ) )
                                    work_item.data.setInt('submit_to_scheduler', 1, 0)
                                    submit_frames = [ str( int(x.frame) ) for x in scheduled_items]
                                    submit_work_items = [ str( x.name ) for x in scheduled_items]
                                    submit_frames_str = ','.join( submit_frames )
                                    self.debugLog( 'submit_to_scheduler: {}'.format(submit_frames_str) )
                                    work_item.data.setString( 'submit_frames_str', submit_frames_str, 0 ) # deprecate this in h18 in favour of python objects
                                    work_item.data.setStringArray( 'submit_work_items', submit_work_items )
                                    
                                    for x in scheduled_items: # Dont submit things twice!
                                        x.data.setInt('spooled', 1, 0)
                                else:
                                    self.debugLog( 'submit_to_scheduler: Skipping, There are still items that can be added to the list: {}'.format( submitted_items_that_can_be ) )
                                    work_item.data.setInt('submit_to_scheduler', 0, 0)

                                update_item = work_item
                                # if work_item.batchParent is not None: update_item = work_item.batchParent

                                update_item.setStringAttrib('state_during_scheduling', str(update_item.state) )
                                update_item.setStringAttrib('current_states', [ str(x) for x in current_states ])
                                update_item.setFloatAttrib('create_asset', [0,0,0]) # visualise if an asset was created. TODO remove this
                                if True in work_items_with_assets:
                                    self.debugLog( 'asset_already_created: True, a work item was found that has already had a new asset created, so another new asset will not be created.' )
                                    asset_already_created = True
                                elif all_items_are_just_scheduled and at_least_one_item_has_an_asset_already: #  if every single state is workItemState.Scheduled, you can't know that an asset has been created yet, because the first work item wont have one,
                                    self.debugLog( 'asset_already_created: True, All work items are in a scheduled state, and one item was found to have an asset created on this run. A new asset will not be created.' )
                                    asset_already_created = True
                                elif False in work_items_with_assets: # otherwise at least one item must be false, and in this instance a new asset must be created.
                                    self.debugLog( 'asset_already_created: False, A new asset must be created since no work items have assets yet. work_items_with_assets: {}'.format( work_items_with_assets ) )
                                    self.debugLog( '\n   current_states: {}\n'.format(current_states) )
                                    asset_already_created = False
                                    update_item.setFloatAttrib('create_asset', [0,0,1])
                                else: 
                                    # self.warningLog( "ERROR: no work items in list to evaluate if assets exists or not. current_states: {}".format( current_states ) )
                                    msg = "ERROR: no work items in list to evaluate if assets exists or not. index_key: {} current_states: {}".format( index_key, current_states )
                                    self.debugLog( msg )
                                    raise pdg.CookError( msg )
                                    return None

                                self.timeLog(label='Dynamic versioning: Completed eval version required')

                                # print 'Check if asset_already_created is on for path: {} index_key: {}'.format( hou_node.path(), index_key ),
                                self.debugLog( 'asset_already_created: {}'.format( asset_already_created ) )
                                
                                if asset_already_created: # use existing version.
                                    self.debugLog( 'Asset is created for this run.' )
                                    if update_method == 'parms':
                                        # version = hou_node.parm('version_' + str(multiparm_index)).eval()
                                        with work_item.makeActive():
                                            version = str( hou_node.parm('version').eval() )
                                    else: # we must be using user data.

                                        json_object = versions_object.get_sidecar_json_object()
                                        if (json_object is None) or (version_db_hou_node_path not in json_object) or ('version_'+index_key not in json_object[ version_db_hou_node_path ]):
                                            with work_item.makeActive():
                                                version = str( hou_node.parm('version').eval() ) # in some circumstances, like resubmission due to an error of only some work items, the asset will have been created, but the json_object will not have been updated with the version, since every submission starts with a new json_object.  We will fall back to using the resolved version for the parm, assuming the last submitted versions were automatically pulled into the session.
                                        else:
                                            version = json_object[ version_db_hou_node_path ][ 'version_'+index_key ]

                                        # version = version_db_hou_node.userData('version_'+index_key) # deprecated.  dont write user data mid job.
                                        if version is not None and version.isdigit():
                                            version = int( version )
                                        else:
                                            self.warningLog( 'ERROR: Tried to inherit the version for an existing asset but failed because it was missing from json_object or user data at: {}'.format(version_db_hou_node_path) )
                                            return None
                                    self.debugLog( 'version: {}'.format( version ) )
                                else: # new version
                                    self.debugLog( "Create New Version.  auto_version set to: {}".format( auto_version ) )
                                    if 'disabled' == auto_version:
                                        version = firehawk_read.getLiveParmOrAttribValue(work_item, attribute, type=var_data_type)
                                    if 'increment' == auto_version:
                                        version = -1 # when set to -1, the asset function will increment the version
                                    if 'from_scene' == auto_version:
                                        # import hou
                                        submission_hip_name = hou.hipFile.name()
                                        # submission_hip_name = hip_path
                                        version = self.get_major_version_from_name(submission_hip_name) # if specified, then new assets will inherit the hip version
                                    self.debugLog( "Set dictionary version: {}".format( version ) )
                                self.ord_dict['version'] =  { 'update_db': None, 'name': None, 'attribute': 'version', 'var_data_type': 'int', 'value': version } # update dictionary
                                if self.debug>=11: self.debugLog( 'self.ord_dict: {}'.format(self.ord_dict) )

                                if self.ord_dict['asset_type']['value'] == 'rendering': # prepare res overrides
                                    self.debugLog( 'asset_type rendering' )
                                    if hou_node.type().name()=='arnold':
                                        resolutionx = self.ord_dict['res']['value'].split('_')[0]
                                        resolutiony = self.ord_dict['res']['value'].split('_')[1]
                                        self.debugLog( 'set resoltuion for arnold at node: {} x{} y{}'.format( hou_node_path, resolutionx, resolutiony ) )
                                        self.persistent_override( hou_node_path=hou_node_path, parm_name='res_overridex', value=resolutionx )
                                        self.persistent_override( hou_node_path=hou_node_path, parm_name='res_overridey', value=resolutiony )                        
                                
                                self.debugLog( "Define tags" )
                                keys_from_ord_dict = [ 'job', 'seq', 'shot', 'element', 'animating_frames', 'asset_type', 'format', 'volatile', 'res', 'variant', 'version', 'hip', 'index_key_unexpanded', 'index_key_expanded', 'index_key' ]
                                tags = { 'pdg_dir': pdg_dir } # Init tags.  PDG_DIR may be required for asset creation
                                
                                for key in keys_from_ord_dict: # the final tags that will be passed to the asset creation module
                                    dict_value = self.ord_dict[key]['value']
                                    self.debugLog('   {} : {}'.format( key, dict_value ) )
                                    tags[key] = dict_value

                                if asset_already_created: # if the asset already exists, we just get the path.
                                    tags['create_asset'] = False
                                    self.debugLog( 'Existing version with tags:' )
                                    if self.ord_dict['version']['value'] == -1:
                                        self.warningLog( 'Error: canot use existing version -1' )
                                        return None
                                else:
                                    tags['create_asset'] = True
                                    tags['range'] = work_item.attribArray('range') # range is different to standard attribs, it should always be pulled from the work item.
                                    # If an asset is to be created we can attach other data required for the asset.

                                ##### TODO Improve logging of create asset reasons here.

                                self.timeLog(label='Dynamic versioning: Prepare tags for asset')
                                
                                tags['use_inputs_as'] = 'tags'

                                asset_creator = firehawk_asset_handler.asset( debug=self.debug, logger_object=None, start_time=self.start_time ) # An instance of the asset handler with passed through logging.

                                if tags['asset_type'] == 'renderarchive': # When render archives are created, ensure other output paths are created too.  exrs are the primary driver of the version on disk, so take this step first.
                                    exr_tags = tags.copy()

                                    exr_tags['asset_type'] = 'rendering'
                                    exr_tags['format'] = 'exr'

                                    self.debugLog( 'Create version with tags (exr):' )
                                    self.debugLog( exr_tags )
                                    
                                    exr_asset_path, exr_version = asset_creator.custom_create_new_asset_version( exr_tags, show_times=True )
                                    # ensure the archive version used will be the same.
                                    tags['version'] = exr_version

                                create_asset.rebuild_tags(tags) # before submission, this hook allows updating of tags to meet custom requirements using a plugin.

                                self.debugLog( 'Create version with tags:' )
                                self.debugLog( tags )
                                asset_path, version = asset_creator.custom_create_new_asset_version( tags, show_times=True ) # this function defines how to create a new asset.  all other vars required to create a new asset must exist prior to this point
                                
                                self.timeLog(label='Dynamic versioning: Ensure Asset exists')
                                self.ord_dict['version']['value'] = version # update dictionary
                                self.ord_dict['version_str'] = { 'value': 'v' + str(version).zfill(3) } # initialise a string for the version for convenience

                                value = version
                                aquired_version = version # aquired_version shoudl always exist, whether it is inherited or auto increments.

                                ## We update expected result data - the path has changed since the item was generated.

                                self.debugLog( 'work_item.name: {}'.format( work_item.name ) )
                                self.timeLog(label='Dynamic versioning: Updated result Data')

                            if value is not None:
                                self.dynamic_override(work_item, name.strip('_'), value, var_data_type) # dynamic overides are stored as json data, loaded by the process executing the workitem.  this only sets the parms used directly by the file path refs (not the db)

                                if update_method == 'parms': # This uses multiparms to store versions, but calling hou to do this is unreliable (can cause hangs)
                                    multiparm_name = '{}_{}'.format( name, str(multiparm_index) )
                                    self.debugLog( "Setting dynamic override and value on multiparm: {} {}".format( multiparm_name, value ) )
                                    self.timeLog( label='Dynamic versioning: Prepare to set Multiparm: {}'.format( multiparm_name ) )
                                    parm = hou_node.parm( multiparm_name )
                                    
                                    if parm.eval() != value:
                                        hdefereval.executeInMainThreadWithResult( parm.set, value ) # values in the db multiparm (UI) are updated for the index_key.    
                                else: # update the version in the dedicated user data node.
                                    if aquired_version is not None:
                                        # this may be unsafe.
                                        # self.debugLog( 'Set user data for version if not already equal at path: {} key: {} to value: {}'.format( version_db_hou_node.path(), 'version_'+index_key, aquired_version ) )
                                        # if 'version_'+index_key in version_db_hou_node.userDataDict() and version_db_hou_node.userData( 'version_'+index_key ) == str( aquired_version ):
                                        #     self.debugLog( 'Version user data: skipping set version_{} to value: {}'.format( index_key, aquired_version ) )
                                        # else:
                                        #     # the current hip file running the graph should have the versions updated as well.
                                        #     self.debugLog( 'Version user data: set version_{} to value: {}'.format( index_key, aquired_version ) )
                                        #     hdefereval.executeInMainThreadWithResult( version_db_hou_node.setUserData, 'version_'+index_key, str(aquired_version) )

                                        # update sidecar file.  the side car file allows a graph running to update versions, to be later loaded by any multiparm for running work items, or if the hip file submitted is later loaded.
                                        # sidecar_file_path = versions_object.get_sidecar_json_file_path()

                                        # self.debugLog( 'sidecar_file_path: {}'.format(sidecar_file_path) )
                                        json_object = versions_object.get_sidecar_json_object()

                                        if version_db_hou_node.path() not in json_object: json_object[ version_db_hou_node.path() ] = {} # init the second level dict.
                                        
                                        if 'version_'+index_key not in json_object[ version_db_hou_node.path() ] or json_object[ version_db_hou_node.path() ][ 'version_'+index_key ] != str(aquired_version):
                                            # update the file only if data not present ot not already equal.
                                            json_object[ version_db_hou_node.path() ][ 'version_'+index_key ] = str(aquired_version)


                                    ### WARNING ### These functions may need to be decoupled if there are stability issues.
                                    # self.update_multiparm(hou_node_path, index_key, version=aquired_version) 

                                self.timeLog(label='Dynamic versioning: Update version if defined')
                            elif attribute not in []: # attributes not in the exeption list will raise an error
                                self.warningLog( "ERROR: Couldn't get value for attribute: {}".format( attribute ) )
                                return None

                                #### continue from here - get all attribs and set them on the node.  also need to head upstream and set them on the override

                        if aquired_version is None:
                            self.warningLog( "ERROR: Didn't set the version on the multiparm" )
                            return None


                        work_item.data.setInt('version', version, 0) # the version attrib is valid only for this work item at the current stage of submission.  It should not be referenced anywhere except for submission purposes.
                
                work_item.data.setInt('onScheduleVersioned', 1, 0) # track that this work item has been versioned and ready for submission.
                
                self.timeLog(label='Dynamic versioning: Set version attrib')

                # save the current json object with the batch parent, always.
                
                if json_object is None:
                    json_object_was_changed = False
                    json_object = versions_object.get_sidecar_json_object() # we may already have a json object if we are the first batch for the version.  otherwise, other batches wont have new assets, and we should load the side car file to attach it as an attribute.
                else:
                    json_object_was_changed = True
                
                    with file( versions_object.get_sidecar_json_file_path() , 'w' ) as versiondb_file:
                        json.dump( json_object, versiondb_file ) # Don't read this file from work items. it is for the current hip file only to read in event of a crash.  it represents the versions state for this hip file.
                        self.debugLog( 'versiondb_file wrote: {}'.format( json_object ) )

                
                set_on_item = work_item
                if work_item.batchParent is not None: set_on_item = work_item.batchParent
                # Stash version data on work items
                set_on_item.setPyObjectAttrib('versiondb', json_object) # TODO this attrib can be used by the work items.  need to ensure other work items with different batch parents in the same submission can also read this.
                work_item.setAttribFlag("versiondb", pdg.attribFlag.NoCopy, True) # don't let this propogate downstream, it will make debugging confusing.
                # Stash version data on disk.  Do not read from this on farm.  Although data may not have changed, we always ensure this file is written for a user to recover the versions used in the last submission.
                # versiondb_file = open( versions_object.get_sidecar_json_file_path() , 'w')

                

                # This next op optionally updates the current hip with all versions.  Hip state should not be relied upon, since pdg pilot submission cannot set it: we shouldn't set parms for a submission to work, we we can do it as a post operation.
                # This operation has also caused problems with freezing historically.  If in doubt, turn it off.
                autoupdate = work_item.attribValue('autoupdate')
                if autoupdate is not None and int( autoupdate ) and not self.disable_update_versions:
                    if json_object_was_changed:
                        self.debugLog( "pull_all_versions_to_all_multiparms()" )
                        versions_object.pull_all_versions_to_all_multiparms( check_hip_matches_submit=False, exec_in_main_thread=True, work_item=set_on_item, use_json_file=False ) # If hanging occurs, consider disabling this.  setting parms and making changes in the main thread has been known to cause freezes.  Produciton safe workflows should not depend on this operation, it is done for convenience.

                self.debugLog( "### end multiversion db block ###" )
                
                # return the output path for the work item
                if uses_version_db:
                    return version
                else:
                    return # trackers / isNoGenerate items dont have versions.
                # ### end dynamic version db ###
        except ( Exception, hou.Error ), e :
            import traceback
            print( 'Exception: {}'.format(e) )
            traceback.print_exc(e)
            raise e