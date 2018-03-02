#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import six
import abc
import json
import logging
import re


@six.add_metaclass(abc.ABCMeta)
class Hook(object):
    """The base for all hooks."""

    def __init__(self, **config):
        """Prepare what's needed by the hook."""
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def filter(self, msg):
        """Finds out whether the hook applies to the message or not.

        Returns: Boolean"""
        self.logger.debug('Filtering msg: %s' % msg)

    def process(self, msg):
        """The actual action covered by the hook."""
        self.logger.debug('Processing msg: %s' % msg.payload)

    def __call__(self, msg):
        if self.filter(msg):
            self.process(msg)


@six.add_metaclass(abc.ABCMeta)
class GerritHook(Hook):
    """Hooks based on Gerrit events."""

    def __init__(self, **config):
        super(GerritHook, self).__init__(**config)
        _topic_filter = ('gerrit/(?P<project_repo>[A-Za-z0-9-_/]+)'
                         '/(?P<event>[A-Za-z0-9-_]+)$')
        self.topic_filter = re.compile(_topic_filter, re.I)

    def filter(self, msg):
        super(GerritHook, self).filter(msg)
        self.logger.debug('Checking topic: %s' % msg.topic)
        if self.topic_filter.match(msg.topic):
            return True
        return False

    def get_data(self, msg):
        project_repo, event = self.topic_filter.match(msg.topic).groups()
        if '/' in project_repo:
            project, repo = project_repo.split('/')
        else:
            project = project_repo
            repo = project_repo
        payload = json.loads(msg.payload)
        return project, repo, payload, event

    def process(self, msg):
        try:
            project, repo, payload, event = self.get_data(msg)
        except Exception as e:
            self.logger.exception(
                'Could not translate %s: e' % (msg.payload, e))
            return
        event_method = 'on_' + event.replace('-', '_')
        getattr(self, event_method,
                self.on_undefined(event))(project=project,
                                          repo=repo,
                                          payload=payload)

    # Catch-all event method
    def on_undefined(self, event):

        def x(**kwargs):
            self.logger.debug(
                '"%s" event hook triggered with %r' % (event, kwargs))

        return x
