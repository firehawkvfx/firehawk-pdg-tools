### If you have more than one 456.py you will need to copy the contents of this into you main 456.py

import os
# Optional import
firehawk_root = os.getenv("FIREHAWK_PDG_TOOLS_ROOT")
if firehawk_root and os.path.isdir(firehawk_root):
    import firehawk_plugin_loader
    firehawk_plugin_loader.module_package('startup_456').startup_456.init()