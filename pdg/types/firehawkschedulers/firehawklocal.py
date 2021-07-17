
from __future__ import print_function 

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

# NAME: firehawklocal.py ( Python )

# COMMENTS: Defines a local scheduler implementation that runs work item

# commands asynchronously. The commands run in separate

# processes, up to some specified maximum process count.

### Do not edit these imports ###

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import threading
import traceback
from distutils.spawn import find_executable
import six.moves.urllib.parse as parse

from pdg import Scheduler, scheduleResult, tickResult, ServiceError
from pdg import TypeRegistry
from pdg.job.callbackserver import CallbackServerMixin
from pdg.scheduler import PyScheduler, convertEnvMapToUTF8
from pdg.staticcook import StaticCookMixin
from pdg.utils import expand_vars, print_headless

### Do not edit imports above this line.  This serves as a baseline for future updates to the localscheduler ###

import logging 
from collections import namedtuple 
import re 
from pdg import CookError

sys.path.append(os.path.expandvars("$HFS/houdini/pdg/types/schedulers")) # TODO: Try and remove this if it can be done without producing errors.

from local import LocalScheduler

import pdg
import firehawk_submit as firehawk_submit # Firehawk presubmission utils for multiparm versioning.
import firehawk_read

import firehawk_plugin_loader
pdgkvstore = firehawk_plugin_loader.module_package('pdgkvstore').pdgkvstore
houpdgkvstore = firehawk_plugin_loader.module_package('houpdgkvstore').houpdgkvstore

import firehawk_plugin_loader
firehawk_logger = firehawk_plugin_loader.module_package('submit_logging').submit_logging.FirehawkLogger(debug=10)
firehawk_logger.timed_info(label='firehawk scheduler loaded')
firehawk_logger.debug('test debug logger')

from datetime import datetime

# Replicate the scheduler with a patched method

class FirehawkLocalScheduler(LocalScheduler):
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
            print( 'update kv: {}'.format( kv ) )
            kwargs.update( kv )
        
        kwargs['version'] = 'v'+str( work_item.intAttribValue('version') ).zfill(3)
        kwargs['subindex'] = work_item.batchIndex
        
        print('kvstore kwargs: {}'.format( kwargs ))
        if all( [ x in kwargs for x in required_components ] ): # If all components are available, then stash job data in our kv store.
            key = '{}/{}/{}/{}/{}/{}/{}'.format( kwargs['job'], kwargs['seq'], kwargs['shot'], kwargs['element'], kwargs['variant'], kwargs['version'], kwargs['subindex'] )
            value = {
                'log_uri': { 'value': self.getLogURI(work_item), 'type': 'string'}
            }
            print('write: {}'.format( value ) )
            pdgkvstore.work_item_db_put(key, value) # write value to disk, or a database if available.
                
        self._verboseLog("End presubmit")

        return item_command

    # getting a log can be customised to be based on an ouput path making log aquisition based on past cooks possible

    # def getLogURI(self, work_item):
    #     if work_item.intAttribValue('updated_itemcommand'): # The work item has been scheduled in this session.
    #         log_path = '{}/logs/{}.log'.format(self.tempDir(True), work_item.name)
    #         uri = 'file://' + log_path
    #     else: # we need to aquire the uri from our kv store
    #         json_object = houpdgkvstore.getPdgKvStore(work_item) # attempt to retrieve work item data from kv store if attribs are not available.
    #         if not isinstance(json_object, dict) or len(json_object)==0: # Couldn't retrieve a kvstore for the work item, 
    #             return ''
    #         required_attribs = ['log_uri']
    #         if not isinstance(json_object, dict) or not all( [ x in json_object for x in required_attribs ] ):
    #             return '' # it wasn't possible to retrieve any valid data.
    #         uri = json_object['log_uri']['value']
    #     return uri+'?file/firehawk/log'

    def registerTypes(type_registry): 
         print("Init firehawklocalscheduler schedulers") 
 
