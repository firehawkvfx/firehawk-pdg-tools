# custom handlers allow us to control if cache items exist / or maked dirty and cooking should occur.  In our case if the path schema changes via an upstream node, or if the output path on the target has been wiped, we need to force a cook.
# if the work item thinks it's already cooked and the path doesn't change on the node directly, then it wouldn't catch this case.  so we force a cook here for handle it.

import os, pdg, hou
import firehawk_submit as firehawk_submit
import firehawk_read

import firehawk_plugin_loader
debug_default = firehawk_plugin_loader.resolve_debug_default()
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=debug_default)

def simple_handler(local_path, raw_file, work_item):
    firehawk_logger.debug(local_path)
    return pdg.cacheResult.Skip

def custom_handler(local_path, raw_file, work_item):
    # firehawk_logger.timed_info(label='custom_handlers.py: timed_info')
    firehawk_logger.debug('')
    firehawk_logger.debug('### CUSTOM CACHE HANDLER ### {}'.format( work_item.name ) )
    # Skip work items that have custom caching disabled.
    # if firehawk_submit.submit().getLiveParmOrAttribValue(work_item, 'use_custom_caching') == 0:
    #     return pdg.cacheResult.Skip
    def endMessage():
        firehawk_logger.debug( '### CUSTOM CACHE HANDLER END ###' )
    try:
        set_output = None
        if int( os.getenv('PDG_USE_CUSTOM_EXPRESSION_HANDLER', '1') ) and work_item.isNoGenerate == False: # This funcitonality can be disabled if it is suspected of causing a hang. SESI state this may be fixed after H18.5.430
            firehawk_logger.timed_debug( '...Use custom logic to see if the path schema has changed.  Ensures the expression is correct, not just the file on disk.' )
            with work_item.makeActive():
                firehawk_logger.timed_debug('get hou node path')
                hou_node_path = firehawk_read.get_hou_node_path(work_item)
                hou_node = hou.node(hou_node_path)
                # set_output = None
                firehawk_logger.timed_debug('read set_out')
                set_output = work_item.stringAttribValue('set_output')
                set_output = firehawk_read.resolve_pdg_vars(set_output, work_item=work_item)
                firehawk_logger.timed_debug('set_output: {}'.format(set_output) )
                # set_output = firehawk_read.getLiveParmOrAttribValue(work_item, 'set_output', debug=debug) # set_output is the unexpanded expression that should be used on the target.
                # get_output = None

                # Node: /obj/sop_geo_process/topnet1/outputprep2/pythonprocessor1 parm: set_output with tags: {'format': u'bgeo.sc', 'res': u'1920_1080_bgeo.sc', 'asset_type': u'geocache', 'job': u'stereo', 'volatile': u'off', 'create_asset': False, 'animating_frames': u'$F4', 'use_inputs_as': 'channels'}
                firehawk_logger.timed_debug('get output')
                get_output = firehawk_read.get_output(hou_node, work_item=work_item, set_output=set_output, debug=debug_default) # get_output is the current expression on the target.  if they dont match, the work item must be queued.
                firehawk_logger.timed_debug('get output: {}'.format(get_output) )
                # set_index_key = None
                firehawk_logger.timed_debug('read index key')
                set_index_key = work_item.stringAttribValue('index_key_unexpanded')
                firehawk_logger.timed_debug('get index_key_expr')
                # set_index_key = firehawk_read.getLiveParmOrAttribValue(work_item, 'index_key', debug=debug)
                # index_key_expr = None
                index_key_expr = firehawk_read.get_output_index_key_expr(hou_node, debug=debug_default)
                firehawk_logger.timed_debug('done aquisition')
            
            if (set_output is not None) and (get_output is None):
                firehawk_logger.timed_debug( 'Result: Miss. Output on target is not yet set. get_output: {} set_output: {}'.format( get_output, set_output ) )
                endMessage()
                return pdg.cacheResult.Miss

            if (set_index_key is not None) and (index_key_expr is None):
                firehawk_logger.timed_debug( 'Result: Miss. index_key on target is not yet set.' )
                endMessage()
                return pdg.cacheResult.Miss

            if (set_output is not None) and (get_output is not None) and len(set_output)>0 and (get_output != set_output):
                firehawk_logger.timed_debug( 'Result: Miss. Output schema not matching current output parm.  Will Cook.' )
                endMessage()
                return pdg.cacheResult.Miss

            if (set_index_key is not None) and (index_key_expr is not None) and len(set_index_key)>0 and (index_key_expr != set_index_key):
                firehawk_logger.timed_debug( 'Result: Miss. Output index_key not matching current index_key parm.  Will Cook.' )
                endMessage()
                return pdg.cacheResult.Miss

        # If these unexpanded strings do not match, force a cook since the schema has changed.
        if not os.path.isfile(local_path):
            firehawk_logger.timed_debug( 'Result: Miss. no file: {}'.format( local_path ) )
            endMessage()
            return pdg.cacheResult.Miss

        firehawk_logger.timed_debug( 'Check if file has no size on disk {}'.format( local_path ) )

        if local_path and os.stat(local_path).st_size == 0:
            firehawk_logger.timed_debug( 'Result: Miss. no file / file with size 0' )
            endMessage()
            return pdg.cacheResult.Miss
        
        firehawk_logger.timed_debug( 'Result: Hit.' )
        endMessage()
        return pdg.cacheResult.Hit
    except Exception as e:
        print("### EXCEPTION ### ERROR:")
        print(str(e))
        print( 'Result: Miss.' )
        endMessage()
        return pdg.cacheResult.Miss

# exceptions = []
# tag_list = pdg.TypeRegistry.types().tags

# def registerTypes(type_registry):
#     for tag in tag_list:
#         if tag in exceptions:
#             print('Simple handler for tag {}'.format(tag))
#             type_registry.registerCacheHandler(tag, simple_handler)
#         else:
#             print('Custom handler for tag {}'.format(tag))
#             type_registry.registerCacheHandler(tag, custom_handler)
    
