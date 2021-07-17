import pdg, hou, firehawk_read
import firehawk_plugin_loader
pdgkvstore = firehawk_plugin_loader.module_package('pdgkvstore').pdgkvstore
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger()

# This retrieves the kvstore for a given work item by reading parameters evaluated for that work item (like the version).  It is seperate to pdgkvstore because it requires hou, which should be isolated from pdg where possible.

def getPdgKvStore(work_item): # Attempt to get previous job id data for a work item to retrieve a log.  this will depend on version parameters defined by hou nodes.
    subindex = work_item.batchIndex # schedulers only ever operate on single work items or batch parents.  This should usually return -1 in this scenario.  if this is used in scenarios other than on a scheduler, we should aquire the batch parent if work item has one.
    kwargs = {}
    
    required_components = ['job', 'seq', 'shot', 'element', 'variant']

    kwargs = {}
    for key in required_components:
        firehawk_logger.debug( 'Retrieve parm/attrib: {} for work_item: {}'.format( key, work_item ))
        value = firehawk_read.getLiveParmOrAttribValue(work_item, key, type='string')
        if value is None:
            return None
        kv = { key: value }
        firehawk_logger.debug( 'update kv: {}'.format( kv ) )
        kwargs.update( kv )

    firehawk_logger.debug('kwargs: {}'.format( kwargs ))

    # Get the version for the work item by evaluating the version prameter on the node.

    if firehawk_read.get_is_exempt_from_hou_node_path(work_item): # kv store for work items without versions / hou nodes is not presently supported.
        return None

    version_db_hou_node_path = firehawk_read.get_version_db_hou_node_path(work_item=work_item)
    firehawk_logger.debug( "version_db_hou_node_path: {}".format( version_db_hou_node_path ) )
    version_db_hou_node = hou.node( version_db_hou_node_path )

    json_object = None
    version_parm = version_db_hou_node.parm('version')
    if version_parm is not None:
        with work_item.makeActive(): version_int = version_parm.eval()
        version_str = 'v'+str( version_int ).zfill(3)
        kwargs['version'] = version_str

        key = '{}/{}/{}/{}/{}/{}/{}'.format( kwargs['job'], kwargs['seq'], kwargs['shot'], kwargs['element'], kwargs['variant'], kwargs['version'], subindex )
        firehawk_logger.debug('work_item_db_get key: {}'.format( key ) )
        json_object = pdgkvstore.work_item_db_get(key)

    return json_object # if an attribute couldn't be aquired, will return none.  if kvstore retrieval file didn't exist or failed, will return empty dict.