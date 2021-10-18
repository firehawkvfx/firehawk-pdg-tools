#
# Copyright (c) <2020> Side Effects Software Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# NAME:         tbdeadline.py ( Python )
#
# COMMENTS:     Defines a Thinkbox Deadline scheduler implementation for PDG.
#               This module depends on the deadline commandline
#               which is installed with the Deadline client, for example: 
#               %DEADLINE_PATH%\deadlinecommand.exe
#
#               To use this module you must ensure that DEADLINE_PATH is set
#               in the environment. This also requires the custom PDGDeadline
#               plugin for Deadline that is shipped with Houdini. The plugin
#               can be found at $HFS/houdini/pdg/plugins
#               
#               Currently supports both new and old MQ.
#               New MQ path uses the ServiceManager to share MQ use.
#               Supports MQ on farm, local, or connecting to existing.
#

import datetime
import os
import sys
import shutil
import time
import shlex
import re
import json
import traceback
import socket
import threading
import six
from threading import Thread
from collections import deque

import six.moves.xmlrpc_client as xmlrpclib
from six.moves.queue import Queue, Empty
import six.moves.urllib.parse as parse
from six.moves import zip

from pdg import attribFlag
from pdg import serviceState, scheduleResult, tickResult, CookError, ServiceError
from pdg import TypeRegistry
from pdg.job.eventdispatch import EventDispatchMixin
from pdg.job.mqrelay import MQRelay
from pdg.job.callbackserver import CallbackServer
from pdg.scheduler import PyScheduler

import pdgd

from . import tbdeadline_utils as tbut
from pdg.utils.mq import MQUtility, MQInfo, MQState, MQUsage, MQSchedulerMixin

from pdgutils import PDGNetMQRelay, mqGetError, mqCreateMessage, PDGNetMessageType

### Do not edit imports above this line.  This serves as a baseline for future updates to the localscheduler ###

import logging 
from collections import namedtuple 
import re 
from pdg import CookError

sys.path.append(os.path.expandvars("$HFS/houdini/pdg/types/schedulers")) # TODO: Try and remove this if it can be done without producing errors.

from tbdeadline import DeadlineScheduler

import pdg
import firehawk_submit as firehawk_submit # Firehawk presubmission utils for multiparm versioning.
import firehawk_read

import firehawk_plugin_loader
pdgkvstore = firehawk_plugin_loader.module_package('pdgkvstore').pdgkvstore
houpdgkvstore = firehawk_plugin_loader.module_package('houpdgkvstore').houpdgkvstore

import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger()
firehawk_logger.timed_info(label='firehawk scheduler loaded')
firehawk_logger.debug('test debug logger')

from datetime import datetime

# Replicate the scheduler with a patched method

class FirehawkDeadlineScheduler(DeadlineScheduler):
    """
    Modified Firehawk Scheduler implementation for Thinkbox's Deadline scheduler.
    """
    def onPreSubmitItem(self, work_item, job_env, item_command):
        """
        Modifies the item command before it gets submitted to be run.
        Intended to be used in a user subclass of this scheduler.
        """

        ### Firehawk on schedule version handling dynamically allows a version per wedge to store as a multiparm db.
        submitObject = firehawk_submit.submit( debug=self._verbose )
        item_command = submitObject.onPreSubmitItem(work_item, job_env, item_command, logger_object=firehawk_logger) # optionally attach a logger object here
        if item_command is None:
            raise CookError( 'Failed: onPreSubmitItem. item_command: {}'.format(item_command) )

        work_item.setCommand( item_command )

        kwargs = {}
        required_components = ['job', 'seq', 'shot', 'element', 'variant'] # store kv for work item permanently to aquire logs if cooked from cache / or just generated.
        for key in required_components:
            value = firehawk_read.getLiveParmOrAttribValue(work_item, key, type='string')
            kv = { key: value }
            firehawk_logger.debug( 'update kv: {}'.format( kv ) )
            kwargs.update( kv )
        
        kwargs['version'] = 'v'+str( work_item.intAttribValue('version') ).zfill(3)
        kwargs['subindex'] = work_item.batchIndex
        
        firehawk_logger.debug('kvstore kwargs: {}'.format( kwargs ))
        if all( [ x in kwargs for x in required_components ] ): # If all components are available, then stash job data in our kv store.
            key = '{}/{}/{}/{}/{}/{}/{}'.format( kwargs['job'], kwargs['seq'], kwargs['shot'], kwargs['element'], kwargs['variant'], kwargs['version'], kwargs['subindex'] )
            value = {
                'log_uri': { 'value': self.getLogURI(work_item), 'type': 'string'}
            }
            firehawk_logger.debug('write: {}'.format( value ) )
            pdgkvstore.work_item_db_put(key, value) # write value to disk, or a database if available.
                
        self._verboseLog("End presubmit")

        return item_command

    def _scheduleTaskForWorkItem(self, work_item, local_job_dir):
        """
        Writes out the task file for the given work item, and
        append it to the pending tasks queue for submission.
        """
        new_task_id = self.next_task_id
        submit_as_job = False

        self.onPreSubmitItem(work_item, work_item.environment, work_item.command) # update the work item to handle autoversioning and optionally modify the work_item command

        self._writeTaskFile(new_task_id, work_item, local_job_dir, work_item.command,
                            work_item.name, work_item.index, work_item.node, submit_as_job)
        self.next_task_id = self.next_task_id + 1

        # Add to pending queue to process in update
        self.pending_tasks_queue.append((new_task_id, work_item))

    def registerTypes(type_registry): 
        firehawk_logger.info("Init firehawkdeadlinecheduler schedulers") 