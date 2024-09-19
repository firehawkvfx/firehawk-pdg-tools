# Firehawk PDG Tools

For Houdini 18.5.596 and higher.  This has been tested on Ubuntu 18.04, CentOS 7, MacOS 11.4, and Windows 10

Firehawk PDG tools is an implementation for PDG enabling common required abilities for production.  It has been used and contributed to by Rising Sun Pictures and Stormborn Studios.

# Installation

- Ensure the "packages" folder exists in the user houdini folder.  The user houdini folder is different depending on your OS.  You may need to create the 'packages' folder if it doesn't already exist. eg:  
```
Linux:  
~/houdini18.5/packages
Mac OS:  
~/Library/Preferences/houdini/18.5/packages
Windows:  
$HOME/Downloads/houdini/18.5/packages
```

- Place the entire firehawk-pdg-tools folder in the `packages` folder.  
- Copy the firehawk-pdg-tools.json directly into the `packages` folder.  Json files in packages are read here and load specified package contents.  

From the packages folder, the tree should look like this: 
```
packages % tree -L 1  
.
├── firehawk-pdg-tools
└── firehawk-pdg-tools.json
```

- If you wish to show debugging information for submission, use this env var before you load houdini:
```
FH_VAR_DEBUG_PDG=10
```

# Features:

- Auto versioning of directories / paths when new cooks occur.
- Wedging large numbers of output across shots, elements and variations - everything is a wedge.
- Timestamped immutable hip files to reproduce submissions.
- Suitable hooks to modify asset requests if required (eg. if you use a database for your assets)
- Python plugin architecture allowing customisation for studio specific requirements, like DB requests for new assets.
- An example clone of the local scheduler implementing the Firehawk submit class.  It's also possible to apply these tools to any scheduler in their onschedule callback.

# Demo

- Open the firehawk.pdg.versioning.demo.hip file
- Right click on /obj/sop_geo_process/topnet1/ropfetch_flipbook, and select 'Cook with Preflight'

# Other Notes:

- If python scripts are executed in a plain shell on a farm outside of the current houdini process, ensure this command has the PYTHONPATH env var set to include the same path defined in firehawk-pdg-tool.json.  Normally with the local scheduler this isn't necesary, since PYTHONPATH has already been set by the package with firehawk-pdg-tool.json.  This is especially relevant for a process like PDGMQ, which wont be executed inside houdini and therefore wouldn't have access to the firehawk-pdg-tools libraries, which could be required.
