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


import paho.mqtt.client as mqtt
import argparse
import logging
from stevedore import driver
from . import config
import sys


LOGGER = logging.getLogger('firehooks')


def load_hook(conf, name, SF):
    hook_class = driver.DriverManager(namespace='firehooks.hooks',
                                      name=name,
                                      invoke_on_load=False).driver
    hook = hook_class(**conf)
    LOGGER.debug('Hook "%s" loaded' % name)
    return hook


# Assign a callback for connect
def on_connect(client, userdata, flags, rc):
    LOGGER.info("MQTT: Connected with result code "+str(rc))
    client.subscribe("#")


def on_message(hooks):
    def _on_message(client, userdata, msg):
        LOGGER.debug(msg.topic)
        # TODO find a way to parallelize this. multiprocessing does not work
        # due to pickling issues
        for h in hooks:
            try:
                h(msg)
            except Exception as e:
                msg = 'Unknown error running hook %s: %s'
                LOGGER.exception(msg % (h.__class__.__name__, e))
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
    parser.add_argument('--config', '-c', help='The configuration file')
    parser.add_argument('--verbose', '-v', default=False, action='store_true',
                        help='Run in debug mode')

    args = parser.parse_args()
    if not args.config:
        sys.exit('Please specify a path to a valid configuration file.')
    conf = config.Config(args.config)
    if args.verbose:
        console.setLevel(logging.DEBUG)
    else:
        loglevel = conf.config.get('logging', {}).get('level', 'INFO')
        LOGGER.setLevel(getattr(logging, loglevel))
        console.setLevel(getattr(logging, loglevel))
        LOGGER.info('logging set to %s' % loglevel)

    # Broker
    broker = conf.config.get('broker', {}).get('url')
    port = conf.config.get('broker', {}).get('port')

    # hooks
    hooks = []
    hks_conf = conf.config.get('hooks', {})
    for hook_name in hks_conf:
        for hook_config in hks_conf[hook_name]:
            h = load_hook(hook_config, hook_name)
            hooks.append(h)

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
