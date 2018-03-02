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

from taiga import TaigaAPI
from taiga.exceptions import TaigaRestException
from taiga.models import Issue as TaigaIssue
from taiga.models import Task as TaigaTask
from taiga.models import UserStory as TaigaUserStory

from firehooks.hooks import base


class RefException(Exception):
    """Triggered when an issue is not found on the tracker."""


class BaseIssueTrackerHook(base.GerritHook):
    """Generic Issue Tracker Hook. It will trigger on gerrit events
    related to projects matching a specific regular expression."""

    def __init__(self, **config):
        super(BaseIssueTrackerHook, self).__init__(**config)
        self.project_regex = re.compile(config['project'], re.I)
        self.tracker_regex = re.compile(
            'Closes: #?(?P<issue>\d+)', re.I)

    def filter(self, msg):
        if super(BaseIssueTrackerHook, self).filter(msg):
            try:
                project, repo, payload, event = self.get_data(msg)
            except Exception as e:
                self.logger.exception(
                    'Could not translate %s: e' % (msg, e))
                return False
            if self.project_regex.match(project):
                return True
        return False

    def on_patchset_created(self, project, repo, payload):
        self.logger.debug('processing "patchset-created" event')

    def on_comment_added(self, project, repo, payload):
        self.logger.debug('processing "comment-added" event')

    def on_change_merged(self, project, repo, payload):
        self.logger.debug('processing "comment-added" event')


class TaigaItemUpdateHook(BaseIssueTrackerHook):
    """A hook interacting with a project on a Taiga board.

    The hook looks for the following pattern in commit messages:
    "TG-<id> [<status>]"

    The hook will update the item's status as the gerrit review evolves."""

    def __init__(self, **config):
        super(TaigaItemUpdateHook, self).__init__(**config)
        self.api = TaigaAPI()
        self.api.auth(username=config['auth']['username'],
                      password=config['auth']['password'])
        self.project = self.api.projects.get_by_slug(config['taiga_project'])
        self.tracker_regex = re.compile(
            'TG-(?P<issue>\d+)\s*(?P<status>#[a-zA-Z-]+)?', re.I)

    def find_by_ref(self, ref):
        try:
            return self.project.get_userstory_by_ref(ref)
        except TaigaRestException:
            pass
        try:
            return self.project.get_issue_by_ref(ref)
        except TaigaRestException:
            pass
        try:
            return self.project.get_task_by_ref(ref)
        except TaigaRestException:
            raise RefException('reference #%s not found' % ref)

    def get_ref_history(self, ref):
        if isinstance(ref, TaigaIssue):
            return self.api.history.issue.get(ref.id)
        elif isinstance(ref, TaigaTask):
            return self.api.history.task.get(ref.id)
        elif isinstance(ref, TaigaUserStory):
            return self.api.history.user_story.get(ref.id)
        else:
            raise RefException('reference #%s not supported' % ref)

    def on_patchset_created(self, project, repo, payload):
        super(TaigaItemUpdateHook, self).on_patchset_created(
            project, repo, payload)
        commit_msg = payload.get('change', {}).get('commitMessage')
        subject = payload.get('change', {}).get('subject')
        author = payload.get('change', {}).get('owner', {}).get('username') or\
            'UNKNOWN'
        patch_number = payload.get('change', {}).get('number')
        url = payload.get('change', {}).get('url')
        # prepare error msg
        m = 'status "%s" not found, using default status'
        for issue_id, status in self.tracker_regex.findall(commit_msg):
            ref = None
            # status irrelevant here, patchset creation sets issue/task/US as
            # in progress by default
            status = 'in-progress'
            try:
                ref = self.find_by_ref(issue_id)
            except RefException as e:
                self.logger.error(e)
            if ref:
                comment = "%s created patch [#%s: %s](%s) on repository %s."
                comment = comment % (author, patch_number,
                                     subject, url, repo)
                # does the ref already mention this patch ?
                ref_history = self.get_ref_history(ref)
                if any([comment in u.get('comment', '')
                        for u in ref_history]):
                    self.debug('Ref #%s up to date, skipping' % ref.id)
                    continue
                ref.add_comment(comment)
                self.logger.debug(comment)
                if isinstance(ref, TaigaIssue):
                    s = self.project.issue_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.issue_statuses.get(
                            slug='in-progress').id
                elif isinstance(ref, TaigaTask):
                    s = self.project.task_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.task_statuses.get(
                            slug='in-progress').id
                elif isinstance(ref, TaigaUserStory):
                    s = self.project.us_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.us_statuses.get(
                            slug='in-progress').id
                else:
                    # ?!
                    status = None
                if status:
                    ref.status = status
                ref.update()
                self.logger.debug('ref #%s updated' % issue_id)

    def on_comment_added(self, project, repo, payload):
        super(TaigaItemUpdateHook, self).on_comment_added(
            project, repo, payload)
        commit_msg = payload.get('change', {}).get('commitMessage')
        subject = payload.get('change', {}).get('subject')
        patch_number = payload.get('change', {}).get('number')
        patchset = payload.get('patchSet', {}).get('number')
        url = payload.get('change', {}).get('url')
        approvals = payload.get('approvals', [])
        owner = payload.get('change', {}).get('owner', {}).get('username') or\
            'UNKNOWN'
        author = payload.get('author', {}).get('username') or 'UNKNOWN'
        _test = [a.get('type') == 'Code-Review' and int(a.get('value', 0)) > 0
                 for a in approvals]
        ready_for_review = (any(_test) and owner == author)
        if ready_for_review:
            for issue_id, status in self.tracker_regex.findall(commit_msg):
                # status irrelevant here
                ref = None
                try:
                    ref = self.find_by_ref(issue_id)
                except RefException as e:
                    self.logger.error(e)
                if ref:
                    comment = "Patch [#%s,%s: %s](%s) is ready for review."
                    ref.add_comment(comment % (patch_number, patchset,
                                               subject, url))
                    self.logger.debug(comment % (patch_number, patchset,
                                                 subject, url))
                # by default issues and tasks are ready for review with one
                # patch, User stories are set as in progress and expected to be
                # closed manually or by explicitly setting "closed" if several
                # patches are needed.
                if isinstance(ref, TaigaIssue):
                    status = self.project.issue_statuses.get(
                        slug='ready-for-review').id
                elif isinstance(ref, TaigaTask):
                    status = self.project.task_statuses.get(
                        slug='ready-for-review').id
                elif isinstance(ref, TaigaUserStory):
                    status = self.project.us_statuses.get(
                        slug='in-progress').id
                else:
                    # ?!
                    status = None
                if status:
                    ref.status = status
                    ref.update()
                    self.logger.debug("#%s set to '%s'" % (issue_id, status))

    def on_change_merged(self, project, repo, payload):
        super(TaigaItemUpdateHook, self).on_change_merged(
            project, repo, payload)
        commit_msg = payload.get('change', {}).get('commitMessage')
        subject = payload.get('change', {}).get('subject')
        patch_number = payload.get('change', {}).get('number')
        url = payload.get('change', {}).get('url')
        # prepare error msg
        m = 'status "%s" not found, using default status'
        for issue_id, status in self.tracker_regex.findall(commit_msg):
            ref = None
            # remove leading '#'
            status = status[1:].lower()
            self.logger.debug('- status: %s' % status)
            try:
                ref = self.find_by_ref(issue_id)
            except RefException as e:
                self.logger.error(e)
            if ref:
                comment = "patch [#%s: %s](%s) was merged."
                ref.add_comment(comment % (patch_number,
                                           subject, url))
                self.logger.debug(comment % (patch_number,
                                             subject, url))
                # by default issues and tasks are closed with one patch,
                # User stories are set as in progress and expected to be
                # closed manually or by explicitly setting "#closed" in the
                # last patch's commit message.
                if isinstance(ref, TaigaIssue):
                    s = self.project.issue_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.issue_statuses.get(
                            slug='closed').id
                elif isinstance(ref, TaigaTask):
                    s = self.project.task_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.task_statuses.get(
                            slug='closed').id
                elif isinstance(ref, TaigaUserStory):
                    s = self.project.us_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        self.logger.debug(m % status)
                        status = self.project.us_statuses.get(
                            slug='in-progress').id
                else:
                    # ?!
                    status = None
                if status:
                    ref.status = status
                ref.update()
                self.logger.debug('ref #%s updated' % issue_id)
