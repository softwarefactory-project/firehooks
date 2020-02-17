%global         sum Firehooks, a Software Factory or OpenStack-style Firehose consumer used to trigger complex actions on specific events

Name:           firehooks
Version:        0.0.0
Release:        4%{?dist}
Summary:        %{sum}

License:        ASL 2.0
URL:            https://softwarefactory-project.io/r/p/software-factory/%{name}
Source0: HEAD.tgz

BuildArch:      noarch

Requires:       python3-paho-mqtt
Requires:       python3-pyyaml
Requires:       python3-taiga
Requires:       python3-requests

Buildrequires:  python3-devel
Buildrequires:  python3-setuptools
Buildrequires:  python3-pbr
Buildrequires:  python3-nose
Buildrequires:  python3-mock
Buildrequires:  git
Buildrequires:  python3-pyyaml
Buildrequires:  python3-paho-mqtt
BuildRequires:  python3-taiga
BuildRequires:  python3-requests
BuildRequires:  python3-dateutil

%description
an MQTT bus consumer used to trigger complex actions on specific events

%prep
%autosetup -n %{name}-%{version}

%build
# init git for pbr
git init
%{__python3} setup.py build

%install
%{__python3} setup.py install --skip-build --root %{buildroot}
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
%{python3_sitelib}/*
%{_bindir}/*
%{_unitdir}/*
%config(noreplace) %{_sysconfdir}/*

%changelog
* Mon Feb 17 2020 Matthieu Huin <mhuin@redhat.com> - 0.0.0-4
- Move to python3

* Tue Mar 27 2018 Matthieu Huin <mhuin@redhat.com> - 0.0.0-3
- Reflect code refactor

* Thu Dec 14 2017 Tristan Cacqueray <tdecacqu@redhat.com> - 0.0.0-2
- Add missing request build requirement

* Wed Nov 29 2017 Matthieu Huin <mhuin@redhat.com> - 0.0.0-1
- Initial package
