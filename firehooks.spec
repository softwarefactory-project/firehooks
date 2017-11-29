%global         sum Firehooks, a Software Factory or OpenStack-style Firehose consumer used to trigger complex actions on specific events

Name:           firehooks
Version: 0.0.0
Release:        1%{?dist}
Summary:        %{sum}

License:        ASL 2.0
URL:            https://softwarefactory-project.io/r/p/software-factory/%{name}
Source0: HEAD.tgz

BuildArch:      noarch

Requires:       python-paho-mqtt
Requires:       PyYAML
Requires:       python-taiga

Buildrequires:  python2-devel
Buildrequires:  python-setuptools
Buildrequires:  python2-pbr
Buildrequires:  python-nose
Buildrequires:	python-mock
Buildrequires:  git
Buildrequires:	PyYAML
Buildrequires:	python-paho-mqtt
BuildRequires:  python-taiga

%description
an MQTT bus consumer used to trigger complex actions on specific events

%prep
%autosetup -n %{name}-%{version}

%build
# init git for pbr
git init
%{__python2} setup.py build

%install
%{__python2} setup.py install --skip-build --root %{buildroot}
install -p -D -m 644 firehooks.service %{buildroot}/%{_unitdir}/%{name}.service
mkdir -p %{buildroot}/%{_sysconfdir}/
install -p -D -m 644 etc/default.yaml %{buildroot}/%{_sysconfdir}/%{name}/default.yaml

%check
nosetests -v

%pre
getent group firehooks >/dev/null || groupadd -r firehooks
getent passwd firehooks >/dev/null || \
useradd -r -g firehooks -G firehooks -d /usr/bin/firehooks -s /sbin/nologin \
-c "firehooks daemon" firehooks
exit 0

%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun %{name}.service

%files -n firehooks
%{python2_sitelib}/*
%{_bindir}/*
%{_unitdir}/*
%config(noreplace) %{_sysconfdir}/*

%changelog
* Wed Nov 29 2017 Matthieu Huin <mhuin@redhat.com> - 0.0.0-1
- Initial package
