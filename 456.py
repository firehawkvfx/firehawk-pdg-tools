"""
Run by 456.py as python -c execfile($0) for all files called

456.py and 456slave.py link in HOUDINI_SCRIPT_PATH
"""

import os
import hou
import time
import traceback

print( '456slave.py: ...Pull versions from sidecar object to multiparms.' )
try:
    import firehawk_dynamic_versions
    # pull_all_versions_to_all_multiparms will search for an attribute (or optionally a sidecar file ending in .json that matches the name of the hip file).  If a match is found, the data contained will allow parameters to be updated on load.
    # This allows dynamically created versions to be updated to all known current versions to the scheduler at the time the hip is being loaded elsewhere like on farm processes.
    # for example, if 10 wedges are on an input, and they all had new versions in this submission, the the output would need to know all 10 wedge versions if they were to be combined, so we load those versions as current as possible.
    use_json_file = hou.isUIAvailable()
    firehawk_dynamic_versions.versions().pull_all_versions_to_all_multiparms( check_hip_matches_submit=True, use_json_file=use_json_file ) # Only update multiparms if this is a farm submission hip file. If no work item reoslves, use the json file to pull versions.
    print( '456.py: Done.' )
except:
    traceback.print_exc()
    print('No PDG dynamic versions were imported')