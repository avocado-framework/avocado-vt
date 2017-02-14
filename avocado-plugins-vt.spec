%global modulename avocado
%if ! 0%{?commit:1}
 %define commit e1c20088823d8480a8eff6f9c16fb77e1dd59301
%endif
%global shortcommit %(c=%{commit}; echo ${c:0:7})

Summary: Avocado Virt Test Plugin
Name: avocado-plugins-vt
Version: 46.0
Release: 0%{?dist}
License: GPLv2
Group: Development/Tools
URL: http://avocado-framework.readthedocs.org/
Source0: https://github.com/avocado-framework/%{name}/archive/%{commit}/%{name}-%{version}-%{shortcommit}.tar.gz
BuildRequires: python2-devel, python-setuptools
BuildArch: noarch
Requires: avocado == %{version}
Requires: python, autotest-framework, p7zip, tcpdump, iproute, iputils, gcc, glibc-headers, python-devel, nc, aexpect, git, python-netaddr

Requires: python-imaging
%if 0%{?el6}
Requires: gstreamer-python, gstreamer-plugins-good, python-simplejson
%else
Requires: pygobject2, gstreamer1-plugins-good
%endif

%description
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.

%prep
%setup -q -n %{name}-%{commit}

%build
%{__python} setup.py build

%install
%{__python} setup.py install --root %{buildroot} --skip-build

%files
%defattr(-,root,root,-)
%dir /etc/avocado
%dir /etc/avocado/conf.d
%config(noreplace)/etc/avocado/conf.d/vt.conf
%doc README.rst LICENSE
%{python_sitelib}/avocado_vt*
%{python_sitelib}/avocado_plugins_vt*
%{python_sitelib}/virttest*
%{_datadir}/avocado-plugins-vt/backends/*
%{_datadir}/avocado-plugins-vt/shared/*
%{_datadir}/avocado-plugins-vt/test-providers.d/*


%changelog
* Tue Feb 14 2017 Cleber Rosa <cleber@redhat.com> - 46.0-0
- New upstream release

* Thu Feb  9 2017 Lukas Doktor <ldoktor@redhat.com> - 45.0-1
- Added python-netaddr to requires

* Tue Jan 17 2017 Cleber Rosa <cleber@redhat.com> - 45.0-0
- New upstream release

* Wed Dec  7 2016 Cleber Rosa <cleber@redhat.com> - 44.0-0
- New upstream version

* Tue Nov  8 2016 Cleber Rosa <cleber@redhat.com> - 43.0-0
- Update to upstream version 43.0

* Mon Oct 10 2016 Cleber Rosa <cleber@redhat.com> - 42.0-0
- Update to upstream version 42.0

* Mon Sep 12 2016 Cleber Rosa <cleber@redhat.com> - 41.0-0
- Update do upstream version 41.0

* Tue Aug 16 2016 Cleber Rosa <cleber@redhat.com> - 40.0-0
- Update to upstream version 40.0

* Tue Jul 26 2016 Cleber Rosa <cleber@redhat.com> - 39.0-0
- Update to upstream version 39.0

* Mon Jul  4 2016 Cleber Rosa <cleber@redhat.com> - 38.0-0
- Update to upstream version 38.0

* Tue Jun 14 2016 Cleber Rosa <cleber@redhat.com> - 37.0-0
- Update to upstream release 37.0

* Mon May  2 2016 Cleber Rosa <cleber@redhat.com> - 35.0-1
- Added git to requires

* Wed Apr 27 2016 Cleber Rosa <cleber@redhat.com> - 35.0-0
- Update to upstream release 35.0

* Mon Mar 21 2016 Cleber Rosa <cleber@redhat.com> - 0.34.0-0
- Update to upstream version 0.34.0

* Tue Feb 23 2016 Cleber Rosa <cleber@redhat.com> - 0.33.0-1
- Require the avocado package of the exact same version

* Wed Feb 17 2016 Cleber Rosa <cleber@redhat.com> - 0.33.0-0
- Update to upstream version 0.33.0

* Wed Jan 20 2016 Cleber Rosa <cleber@redhat.com> - 0.32.0-0
- Update to upstream version 0.32.0

* Wed Dec 23 2015 Cleber Rosa <cleber@redhat.com> - 0.31.0-0
- Update to upstream version 0.31.0

* Thu Nov  5 2015 Cleber Rosa <cleber@redhat.com> - 0.30.0-0
- Update to upstream version 0.30.0

* Wed Oct 7 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.29.0-1
- Update to upstream version 0.29.0

* Mon Sep 21 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.28.1-1
- Update to upstream version 0.28.1

* Wed Sep 16 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.28.0-1
- Update to upstream version 0.28.0

* Wed Sep 2 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.27.0-4
- Add aexpect dependency

* Tue Aug 4 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.27.0-3
- Add video dependencies

* Tue Aug 4 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.27.0-2
- Updated the spec file to require 'nc' instead of 'nmap-ncat'

* Mon Aug 3 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.27.0-1
- Update to upstream version 0.27.0

* Thu Jul 30 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.26.0-2
- Merge with virt-test/updated package dependencies

* Mon Jul 6 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.26.0-1
- Update to upstream version 0.26.0

* Tue Jun 16 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.25.0-1
- Update to upstream version 0.25.0

* Wed Jun 3 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.24.0-2
- First version of the compatibility layer plugin
