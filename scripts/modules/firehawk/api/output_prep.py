import os

import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=10)

firehawk_logger.timed_info(label='output_prep plugin loaded')

debug_default = int(( os.getenv('DEBUG_PDG', 'false').lower() in ('true', 'yes', '1') )) # resolve env var as int

def parm_format_menu_list():
    result = [  'bgeo.sc', "Bgeo (Blosc)", # default shoudl be item zero.  string refs to defaults can cause errors due to a bug.
                'bgeo.gz', "Bgeo (Zipped)",
                'bgeo', "Bgeo",
                'obj', "Obj", 
                'abc', "MeshCache (abc)", 
                'sim', "Dop Sim", 
                'simdata', "Dop Simdata", 
                'pc', "Pointcloud (pc)",
                'abc', 'Alembic',
                'vdb', 'OpenVDB',
                'vdbpoints', 'OpenVDB Points',
                'ass', 'Arnold Ass File',
                'exr', 'Exr',
                'jpg', 'Jpg',
                'mp4', 'Mp4',
                'ip', 'Ip (Interactive Mplay)',
                'hip', 'Hip',
                'py', 'Py'
                ]
    return result

def parm_asset_type_menu_list():
    result = [  'geocache', "Geo Cache", # Default should be item 0, normally used for houdini caching with bgeo.sc
                'meshcache', "Mesh Cache", 
                'pointcache', "Point Cache", 
                'volumecache', "Volume Cache", 
                'rendering', "Rendering", 
                'renderarchive', "Render Archive",
                'setup', "Setup",
                'script', "Script"
                ]
    return result

def prepare_output_type(work_item, output_topnode_path, output_topnode_type_name, output_format):
    if output_format == "mp4":
        work_item.setStringAttrib('rop', output_topnode_path) # onscheduled callback still needs to consider the output for versioning.
        work_item.setStringAttrib('outputparm', 'outputfilepath')
        # file_name_result used to be set to the asset path.  this may be required again in the future. TODO: validate this.
    elif len(output_topnode_type_name) > 0 and output_topnode_type_name == 'ropcomposite':
        work_item.setStringAttrib('rop', output_topnode_path)
        work_item.setStringAttrib('outputparm', 'copoutput')

def output_nodes_kv(): # to a avoid hou calls in python generate blocks, we construct a dictionary with the required info to aid stability
    import json
    import hou

    node_list = []
    parent = hou.pwd().parent()

    kv={}
    for parm in parent.parm('output_nodes0').multiParmInstances():
        for node in parm.evalAsNodes():
            
            child_rops = [ x for x in node.children() if x.type().name()=='ropfetch' ]
            
            override_target = node.path()
            override_target_type_name = node.type().name()
            if len(child_rops) > 0: # if there is a rop nested, target that instead
                override_target = child_rops[0].path()
                override_target_type_name = child_rops[0].path().type().name()
            
            new_kv = { 
                node.path() : { 
                    "output_topnode_path" : node.path(), # this may be a parent node containing others, ie matnra top/
                    "output_topnode_type_name" : node.type().name(), 
                    "child_rops" : child_rops, 
                    "override_target" : override_target, # this is the actual node doing the workload, ie the rop fetch inside a mantra top.
                    "override_target_type_name" : override_target_type_name,
                    "override_origin_path" : hou.pwd().path()
                }
            }
            kv.update( new_kv )

    return json.dumps(kv)

# {"/obj/sop_geo_process/topnet1/ropfetch2": {"output_topnode_type_name": "ropfetch", "override_origin_path": "/obj/sop_geo_process/topnet1/outputprep2/pythonprocessor1", "override_target_type_name": "ropfetch", "output_topnode_path": "/obj/sop_geo_process/topnet1/ropfetch2", "child_rops": [], "override_target": "/obj/sop_geo_process/topnet1/ropfetch2"}}

def update_workitems(pdg_node, item_holder, upstream_items, generation_type, eval_output_expr_once=True):
    # update_workitems is used to attach submission data required for auto versioning, asset creation, and scheduler customisation.
    print('\nupdate_workitems')

    # pdg_node         -   A reference to the current pdg.Node instance
    # item_holder      -   A pdg.WorkItemHolder for constructing and adding work items
    # upstream_items   -   The list of work items in the node above, or empty list if there are no inputs
    # generation_type  -   The type of generation, e.g. pdg.generationType.Static, Dynamic, or Regenerate
    # eval_output_expr_once - since the output expression can apply to all output, it may only need to be evaluated once.  evaluation of this for every work item could be very slow since it may involve a request to some db or schema once per item.

    firehawk_logger.timed_info(label='update_workitems: start')
    import pdg, json
    firehawk_logger.timed_info( label='update_workitems: iter node_list:' )
    
    try:
        output_nodes_kv_str = str( pdg_node.parameter("output_nodes_kv").evaluate() )
        output_nodes_kv = json.loads( output_nodes_kv_str )
    except:
        print('ERROR: Could not get json from string. pdg_node: {}'.format( pdg_node ) )
        output_nodes_kv = {}

    if output_nodes_kv is None or len(output_nodes_kv) == 0:
        return

    node_list = [ output_nodes_kv[x]['output_topnode_path'] for x in output_nodes_kv ]

    if len(node_list) == 0:
        raise pdg.CookError("Must specify a downstream top node to submit")

    keys = []
    pydict = {}
    for k,v in output_nodes_kv.iteritems():
        keys.append(k) # list keys

        # This data is intended for downtream
        override_target = v["override_target"]
        pydict[override_target] = {}
        pydict[override_target]["override_origin_path"] = v["override_origin_path"]
        pydict[override_target]["pdg_node_name"] = pdg_node.name

    output_topnode_path = output_nodes_kv[ keys[0] ]["output_topnode_path"] # presently the rop attribute only supports one item.  This method should potentially be relocated to the onschedule callback to support multiple nodes.
    output_topnode_type_name = output_nodes_kv[ keys[0] ]["output_topnode_type_name"]
    output_format = pdg_node.parameter('format').evaluateString()
    set_output = None
    index_key_unexpanded = pdg_node.parameter('index_key').evaluateString()

    asset_type = pdg_node.parameter('asset_type').evaluateString()

    render_asset_types = [ 'renderarchive', 'rendering' ]
    resolution = None
    if asset_type in render_asset_types: # Add resolution if we are rendering.
        resolution = pdg_node.parameter('resolution').evaluateInt()

    for item in upstream_items:
        firehawk_logger.timed_info( label='update_workitems: start item: {}'.format( item ) )
        options = pdg.WorkItemOptions()
        options.cloneMode = pdg.cloneMode.Always
        options.cloneTarget = item
        options.cloneResultData = True
        options.inProcess = True
        options.parent = item
        work_item = item_holder.addWorkItem(options) # clone upstream items

        firehawk_logger.timed_info( label='update_workitems: iter parms: {}'.format( item ) )

        work_item.addAttrib('overrides', pdg.attribType.PyObject)
        work_item.setPyObjectAttrib('overrides', pydict) # set the attribute
                
        firehawk_logger.timed_info( label='update_workitems: done iter node list: {}'.format( item ) )

        # An output node can record many output paths (wedges/shots/assets).  The index key determines what should be currently read from or written to.  if the index key doesn't exist, a new entry is created.
        # index_key_unexpanded = pdg_node['index_key'].evaluateString(work_item)
        work_item.setStringAttrib('index_key_unexpanded', index_key_unexpanded)

        firehawk_logger.timed_info( label='update_workitems: make active' )
        with work_item.makeActive():
            if eval_output_expr_once:
                if set_output is None:
                    set_output = pdg_node.parameter('set_output').evaluateString() # output parm uses in this case a constant expression that we only need to eval once.  it doesn't vary per work item.  This operation is expensive.
            else: 
                set_output = pdg_node.parameter('set_output').evaluateString() # evaluating this as a unique value for every work item is not recommended, this logic may take a long time to do so!
            index_key_expanded = pdg_node['index_key_expanded'].evaluateString()
        
        work_item.setStringAttrib('set_output', set_output)
        
        firehawk_logger.timed_info( label='update_workitems: set index key: {}'.format( item ) )

        work_item.setStringAttrib('index_key', index_key_expanded) # precompute the index key for submission. it is ephemeral, should not be used beyond the next node.

        firehawk_logger.timed_info( label='update_workitems: done set index key: {}'.format( item ) )
        if resolution is not None:
            work_item.setIntAttrib('resolution', resolution)
            
        work_item.setIntAttrib('onScheduleVersioned', 0) # This attribute is updated if items get scheduled to track asset creation.
        firehawk_logger.timed_info( label='update_workitems: prepare_output_type: {}'.format( item ) )
        prepare_output_type(work_item, output_topnode_path, output_topnode_type_name, output_format)
        firehawk_logger.timed_info( label='update_workitems: end item: {}'.format( item ) )

    print('update_workitems done.\n\n')