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

import re

from firehooks.hooks import base


class SFZuulAutoholdHook(base.GerritHook):
    """Hook used to allow authorized users to set a nodeset on hold
    automatically in case of a job failure on a given Gerrit review.

    The hook is triggered by commenting on a review, following this pattern:

    autohold <job name> on <tenant> [hold for <duration>]"""
    def __init__(self, **config):
        super(SFZuulAutoholdHook, self).__init__(**config)
        self.autohold_regex = re.compile(
            r'autohold (?P<job>.+?) on (?P<tenant>.+)'
            r'(\s+hold for (?P<duration>\d+) (?P<unit>hour|minute))?',
            re.I)

    def on_comment_added(self, project, repo, payload):
        super(SFZuulAutoholdHook, self).on_undefined('comment-added')(
            project=project, repo=repo, payload=payload)
        comment = payload.get('comment', '')
        # patch_number = payload.get('change', {}).get('number')
        # current_revision = payload.get('patchSet', {}).get('number')
        # author = payload.get('author', {}).get('username')
        # changeid = payload.get('change', {}).get('id')
        if self.autohold_regex.search(comment):
            self.logger.debug('autohold query matched')
