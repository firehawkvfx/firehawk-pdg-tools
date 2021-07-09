# firehawk-pdg-tools

For houdini 18.5.596 and higher.

Firehawk PDG tools is an implementation for PDG enabling common required abilities for production:
- Auto versioning of directories / paths when new cooks occur.
- Wedging large numbers of output across assets, shots, variations.
- Timestamped immutable hip files to reproduce submissions.
- Suitable hooks to modify asset requests if required (eg. if you use a database for your assets)
- Python plugin architcture allowing customisation for studio specific requirements
- An example clone of the local scheduler implementing the firehawk submit functions.  It's also possible to apply these tools to any scheduler during the onschedule callback.

All you needs to do is place firehawk_pdg_tools.json and firehawk_pdg_tools folder in your ~/houdini18.5/packages path.  You may need to create the 'packages' folder if it doesn't alreaady exist.
