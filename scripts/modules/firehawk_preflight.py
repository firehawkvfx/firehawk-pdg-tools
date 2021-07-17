# deprecated in favour of plugin

# from functools import partial
# import os, sys

# import firehawk_plugin_loader
# import firehawk.plugins
# import firehawk.api
# plugin_modules, api_modules=firehawk_plugin_loader.load_plugins() # load modules in the firehawk.api namespace

# post_flight = firehawk_plugin_loader.module_package('post_flight').post_flight

# class Preflight(): # This class will be used for assigning and using preflight nodes and cooking the main graph.  reloads may not work on this SESI code.
#     def __init__(self, node=None, debug=None, logger_object=None):
#         self.node = node
#         self.selected_nodes = []

#     def cook(self, use_preflight_node=False):
#         import hou, pdg
#         try:
#             if not hou.isUIAvailable():
#                 self.warningLog( 'ERROR hdefereval cannot be called without UI being available' )
#                 return

#             node = self.node

#             import firehawk_submit, firehawk_dynamic_versions

#             submit = firehawk_submit.submit( node )

#             def pull_all_versions_to_all_multiparms():
#                 print( '...Ensuring versions are current from previous submission')
#                 submit = firehawk_submit.submit( hou.node('/') )
#                 firehawk_dynamic_versions.versions().pull_all_versions_to_all_multiparms( check_hip_matches_submit=False, exec_in_main_thread=False, use_json_file=True ) # Ensure any versions generated in the last submisison are in the current hip.
#                 print('...Versions finished sync before saving hip.')
            
#             pull_all_versions_to_all_multiparms()
#             print('...Save_hip_for_submission')
#             hip_name, taskgraph_file = submit.save_hip_for_submission(set_user_data=True, preflight=False, exec_in_main_thread=False) # Snapshot a time stamped hip file for cooking runs.  Must be used for all running tasks, not the live hip file in the current session

#             from nodegraphtopui import cookNode
#             cookNode(node)

#             # use a handler to save the graph on completion.from functools import partial
# import os, sys

# import firehawk_plugin_loader
# import firehawk.plugins
# import firehawk.api
# plugin_modules, api_modules=firehawk_plugin_loader.load_plugins() # load modules in the firehawk.api namespace

# post_flight = firehawk_plugin_loader.module_package('post_flight').post_flight

# class Preflight(): # This class will be used for assigning and using preflight nodes and cooking the main graph.  reloads may not work on this SESI code.
#     def __init__(self, node=None, debug=None, logger_object=None):
#         self.node = node
#         self.selected_nodes = []

#     def cook(self, use_preflight_node=False):
#         import hou, pdg
#         try:
#             if not hou.isUIAvailable():
#                 self.warningLog( 'ERROR hdefereval cannot be called without UI being available' )
#                 return

#             node = self.node

#             import firehawk_submit, firehawk_dynamic_versions

#             submit = firehawk_submit.submit( node )

#             def pull_all_versions_to_all_multiparms():
#                 print( '...Ensuring versions are current from previous submission')
#                 submit = firehawk_submit.submit( hou.node('/') )
#                 firehawk_dynamic_versions.versions().pull_all_versions_to_all_multiparms( check_hip_matches_submit=False, exec_in_main_thread=False, use_json_file=True ) # Ensure any versions generated in the last submisison are in the current hip.
#                 print('...Versions finished sync before saving hip.')
            
#             pull_all_versions_to_all_multiparms()
#             print('...Save_hip_for_submission')
#             hip_name, taskgraph_file = submit.save_hip_for_submission(set_user_data=True, preflight=False, exec_in_main_thread=False) # Snapshot a time stamped hip file for cooking runs.  Must be used for all running tasks, not the live hip file in the current session

#             from nodegraphtopui import cookNode
#             cookNode(node)

#             # use a handler to save the graph on completion.
#             if node is None: return
#             pdg_context = node.getPDGGraphContext()
#             if pdg_context is None: return

#             def update_parms( pdg_context, taskgraph_file, hip_name, handler, event ):

#                 print('...Removing event handler')
#                 handler.removeFromAllEmitters()
#                 print('...Running post_flight.graph_complete.')
#                 post_flight.graph_complete( hip_name ) # you may wish to perform an operation on the hip asset after completion of the graph.
#                 print('...Updating Parms/Versions in this Hip session.')
#                 pull_all_versions_to_all_multiparms() # we update parms last, since its a risky event with hou sometimes crashing, but the crash should be inconequential, since reopening the hip, and pulling versions is also safe.
#                 print('...Finished update_parms in event handler.')

#             print('...AddEventHandler update_parms_partial')
#             update_parms_partial = partial(update_parms, pdg_context, taskgraph_file, hip_name)
#             pdg_context.addEventHandler(update_parms_partial, pdg.EventType.CookComplete, True) # This should save the graph in any event that it stops, including if it is an error.
#             print('Added event handler')
#         except ( Exception, hou.Error ), e :
#             import traceback
#             print( 'Exception: {}'.format(e) )
#             traceback.print_exc(e)
#             raise e

#             def update_parms( pdg_context, taskgraph_file, hip_name, handler, event ):

#                 print('...Removing event handler')
#                 handler.removeFromAllEmitters()
#                 print('...Running post_flight.graph_complete.')
#                 post_flight.graph_complete( hip_name ) # you may wish to perform an operation on the hip asset after completion of the graph.
#                 print('...Updating Parms/Versions in this Hip session.')
#                 pull_all_versions_to_all_multiparms() # we update parms last, since its a risky event with hou sometimes crashing, but the crash should be inconequential, since reopening the hip, and pulling versions is also safe.
#                 print('...Finished update_parms in event handler.')

#             print('...AddEventHandler update_parms_partial')
#             update_parms_partial = partial(update_parms, pdg_context, taskgraph_file, hip_name)
#             pdg_context.addEventHandler(update_parms_partial, pdg.EventType.CookComplete, True) # This should save the graph in any event that it stops, including if it is an error.
#             print('Added event handler')
#         except ( Exception, hou.Error ), e :
#             import traceback
#             print( 'Exception: {}'.format(e) )
#             traceback.print_exc(e)
#             raise e