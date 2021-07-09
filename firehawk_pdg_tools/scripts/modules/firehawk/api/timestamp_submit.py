
# Modules that are called to timestamp a hip file for submission

import os
import datetime as dt

import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=10)

def datetime_object_str_to_object(datetime_object_str): # return string as datetime object
    datetime_object = dt.datetime.strptime(datetime_object_str, "%Y-%m-%d %H:%M:%S.%f") # ensure the dt object successfuly converts to string and back for consistency.
    return datetime_object

def update_timestamp(): # return datetime object as string
    datetime_object = dt.datetime.now()
    datetime_object_str = str( datetime_object )
    datetime_object = datetime_object_str_to_object(datetime_object_str) # ensure the string safely converts back to a datetime object, since it will be read from user data.
    return datetime_object, datetime_object_str 

def ensure_dir_exists(directory ):
    if not os.path.isdir( directory ):
        ### Need to create dir here
        firehawk_logger.debugLog( "Creating Directory: {}".format( directory ) )
        os.makedirs( directory )
        if not os.path.isdir( directory ): # check that it actually got created
            firehawk_logger.debugLog( "Error creating dir: {}".format( directory ) )
            return

def timestamp_submission_str(datetime_object, dir, hip_basename): # return a timestamped hip file and a custom formated string from the timestamp

    timestamp_str = datetime_object.strftime("%Y-%m-%d.%H-%M-%S-%f") # append a time of submission, with microseconds.

    # hip_name = "{dir}/submit/{base}.{date}.hip".format( dir=dir, base=hip_basename, date=timestamp_str)
    # ensure_dir_exists( os.path.dirname( hip_name ) )

    return timestamp_str


