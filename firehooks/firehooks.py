#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Red Hat
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


from taiga import TaigaAPI
from taiga.exceptions import TaigaRestException
from taiga.models import Issue as TaigaIssue
from taiga.models import Task as TaigaTask
from taiga.models import UserStory as TaigaUserStory

import paho.mqtt.client as mqtt
import argparse
import logging
import re
import json
import sys
import yaml


LOGGER = logging.getLogger('firehooks')


# Assign a callback for connect
def on_connect(client, userdata, flags, rc):
    LOGGER.info("MQTT: Connected with result code "+str(rc))
    client.subscribe("#")


def debug_event(event):
    def _(**kwargs):
        LOGGER.debug('"%s" event hook triggered with %r' % (event, kwargs))
    return _


class RefException(Exception):
    """Triggered when an issue is not found on the tracker."""


class Hook(object):
    _regex = '(?!issue|task|story):\s*(?P<issue>\d+)'

    def __init__(self, **config):
        self.regex = re.compile(self._regex, re.I + re.M)

    def on_patchset_created(self, project, repo, payload):
        debug_event('patchset-created')(project=project,
                                        repo=repo,
                                        payload=payload)

    def on_comment_added(self, project, repo, payload):
        debug_event('comment-added')(project=project,
                                     repo=repo,
                                     payload=payload)

    def on_change_merged(self, project, repo, payload):
        debug_event('change-merged')(project=project,
                                     repo=repo,
                                     payload=payload)


class TaigaHook(Hook):
    # This regex mimics taiga.io's github support
    _regex = 'TG-(?P<issue>\d+)\s*(?P<status>#[a-zA-Z-]+)?'

    def __init__(self, **config):
        super(TaigaHook, self).__init__(**config)
        self.api = TaigaAPI()
        self.api.auth(username=config['username'], password=config['password'])
        self.project = self.api.projects.get_by_slug(config['project'])

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
        commit_msg = payload.get('change', {}).get('commitMessage')
        subject = payload.get('change', {}).get('subject')
        author = payload.get('change', {}).get('owner', {}).get('username') or\
            'UNKNOWN'
        patch_number = payload.get('change', {}).get('number')
        url = payload.get('change', {}).get('url')
        # prepare error msg
        m = 'status "%s" not found, using default status'
        for issue_id, status in self.regex.findall(commit_msg):
            ref = None
            # status irrelevant here, patchset creation sets issue/task/US as
            # in progress by default
            status = 'in-progress'
            try:
                ref = self.find_by_ref(issue_id)
            except RefException as e:
                LOGGER.error(e)
            if ref:
                comment = "%s created patch [#%s: %s](%s) on repository %s."
                comment = comment % (author, patch_number,
                                     subject, url, repo)
                # does the ref already mention this patch ?
                ref_history = self.get_ref_history(ref)
                if any([comment in u.get('comment', '')
                        for u in ref_history]):
                    LOGGER.debug('Ref #%s up to date, skipping' % ref.id)
                    continue
                ref.add_comment(comment)
                LOGGER.debug(comment)
                if isinstance(ref, TaigaIssue):
                    s = self.project.issue_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        LOGGER.debug(m % status)
                        status = self.project.issue_statuses.get(
                            slug='in-progress').id
                elif isinstance(ref, TaigaTask):
                    s = self.project.task_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        LOGGER.debug(m % status)
                        status = self.project.task_statuses.get(
                            slug='in-progress').id
                elif isinstance(ref, TaigaUserStory):
                    s = self.project.us_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        LOGGER.debug(m % status)
                        status = self.project.us_statuses.get(
                            slug='in-progress').id
                else:
                    # ?!
                    status = None
                if status:
                    ref.status = status
                ref.update()
                LOGGER.debug('ref #%s updated' % issue_id)
        super(TaigaHook, self).on_patchset_created(project, repo, payload)

    def on_comment_added(self, project, repo, payload):
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
            for issue_id, status in self.regex.findall(commit_msg):
                # status irrelevant here
                ref = None
                try:
                    ref = self.find_by_ref(issue_id)
                except RefException as e:
                    LOGGER.error(e)
                if ref:
                    comment = "Patch [#%s,%s: %s](%s) is ready for review."
                    ref.add_comment(comment % (patch_number, patchset,
                                               subject, url))
                    LOGGER.debug(comment % (patch_number, patchset,
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
        super(TaigaHook, self).on_comment_added(project, repo, payload)

    def on_change_merged(self, project, repo, payload):
        commit_msg = payload.get('change', {}).get('commitMessage')
        subject = payload.get('change', {}).get('subject')
        patch_number = payload.get('change', {}).get('number')
        url = payload.get('change', {}).get('url')
        # prepare error msg
        m = 'status "%s" not found, using default status'
        for issue_id, status in self.regex.findall(commit_msg):
            ref = None
            # remove leading '#'
            status = status[1:].lower()
            LOGGER.debug('- status: %s' % status)
            try:
                ref = self.find_by_ref(issue_id)
            except RefException as e:
                LOGGER.error(e)
            if ref:
                comment = "patch [#%s: %s](%s) was merged."
                ref.add_comment(comment % (patch_number,
                                           subject, url))
                LOGGER.debug(comment % (patch_number,
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
                        LOGGER.debug(m % status)
                        status = self.project.issue_statuses.get(
                            slug='closed').id
                elif isinstance(ref, TaigaTask):
                    s = self.project.task_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        LOGGER.debug(m % status)
                        status = self.project.task_statuses.get(
                            slug='closed').id
                elif isinstance(ref, TaigaUserStory):
                    s = self.project.us_statuses.get(slug=status)
                    if s:
                        status = s.id
                    else:
                        LOGGER.debug(m % status)
                        status = self.project.us_statuses.get(
                            slug='in-progress').id
                else:
                    # ?!
                    status = None
                if status:
                    ref.status = status
                ref.update()
                LOGGER.debug('ref #%s updated' % issue_id)
        super(TaigaHook, self).on_change_merged(project, repo, payload)


def on_message(hooks):
    # TODO check if gerrit has rules on this
    _filter = ('gerrit/(?P<project_repo>[A-Za-z0-9-_/]+)'
               '/(?P<event>[A-Za-z0-9-_]+)$')
    filter = re.compile(_filter, re.I)

    def _on_message(client, userdata, msg):
        LOGGER.debug(msg.topic)
        if filter.match(msg.topic):
            project_repo, event = filter.match(msg.topic).groups()
            if '/' in project_repo:
                project, repo = project_repo.split('/')
            else:
                project = project_repo
                repo = project_repo
            try:
                jmsg = json.loads(msg.payload)
            except Exception as e:
                LOGGER.error('could not translate %s: e' % (msg.payload, e))
                return
            event = 'on_' + event.replace('-', '_')
            if project in hooks:
                getattr(hooks[project], event, debug_event(event))(
                    project=project,
                    repo=repo,
                    payload=jmsg)
    return _on_message


def main():
    console = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    LOGGER.addHandler(console)

    broker = None
    port = None
    hooks = {}

    parser = argparse.ArgumentParser(description="Firehooks")
    parser.add_argument('--password', '-p', metavar='XXX',
                        help="SFBot0's password")
    parser.add_argument('--project', '-P', metavar='morucci-software-factory',
                        help="the taiga project to synchronize")
    parser.add_argument('--verbose', '-v', default=False, action='store_true',
                        help='Run in debug mode')

    args = parser.parse_args()
    if not args.verbose and not args.password and not args.project:
        with open('/etc/firehooks/default.yaml', 'r') as default_conf:
            conf = yaml.load(default_conf)
            # logging
            loglevel = conf.get('logging', {}).get('level', 'INFO')
            LOGGER.setLevel(getattr(logging, loglevel))
            console.setLevel(getattr(logging, loglevel))
            LOGGER.info('logging set to %s' % loglevel)
            # broker
            broker = conf.get('broker', {}).get('url')
            port = conf.get('broker', {}).get('port')
            # hooks
            projects = conf.get('projects', [])
            for u in projects:
                prj = u.keys()[0]
                auth = u[prj].get('TaigaIO', {}).get('auth', {})
                username = auth.get('user')
                pw = auth.get('password')
                taiga_project = u[prj].get('TaigaIO', {}).get('project')
                hooks[prj] = TaigaHook(username=username,
                                       project=taiga_project,
                                       password=pw)

    else:
        if args.verbose:
            console.setLevel(logging.DEBUG)
        else:
            console.setLevel(logging.INFO)
        if not args.password or not args.project:
            sys.exit('Missing argument(s)')
        username = 'sfbot0'
        pw = args.password
        taiga_project = args.project
    if not broker:
        broker = "softwarefactory-project.io"
    if not port:
        port = 1883

    # Setup hooks
    if not hooks:
        hooks = {'software-factory': TaigaHook(username=username,
                                               project=taiga_project,
                                               password=pw),
                 'DLRN': TaigaHook(username=username,
                                   project=taiga_project,
                                   password=pw),
                 'repoxplorer': TaigaHook(username=username,
                                          project=taiga_project,
                                          password=pw), }

    # Setup the MQTT client
    client = mqtt.Client()
    client.connect(broker, port, 60)

    # Callbacks
    client.on_connect = on_connect
    client.on_message = on_message(hooks)

    # Loop the client forever
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        LOGGER.info('Manual interruption, bye!')
        sys.exit(2)


if __name__ == '__main__':
    main()
