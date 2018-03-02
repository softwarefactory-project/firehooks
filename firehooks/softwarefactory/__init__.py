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


import requests
from requests.auth import HTTPBasicAuth
from pysflib import sfauth
import logging


class SoftwareFactory(object):
    """Used by hooks to interact with an instance of Software Factory"""

    def __init__(self, **config):
        self.config = config
        # used for direct API calls to services like gerrit, as the service
        # user
        self.user = config['auth']['user']
        self.password = config['auth']['password']
        self.sf_base_url = config['url']
        # used for calls to manageSF API on behalf of another user
        self.managesf_endpoint = config['managesf']
        self.gerrit_endpoint = config['gerrit']
        self.logger = logging.getLogger('firehooks')
        # Default value, will change with next release of SF
        self._apikey = "password"
        self.verify = config.get('verify', False)

    @property
    def apikey(self):
        # since the api key can change anytime, we need to always validate it
        resp = requests.head(self.gerrit_endpoint + "accounts/self/",
                             auth=HTTPBasicAuth(self.user, self._apikey),
                             allow_redirects=False)
        if resp.status_code >= 300:
            c = sfauth.get_cookie(self.sf_base_url, self.user, self.password,
                                  verify=False)
            key_get = requests.get(self.sf_base_url + '/auth/apikey',
                                   verify=self.verify,
                                   cookies={'auth_pubtkt': c})
            if key_get.status_code == 404:
                # Create a key
                key_get = requests.post(self.sf_base_url + '/auth/apikey',
                                        verify=self.verify,
                                        cookies={'auth_pubtkt': c})
            self._apikey = key_get.json()['api_key']
        return self._apikey

    def _fetch_as(self, verb, user, url_end, **kwargs):
        headers = {}
        url = self.managesf_endpoint + url_end
        if 'headers' in kwargs:
            headers = kwargs['headers']
        headers['X-Remote-User'] = user
        kwargs['headers'] = headers
        return getattr(requests, verb)(url, **kwargs)

    def get_as(self, user, url_end, **kwargs):
        return self._fetch_as('get', user, url_end, **kwargs)

    def put_as(self, user, url_end, **kwargs):
        return self._fetch_as('put', user, url_end, **kwargs)

    def post_as(self, user, url_end, **kwargs):
        return self._fetch_as('post', user, url_end, **kwargs)

    def delete_as(self, user, url_end, **kwargs):
        return self._fetch_as('delete', user, url_end, **kwargs)

    def comment_on_review(self, changeid, revision, comment):
        reviewInput = {'message': comment}
        url_end = "changes/%s/revisions/%s/review" % (changeid, revision)
        self.logger.debug(self.gerrit_endpoint + url_end)
        resp = requests.post(self.gerrit_endpoint + url_end,
                             json=reviewInput,
                             auth=HTTPBasicAuth(self.user, self.apikey))
        self.logger.debug(resp.status_code)


# TODO instantiate from config

SF = None
