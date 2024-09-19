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