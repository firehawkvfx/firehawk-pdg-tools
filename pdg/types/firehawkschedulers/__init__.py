

from . import firehawklocal
from . import custom_handlers
from . import firehawktbdeadline

import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger()

import pdg
exceptions = []
tag_list = pdg.TypeRegistry.types().tags

def registerTypes(type_registry):
    print("Register types for Firehawk Schedulers...")

    for tag in tag_list:
        if tag in exceptions:
            firehawk_logger.debug('Simple handler for tag {}'.format(tag))
            type_registry.registerCacheHandler(tag, custom_handlers.simple_handler)
        else:
            firehawk_logger.debug('Custom handler for tag {}'.format(tag))
            type_registry.registerCacheHandler(tag, custom_handlers.custom_handler)

    firehawk_logger.debug("Registering firehawklocalscheduler for H18.5")
    type_registry.registerScheduler(firehawklocal.FirehawkLocalScheduler, label="Firehawk Local Scheduler")
    firehawk_logger.debug("Registering firehawkdeadlinescheduler for H18.5")
    type_registry.registerScheduler(firehawktbdeadline.FirehawkDeadlineScheduler, label="Firehawk Deadline Scheduler")
    firehawk_logger.debug("Done registering firehawk schedulers.")
    firehawk_logger.debug("Registering script viewer")
    type_registry.addTag("file/firehawk/log")
    type_registry.addExtensionTag(".sh", "file/firehawk/log")
    # type_registry.addTagViewer("file/firehawk/log", "pluma") # Tested pluma/nedit.  No vscode. TODO: find suitable handling for os