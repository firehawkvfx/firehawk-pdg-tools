import os, sys
import json

from os.path import sep, join
def pjoin(*args, **kwargs):
    return join(*args, **kwargs).replace(sep, '/') # for windows compatibility.

def work_item_db_put(key, value): # This method's contents should be replaced with a database call instead of using the filesystem.  value should be a dict, even if it is just a single value.
    # key should be of form job/seq/shot/element/variant/version/index
    # write to /tmp/log/pdg/pdgkvstore/workitems/job/seq/shot/element/variant/version/index

    try: 
        if not isinstance( value, dict ):
            raise Exception('Error: value must be a dictionary')
        root_dir = '/tmp/log/pdg/pdgkvstore/workitems/'
        file_path = pjoin( root_dir, key )
        if os.path.isfile(file_path): # erase any content if already there.  the method is used to init an entry and set it.  if updating the entry is required, you will need another method - be careful, without a database manager you will run into lock issues.
            os.remove(file_path)
        dirname = os.path.dirname(file_path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        with file( file_path , 'w' ) as db_file:
            json.dump( value, db_file )
    except Exception as e:
        print("### EXCEPTION work_item_db_put(key, value) ###")
        print(str(e))

def work_item_db_get(key): # This method's contents should be replaced with a database call in stead of using the filesystem.  value should be a dict, even if it is just a single value.
    # key should be of form job/seq/shot/element/variant/version/index
    # write to /tmp/log/pdg/pdgkvstore/workitems/job/seq/shot/element/variant/version/index
    root_dir = '/tmp/log/pdg/pdgkvstore/workitems/'
    file_path = pjoin( root_dir, key )
    print('Retrieving work item at key: {}'.format( file_path ) )
    
    json_object = {}
    if os.path.isfile( file_path ):
        with open(file_path, 'r') as db_file:
            json_object = json.load(db_file)
            if not isinstance( json_object, dict ):
                json_object = {}
            else:
                print( 'Loaded existing JSON data: {}'.format(json_object) )

    return json_object