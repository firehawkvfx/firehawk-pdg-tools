

from . import firehawklocal
from . import custom_handlers

import pdg
exceptions = []
tag_list = pdg.TypeRegistry.types().tags

def registerTypes(type_registry):

    for tag in tag_list:
        if tag in exceptions:
            print('Simple handler for tag {}'.format(tag))
            type_registry.registerCacheHandler(tag, custom_handlers.simple_handler)
        else:
            print('Custom handler for tag {}'.format(tag))
            type_registry.registerCacheHandler(tag, custom_handlers.custom_handler)

    print("Registering firehawklocalscheduler for H18.5") 
    type_registry.registerScheduler(firehawklocal.FirehawkLocalScheduler, label="Firehawk Local Scheduler")
    print("Done registering firehawk schedulers.")
    print("Registering script viewer") 
    type_registry.addTag("file/firehawk/log")
    type_registry.addExtensionTag(".sh", "file/firehawk/log")
    # type_registry.addTagViewer("file/firehawk/log", "pluma") # Tested pluma/nedit.  No vscode. TODO: find suitable handling for os