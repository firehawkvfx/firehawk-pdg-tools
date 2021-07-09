# A light weight library for multithreaded processes.  Multithreaded ops like the custom cache handlers benefit loading these libraries rapidly.

import sys, os
import re
import hou, pdg
import time

parmprefix='firehawk_read'
spacer=''
debug=0
silent_errors=False

version_prefix='version_'
def get_version_prefix():
    return version_prefix

def _verboseLog(args): # This is taken from scheduler.py
    _verbose=True
    if _verbose:
        print('{}: {}: {}{}'.format( time.strftime('%H:%M:%S', time.localtime()), parmprefix, spacer, args))
        sys.stdout.flush()

def debugLog(message, debug=debug):
    if debug>=10: _verboseLog( message )

def warningLog(message, debug=debug):
    if debug>=10: _verboseLog( message )

def get_is_exempt_from_hou_node_path(work_item):
    exempt = False
    if work_item.isNoGenerate == True:
        print('\nExempt: isNoGenerate')
        exempt = True
    if work_item.node.topNode().type().name() in [ 'pythonscript' ]:
        print('\nExempt: pythonscript')
        exempt = True
    if exempt: print('No hou node because the work item exempt from this requirement\n')
    return exempt
    
def get_hou_node_path(work_item, debug=debug):
    if get_is_exempt_from_hou_node_path(work_item):
        return
    hou_node_path = None
    work_item_node_type_name = work_item.node.topNode().type().name()
    accepted_list = [ 'ropfetch', 'houdiniserver' ]
    if work_item_node_type_name not in accepted_list: # Currently, a hou node path and versioning applies to nodes being cooked by nodes in this list. We should detect if that is not the case, since the attributes do not use the NoCopy limited scope, and can polute the network downstream.
        print('No hou node because the work item is not from {}.  work_item_node_type_name: {}'.format( accepted_list, work_item_node_type_name ) )
        return
    
    if work_item_node_type_name == 'houdiniserver':
        hou_node_path = work_item.node.topNode().path()

    if work_item_node_type_name == 'ropfetch':
        rop_path = work_item.data.stringData('rop', 0)
        top_path = work_item.data.stringData('top', 0)
        if top_path is not None and len(top_path) and top_path in rop_path: # and hou.node(top_path): # calls to hou may be unstable.
            hou_node_path = top_path # If the rop is nested inside the top, apply versioning to the top node itself.
        else:
            hou_node_path = rop_path # else, apply versioning to the target, eg: rop geometry in sops.
    
    debugLog('done: {}'.format(hou_node_path), debug=debug)
    return hou_node_path

def get_version_str(version_int):
    version_str = 'v'+str( version_int ).zfill(3)
    return version_str

def get_output(hou_node, work_item=None, set_output=None, output_parm_name=None, debug=debug):
    # The output path parm must be set.
    result = None
    if set_output is None: set_output = getLiveParmOrAttribValue(work_item, 'set_output', debug=debug)
    if set_output:
        debugLog('...get string data', debug=debug)
        if output_parm_name is None: 
            
            output_parm_name = work_item.data.stringData('outputparm', 0)
            debugLog('...get string data done', debug=debug)
        result = hou_node.parm(output_parm_name).unexpandedString()
        debugLog('...get unexpanded string data done', debug=debug)
        if len(result)==0: result = None

    return result

def resolve_pdg_vars(path, work_item=None, node_path=None):
    
    if '__PDG_DIR__' in path:
        print( '__PDG_DIR__ in: {}'.format( path ) )
        pdg_dir = None

        if work_item is None and node_path is None:
            raise Exception('resolve_pdg_vars: requires either work_item or node_path')
        
        # if work_item is not None and hasattr(work_item, 'environment') and 'PDG_DIR' in work_item.environment:
        #     pdg_dir = work_item.environment['PDG_DIR']
        if 'PDG_DIR' in os.environ:
            pdg_dir = os.environ['PDG_DIR']
        elif work_item is not None:
            import pdg
            pdg_dir = work_item.node.scheduler.workingDir(True)
        elif node_path is not None:
            import hou
            pdg_dir = hou.node(node_path).userData( 'workingdir_local' )
        # elif 'workingdir_local' in user_data_dict: # we can resolve the working dir for the local session as well.
        #     pdg_dir = user_data_dict['workingdir_local']
        
        print( 'PDG_DIR: {}'.format(pdg_dir) )

        if pdg_dir is not None:
            path = path.replace( '__PDG_DIR__', pdg_dir )
            print( 'result path: {}'.format( path ) )
        else:
            print('WARNING: No PDG_DIR found')
    return path

def get_output_index_key_expr(hou_node, debug=debug):
    version_db_hou_node_path = get_version_db_hou_node_path( hou_node_path=hou_node.path() ) # the version db may not reside on the output node.
    index_key_parm=hou.node(version_db_hou_node_path).parm('version_db_index_key')
    result = None
    if index_key_parm: # the index key parm may not exist on the node at first use
        result = index_key_parm.unexpandedString()
        if len(result)==0: result = None
    return result

def getLiveParmOrAttribValue(work_item, attrib_name, type='string', use_batch_parent=True, top_node_path=None, spacer='', debug=debug): # this function will aquire a parameter on the the node for a work item, a python overide dict, or an attribute, whichever is found first.  this allows parms and dicts to override attributes.
    try:
        if use_batch_parent and hasattr( work_item, 'batchParent' ) and work_item.batchParent is not None:
            work_item = work_item.batchParent

        debugLog( '...getLiveParmOrAttribValue: "{}" on node: {}'.format( attrib_name, work_item.node ), debug=debug )
        spacer = '   '

        def eval_parm_on_node(parm_name, pdg_node, work_item_id, top_node_path):
            debugLog('eval parm on node parm_name: {}, pdg_node: {}, work_item_id: {}, top_node_path: {}'.format( parm_name, pdg_node, work_item_id, top_node_path ) , debug=debug )
            context = pdg_node.context
            work_item = context.graph.workItemById( int(work_item_id) )
            result=None
            # result defaults to input result or none.
            if parm_name in pdg_node.parameterNames:
                # Parameters take precedence over pdg attributes because it can be unique for any pdg node with less conflicts.
                enabled = True # if a matching parameter name is found on the top fetch node, then it will be used.  if if a toggle exists, the value of the toggle will be used to determine if the parm has precedence over an attribute.
                if parm_name+'_enabled' in pdg_node.parameterNames:
                    with work_item.makeActive():
                        enabled = int( pdg_node.parameter( parm_name+'_enabled' ).evaluateInt() )
                if enabled:
                    if type == 'string':
                        debugLog( 'Parm String pdg_node: {} parm_name: {} work_item: {} \nResult:'.format( pdg_node.topNode().path(), parm_name, work_item ) , debug=debug )
                        with work_item.makeActive():
                            result = str( pdg_node.parameter(parm_name).evaluateString() )
                        debugLog( result , debug=debug )
                    elif type == 'float':
                        debugLog( 'Parm Float Result:' )
                        with work_item.makeActive():
                            result = int( pdg_node.parameter(parm_name).evaluateFloat() )
                        debugLog( result , debug=debug )
                    elif type == 'array':
                        debugLog( 'Parm Array Result:' , debug=debug )
                        with work_item.makeActive():
                            result = str( pdg_node.parameter(parm_name).evaluateFloat() )
                        debugLog( result , debug=debug )
                    else:
                        debugLog( 'Parm Int Result:' , debug=debug )
                        with work_item.makeActive():
                            result = int( pdg_node.parameter(parm_name).evaluateInt() )
                        debugLog( result , debug=debug )
                else:
                    debugLog( 'Not evaluating custom parm. Disabled', debug=debug )
            debugLog( 'result: {}'.format(result) , debug=debug )
            # else:
                # self.warningLog( 'Warning: parm_name: {} not in pdg_node: {} parameterNames: {}'.format( parm_name, top_node_path, pdg_node.parameterNames ) )
            return result
        
        # Get overrides dictionary for python ref to upstream overrides if no parm was defined.  those expressions will be evaluated in that location for the current workitem.
        if top_node_path is None: # Top node path can be provided to get a value from a different location and detect the correct overrides
            top_node_path = work_item.node.topNode().path()
        attrib_names = work_item.attribNames()
        override_present = ( 'overrides' in attrib_names )

        result = None # if an override node is specified, inherit atribs from that node
        if ( result is None ) and override_present:
            override_pdg_node = None

            overrides_attrib = work_item.attrib('overrides')
            if overrides_attrib.type == pdg.attribType.PyObject and overrides_attrib.object is not None:
                overrides_dict = overrides_attrib.object
                parent_matches = { x:overrides_dict[x] for x in overrides_dict if x in top_node_path } # rebuild dict for matches only.
                override_pdg_node_name = None
                if top_node_path in overrides_dict:
                    override_pdg_node_name = overrides_dict[top_node_path]['pdg_node_name']
                elif len(parent_matches) > 0: # use the first nested match if any nested matches occured
                    override_pdg_node_name = parent_matches[ next(iter( parent_matches )) ]['pdg_node_name']
                else:
                    debugLog( 'top_node_path: {} not in overrides_dict: {}. \nparent_matches: {} If you intend to define an output path for this node you should use an output prep node above this node'.format( top_node_path, overrides_dict, parent_matches ) , debug=debug )
                    spacer = ''
                    # return
                if override_pdg_node_name is not None:
                    override_pdg_node = work_item.node.context.graph.node(override_pdg_node_name) # Get the node by its name (really a path with underscores for the current graph)
                # if not override_pdg_node:
                #     raise Exception( 'Error: couldnt get pdg node from work_item: {} name: {}'.format( work_item, override_pdg_node_name ) )

            if not override_pdg_node:
                debugLog( 'No pdg output override node for: {}'.format( work_item.name ) , debug=debug )
                spacer = ''
                # return
            else:
                result = eval_parm_on_node(attrib_name, override_pdg_node, work_item.id, top_node_path)

        if ( result is None ): # ... otherwise aquire value as parameter on the top node.  if it doesn't exist, or is disabled, continue with next method.
            result = eval_parm_on_node(attrib_name, work_item.node, work_item.id, top_node_path)

        # If no other values were defined, use the attribute value as the default / fallback.
        if ( result is None ) and hasattr(work_item, 'data') and hasattr(work_item.data, 'allDataMap') and ( attrib_name in work_item.data.allDataMap ): # lengthy condition for h17.5 compatibility
            # Attributes are aquired only if there is no parameter on the pdg node by the same name.
            if type == 'string':
                result = str( work_item.attrib(attrib_name).value() )
            elif type == 'float':
                result = int( work_item.attrib(attrib_name).value() )              
            elif type == 'array':
                result = work_item.attribArray(attrib_name)    
            else:
                result = int( work_item.attrib(attrib_name).value() )
        debugLog( '...get attrib name: "{}" result: {}'.format( attrib_name, result ) , debug=debug )

        return result

    except ( Exception ), e :
        import traceback
        warningLog( 'ERROR: During getLiveParmOrAttribValue' )
        traceback.print_exc(e)
        # raise e
    

def get_version_db_hou_node_path(work_item=None, hou_node_path=None, debug=debug):
    if work_item is not None:
        hou_node_path = get_hou_node_path( work_item, debug=debug )

    # hou_node = hou.node( hou_node_path )

    # Optionally the version db can be located on another node to isolate any callbacks that we may not want to trigger.  Do not remove.
    # version_db_hou_node_path = hou_node.parent().path() + '/versiondb_' + hou_node.name()

    # version_db_hou_node_path = hou_node.path()

    # return version_db_hou_node_path

    return hou_node_path


