# OCHLERO

Ochlero is a script that monitors the systemd journal for specific events that
trigger publications on an MQTT queue.

"Ochlero" comes from "Ochlerotatus Triseriatus", a species of tree hole breeding
mosquitoes (https://en.wikipedia.org/wiki/Ochlerotatus_triseriatus), ie
mosquitoes that like logs...

## Running and testing

Ochlero is tested against and runs on python 2.7 and python 3.5.

With python 2.x you need to install the systemd and mqtt wrappers on your system.
On CentOS or Fedora, you can do so with the following command (extra repositories
such as EPEL might need to be activated):

```bash
sudo yum install systemd-python python-paho-mqtt
```

This is necessary due to a problem in the PyPI version of the systemd wrapper.

With python 3.5, running

```bash
pip install -r requiremenits.txt
```

should be enough.

To start ochlero, simply run

```bash
ochlero -c /path/to/config/file.yaml
```

## The configuration file

Ochlero uses a yaml configuration file to define the mosquitto service to publish
to, and the processes and events to look for. See etc/ochlero.yaml for an example.

### Writing patterns

When ochlero is running, it will attempt to match log lines associated with a given
unit or command against patterns. A pattern is basically a regular expression.
Please refer to python's documentation for details on syntax, for example
https://docs.python.org/2/howto/regex.html

Most of the time, you will want to pick some information from the log line and
publish it to MQTT. These elements of interest are defined in the pattern like
bash variables, ie "${ELEMENTNAME}. You must then define the regex matching for
each variable in the directive "where" of your event. For example:

```yaml
events
  - name: hello world
    pattern: "hello, my name is ${PERSON}"
    where:
      PERSON: [A-Za-z]+
    publish: "Hi ${PERSON}!"
```

A log message like "Hello, my name is Mark" will publish the message "Hi Mark!".

### Predefined substitution types

To make it easier for you, some substitutions are included in ochlero so you don't
have to write annoying regular expressions:

* \_ALPHANUMERIC\_
* \_INT\_
* \_URL\_
* \_EMAIL\_
* \_IPv4\_
* \_SYSLOGTIMESTAMP\_

### Writing messages to publish

Variables can be reused as they are in publish messages (see previous example). Some
predefined "macros" can also be used:

* \_EPOCH\_ : the Unix Epoch timestamp at parsing time.

## Contributing

Ochlero is developped in **Software Factory** and contributions follow a review workflow.

To contribute:

1. Log in once to Software Factory at https://softwarefactory-project.io
2. Set up your ssh key in Gerrit's settings page
3. Clone the project:
```bash
git clone ssh://<your_username>@softwarefactory-project.io:29418/software-factory/ochlero.git
```
4. Set up git review
```bash
cd ochlero && git review -s
```
5. Work on your feature, make a commit, then send the review
```bash
git commit -m'my feature' && git review
```
