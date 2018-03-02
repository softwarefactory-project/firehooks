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
            'autohold (?P<job>.+?) on (?P<tenant>.+)'
            '(\s+hold for (?P<duration>\d+) (?P<unit>hour|minute))?',
            re.I)

    def on_comment_added(self, project, repo, payload):
        super(SFZuulAutoholdHook, self).on_undefined('comment-added')(
            project=project, repo=repo, payload=payload)
        comment = payload.get('comment', '')
        patch_number = payload.get('change', {}).get('number')
        current_revision = payload.get('patchSet', {}).get('number')
        author = payload.get('author', {}).get('username')
        changeid = payload.get('change', {}).get('id')
        if self.autohold_regex.search(comment):
            raw_args = self.autohold_regex.search(comment).groupdict()
            zuul_project = project
            if project != repo:
                zuul_project = project + '/' + repo
            url_args = {'tenant': raw_args['tenant'],
                        'job': raw_args['job'],
                        'project': zuul_project}
            json_args = {'change': patch_number,
                         'reason': 'Requested by %s' % author,
                         'count': 1}
            url = '/v2/zuul/admin/%(tenant)s/%(project)s/%(job)s/autohold'
            headers = {'Content-Type': 'application/json'}
            response = self.SF.post_as(author,
                                       url % url_args,
                                       json=json_args,
                                       headers=headers)
            self.logger.debug(
                'autohold query returned: %s' % response.status_code)
            self.logger.debug(
                'autohold query returned: %s' % response.text)
            if response.status_code < 400:
                msg = 'Autohold successfully set.'
                self.SF.comment_on_review(changeid, current_revision, msg)
            elif response.status_code == 401:
                msg = 'Autohold is not allowed for user %s.' % author
                self.SF.comment_on_review(changeid, current_revision, msg)
            elif response.status_code == 404:
                msg = 'Job and/or tenant not found.'
                self.SF.comment_on_review(changeid, current_revision, msg)
            else:
                msg = ("Unkwown error while attempting autohold, "
                       "please contact an administrator.")
                self.SF.comment_on_review(changeid, current_revision, msg)
