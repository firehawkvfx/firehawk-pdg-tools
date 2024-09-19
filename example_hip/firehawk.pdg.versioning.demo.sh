#!/bin/bash

# This is an automated cook test.  

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )" # The directory of this script

FH_VAR_DEBUG_PDG=10 hython $SCRIPTDIR/firehawk.pdg.versioning.demo.hip $SCRIPTDIR/firehawk.pdg.versioning.demo.py