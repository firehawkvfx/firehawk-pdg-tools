import pdg
import os, sys
import json
from os.path import sep, join

def pjoin(*args, **kwargs):
    return join(*args, **kwargs).replace(sep, '/') # for windows compatibility.

def convert_to_valid_key(name):
    name = name.replace("-", "_")
    name = name.replace(".", "_")
    name = name.replace("/", "_")
    name = name.replace("\\", "_")

    return name

def work_item_db_put(key, value, graph=None): # This method's contents should be replaced with a database call instead of using the filesystem.  value should be a dict, even if it is just a single value.
    # key should be of form job/seq/shot/element/variant/version/index
    # write to /tmp/log/pdg/pdgkvstore/workitems/job/seq/shot/element/variant/version/index

    try:
        if not isinstance( value, dict ):
            raise Exception('Error: value must be a dictionary')

        if graph:
            key = convert_to_valid_key(key)
            # print("Set graph [{}] attrib [{}] value [{}]".format(graph, key, value))
            # if not new_item.graph.attribValue("version"):
            with graph.lockAttributes() as owner:
                owner.setDictAttrib(key, value)
            return

        raise ValueError("Graph object required")
    except Exception as e:
        print("### EXCEPTION work_item_db_put() ###")
        print(str(e))

def work_item_db_get(key, graph=None): # This method's contents should be replaced with a database call in stead of using the filesystem.  value should be a dict, even if it is just a single value.
    # key should be of form job/seq/shot/element/variant/version/index
    # write to /tmp/log/pdg/pdgkvstore/workitems/job/seq/shot/element/variant/version/index

    if graph:
        key = convert_to_valid_key(key)
        value = graph.dictAttribValue(key).asDictionary()
        # print("Retrieve graph [{}] attrib [{}] value [{}]".format(graph, key, value))
        return value

    raise ValueError("Graph object required")