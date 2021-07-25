# This file is used in the .sh script to test cooking with preflight.

import hou
node=hou.node('/obj/sop_geo_process/topnet1/output0')

import firehawk_plugin_loader
firehawk_plugin_loader.module_package('pre_flight').pre_flight.Preflight( node ).cook()