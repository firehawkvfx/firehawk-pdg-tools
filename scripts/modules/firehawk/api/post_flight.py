import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger()

def graph_complete(hip_name):
    firehawk_logger.info('End Cooking Graph: {}'.format(hip_name))