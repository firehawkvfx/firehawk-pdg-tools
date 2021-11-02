from functools import partial
import os, sys

import firehawk_plugin_loader
debug_default = firehawk_plugin_loader.resolve_debug_default()
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=debug_default)

def pull_all_versions_to_all_multiparms(exec_in_main_thread=False, use_json_file=True):
    import firehawk_dynamic_versions
    firehawk_logger.info( '...Ensuring versions are current from previous submission')
    # submit = firehawk_submit.submit( hou.node('/') )
    firehawk_dynamic_versions.versions().pull_all_versions_to_all_multiparms( check_hip_matches_submit=False, exec_in_main_thread=exec_in_main_thread, use_json_file=True ) # Ensure any versions generated in the last submisison are in the current hip.
    firehawk_logger.info('...Versions finished sync before saving hip.')

def init_firehawk_topnet_parms(parent):
    import firehawk_dynamic_versions, firehawk_read

    top_net_path = firehawk_read.get_parent_top_net(parent).path()
    firehawk_dynamic_versions.versions().init_firehawk_topnet_parms( top_net_path )

class Preflight(): # This class will be used for assigning and using preflight nodes and cooking the main graph.  reloads may not work on this SESI code.
    def __init__(self, node=None, debug=None, logger_object=None):
        self.node = node
        self.selected_nodes = []
        self.submit = None

    def set_update_workitems(self, node):
        # submitObject = firehawk_submit.submit( debug=self._verbose, logger_object=None )
        parent_top_net = self.submit.get_parent_top_net(node)
        regenerationtype_parm = parent_top_net.parm('regenerationtype')
        
        if regenerationtype_parm and regenerationtype_parm.evalAsInt() != 1: regenerationtype_parm.set(1)

    def cook(self, use_preflight_node=False):
        import hou, pdg

        exec_in_main_thread=True
        if not hou.isUIAvailable():
            exec_in_main_thread=False

        node = self.node

        import firehawk_submit
        import firehawk_plugin_loader
        post_flight = firehawk_plugin_loader.module_package('post_flight').post_flight

        # ensure firehawk parms exist on topnet
        init_firehawk_topnet_parms(node.parent())

        self.submit = firehawk_submit.submit( node )

        # self.submit = firehawk_submit.submit( hou.node('/') )

        pull_all_versions_to_all_multiparms(use_json_file=True) # we are in the ui thread already, no need to exec in main thread.
        self.set_update_workitems(node)

        firehawk_logger.info('...Save_hip_for_submission')
        hip_name, taskgraph_file = self.submit.save_hip_for_submission(set_user_data=True, preflight=False, exec_in_main_thread=False) # Snapshot a time stamped hip file for cooking runs.  Must be used for all running tasks, not the live hip file in the current session

        if hou.isUIAvailable():
            from nodegraphtopui import cookNode
            cookNode(node)
        else:
            node.executeGraph(block=True)

        # use a handler to save the graph on completion.
        if node is None: return
        pdg_context = node.getPDGGraphContext()
        if pdg_context is None: return

        def update_parms( pdg_context, taskgraph_file, hip_name, handler, event ):
            firehawk_logger.info('...Removing event handler')
            handler.removeFromAllEmitters()
            firehawk_logger.info('...Running post_flight.graph_complete.')
            post_flight.graph_complete( hip_name ) # you may wish to perform an operation on the hip asset after completion of the graph.
            firehawk_logger.info( '...Updating Parms/Versions in this Hip session. exec_in_main_thread: {}'.format( exec_in_main_thread ) )
            pull_all_versions_to_all_multiparms(exec_in_main_thread=exec_in_main_thread, use_json_file=True) # we update parms last, but since this is coming from a callback, we needs to use hou's ability to execute in the main thread.
            firehawk_logger.info('...Finished update_parms in event handler.')

        firehawk_logger.info('...AddEventHandler update_parms_partial')
        update_parms_partial = partial(update_parms, pdg_context, taskgraph_file, hip_name)
        pdg_context.addEventHandler(update_parms_partial, pdg.EventType.CookComplete, True) # This should save the graph in any event that it stops, including if it is an error.
        firehawk_logger.info('Added event handler')

