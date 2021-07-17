# work items can attach attribute values to the submitObject.ord_dict, a plain dictionary that may be used in a submission pipeline.

def get_submission_attributes():
    submission_attributes = {
        'job': {'var_data_type': 'string' },
        'asset_type': {'var_data_type': 'string' },
        'format': {'var_data_type': 'string' },
        'volatile': {'var_data_type': 'int' },
        'res': {'var_data_type': 'string' },
        'animating_frames': {'var_data_type': 'string' }
    }
    return submission_attributes


    