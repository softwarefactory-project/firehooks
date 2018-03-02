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


from unittest import TestCase

import json
import mock

from firehooks.hooks import base
from firehooks.hooks import trackers
from firehooks.hooks import zuul


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class FakeResponse:
    def __init__(self, status_code, text=None):
        self.status_code = status_code
        self.text = text or ''


class TestBaseHook(TestCase):
    def test_simple_hook(self):

        class DummyHook(base.Hook):
            x = 17

            def filter(self, msg):
                return msg > 2

            def process(self, msg):
                self.x = msg

        dummy = DummyHook()
        self.assertTrue(dummy.filter(4))
        dummy(0)
        self.assertEqual(17, dummy.x)
        dummy(4)
        self.assertEqual(4, dummy.x)


class TestGerritHook(TestCase):
    def test_filter(self):
        ghook = base.GerritHook()
        msg = FakeMessage('just/a/random/topic', '{"a": "b"}')
        self.assertFalse(ghook.filter(msg))
        msg = FakeMessage('gerrit/myproject/comment-added', '{"a": "b"}')
        self.assertTrue(ghook.filter(msg))

    def test_process(self):
        """test the event dispatcher"""

        class TestGH(base.GerritHook):
            last_call = None

            def on_fake_event(self, project, repo, payload):
                self.last_call = project, repo, payload

            def on_undefined(self, event):

                def x(**kwargs):
                    self.last_call = event, kwargs

                return x

        tgh = TestGH()
        msg = FakeMessage('gerrit/myproject/comment-added', '{"a": "b"}')
        tgh(msg)
        self.assertEqual(2, len(tgh.last_call))
        event, kwargs = tgh.last_call
        self.assertEqual('comment-added', event)
        self.assertEqual('myproject', kwargs['project'])
        self.assertEqual('myproject', kwargs['repo'])
        self.assertEqual({"a": "b"}, kwargs['payload'])

        msg = FakeMessage('gerrit/myproject/myrepo/comment-added',
                          '{"a": "b"}')
        tgh(msg)
        self.assertEqual(2, len(tgh.last_call))
        event, kwargs = tgh.last_call
        self.assertEqual('comment-added', event)
        self.assertEqual('myproject', kwargs['project'])
        self.assertEqual('myrepo', kwargs['repo'])
        self.assertEqual({"a": "b"}, kwargs['payload'])

        msg = FakeMessage('gerrit/myproject/myrepo/fake-event',
                          '{"a": "b"}')
        tgh(msg)
        self.assertEqual(3, len(tgh.last_call))
        project, repo, payload = tgh.last_call
        self.assertEqual('myproject', project)
        self.assertEqual('myrepo', repo)
        self.assertEqual({"a": "b"}, payload)


class TestIssueTrackerHooks(TestCase):

    def test_filter(self):
        bith = trackers.BaseIssueTrackerHook(project='myproject')
        msg = FakeMessage('gerrit/myproject/myrepo/comment-added',
                          '{"a": "b"}')
        f = bith.filter(msg)
        self.assertTrue(f)
        msg = FakeMessage('gerrit/myproject/comment-added',
                          '{"a": "b"}')
        f = bith.filter(msg)
        self.assertTrue(f)
        msg = FakeMessage('gerrit/myotherproject/myrepo/comment-added',
                          '{"a": "b"}')
        f = bith.filter(msg)
        self.assertFalse(f)
        msg = FakeMessage('some/unrelated/topic',
                          '{"a": "b"}')
        f = bith.filter(msg)
        self.assertFalse(f)


class TestTaigaHook(TestCase):
    # This is minimal testing, making sure the issues are checked on Taiga.

    def test_patchset_created(self):
        with mock.patch('firehooks.hooks.trackers.TaigaAPI'):
            T = trackers.TaigaItemUpdateHook(auth={'username': 'a',
                                                   'password': 'b'},
                                             project='myproject',
                                             taiga_project='d')
            msg = FakeMessage(
                topic='gerrit/myproject/patchset-created',
                payload=json.dumps(
                    {"change": {"commitMessage": "blah TG-1337",
                                "subject": "a_cool_change",
                                "owner": {"username": "Johnny"},
                                "number": 12,
                                "url": "http://some.url"}}
                )
            )
            self.assertTrue(T.filter(msg))
            with mock.patch.object(T, "get_ref_history"):
                T(msg)
                T.project.get_userstory_by_ref.assert_called_with("1337")

    def test_comment_added(self):
        with mock.patch('firehooks.hooks.trackers.TaigaAPI'):
            T = trackers.TaigaItemUpdateHook(auth={'username': 'a',
                                                   'password': 'b'},
                                             project='myproject',
                                             taiga_project='d')
            msg = FakeMessage(
                topic='gerrit/myproject/comment-added',
                payload=json.dumps(
                    {"change": {"commitMessage": "blah TG-1337",
                                "subject": "a_cool_change",
                                "owner": {"username": "Johnny"},
                                "number": 12,
                                "url": "http://some.url"},
                     "patchSet": {"number": 2},
                     "approvals": [{"type": "Code-Review",
                                    "value": 1}],
                     "author": {"username": "Johnny"}}
                )
            )
            self.assertTrue(T.filter(msg))
            with mock.patch.object(T, "get_ref_history"):
                T(msg)
                T.project.get_userstory_by_ref.assert_called_with("1337")

    def test_comment_added_by_other(self):
        with mock.patch('firehooks.hooks.trackers.TaigaAPI'):
            T = trackers.TaigaItemUpdateHook(auth={'username': 'a',
                                                   'password': 'b'},
                                             project='myproject',
                                             taiga_project='d')
            msg = FakeMessage(
                topic='gerrit/myproject/comment-added',
                payload=json.dumps(
                    {"change": {"commitMessage": "blah TG-1337",
                                "subject": "a_cool_change",
                                "owner": {"username": "Johnny"},
                                "number": 12,
                                "url": "http://some.url"},
                     "patchSet": {"number": 2},
                     "approvals": [{"type": "Code-Review",
                                    "value": 1}],
                     "author": {"username": "Mark"}}
                )
            )
            self.assertTrue(T.filter(msg))
            with mock.patch.object(T, "get_ref_history"):
                T(msg)
                # Not called if the author of CR+1 is not the owner
                self.assertFalse(T.project.get_userstory_by_ref.called)

    def test_change_merged(self):
        with mock.patch('firehooks.hooks.trackers.TaigaAPI'):
            T = trackers.TaigaItemUpdateHook(auth={'username': 'a',
                                                   'password': 'b'},
                                             project='myproject',
                                             taiga_project='d')
            msg = FakeMessage(
                topic='gerrit/myproject/change-merged',
                payload=json.dumps(
                    {"change": {"commitMessage": "blah TG-1337",
                                "subject": "a_cool_change",
                                "owner": {"username": "Johnny"},
                                "number": 12,
                                "url": "http://some.url"}}
                )
            )
            self.assertTrue(T.filter(msg))
            with mock.patch.object(T, "get_ref_history"):
                T(msg)
                T.project.get_userstory_by_ref.assert_called_with("1337")


class TestZuulHook(TestCase):
    def test_autohold(self):
        with mock.patch('firehooks.softwarefactory') as _SF:
            Z = zuul.SFZuulAutoholdHook()
            Z.SF = _SF
            msg = FakeMessage(
                topic='gerrit/myproject/comment-added',
                payload=json.dumps(
                    {"change": {"commitMessage": "blah TG-1337",
                                "subject": "a_cool_change",
                                "owner": {"username": "Johnny"},
                                "number": 12,
                                "url": "http://some.url",
                                "id": "I12345"},
                     "patchSet": {"number": 3},
                     "comment": "hehe\n\n"
                                "autohold run-tests on local",
                     "author": {"username": "Mark"}}
                )
            )
            self.assertTrue(Z.filter(msg))
            _SF.post_as.return_value = FakeResponse(200)
            Z(msg)
            _SF.post_as.assert_called_with(
                "Mark",
                "/v2/zuul/admin/local/myproject/run-tests/autohold",
                json={'change': 12,
                      'reason': 'Requested by Mark',
                      'count': 1},
                headers={'Content-Type': 'application/json'})
            _SF.comment_on_review.assert_called_with(
                "I12345", 3, "Autohold successfully set.")
