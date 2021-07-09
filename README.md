# Firehawk PDG Tools

For houdini 18.5.596 and higher.  This has been tested on Ubuntu 18.04, CentOS 7 and MacOS 11.4.

Firehawk PDG tools is an implementation for PDG enabling common required abilities for production.  It has been used and contributed to by Rising Sun Pictures and Stormborn Studios.

# Features:
- Auto versioning of directories / paths when new cooks occur.
- Wedging large numbers of output across shots, elements and variations - everything is a wedge.
- Timestamped immutable hip files to reproduce submissions.
- Suitable hooks to modify asset requests if required (eg. if you use a database for your assets)
- Python plugin architecture allowing customisation for studio specific requirements, like DB requests for new assets.
- An example clone of the local scheduler implementing the Firehawk submit class.  It's also possible to apply these tools to any scheduler in their onschedule callback.

# Installation

All you need to do is place firehawk_pdg_tools.json and firehawk_pdg_tools folder in your ~/houdini18.5/packages path.  You may need to create the 'packages' folder if it doesn't already exist.

# Demo

- Open the firehawk.pdg.versioning.demo.hip file
- Right click on /obj/sop_geo_process/topnet1/ropfetch_flipbook, and select 'Cook with Preflight'
- Once it is cooked, if you select to cook again, nothing should occur since the outputs exist on disk.  You should also be able to see the versions of the assets populate on the output nodes.

