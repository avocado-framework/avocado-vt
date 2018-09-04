%global modulename avocado-vt
%if ! 0%{?commit:1}
 %define commit 2d2b89108da1b83a62b83c7e0c8533419e37bc6a
%endif
%global shortcommit %(c=%{commit}; echo ${c:0:8})

Summary: Avocado Virt Test Plugin
Name: avocado-plugins-vt
Version: 62.0
Release: 0%{?dist}
License: GPLv2
Group: Development/Tools
URL: http://avocado-framework.readthedocs.org/
Source0: https://github.com/avocado-framework/%{modulename}/archive/%{commit}/%{modulename}-%{version}-%{shortcommit}.tar.gz
BuildRequires: python2-devel, python-setuptools
BuildArch: noarch
Requires: python-avocado >= 51.0
Requires: python, autotest-framework, xz, tcpdump, iproute, iputils, gcc, glibc-headers, python-devel, nc, python-aexpect, git, python-netaddr, python-netifaces, python-simplejson
Requires: attr
%if 0%{?rhel}
Requires: policycoreutils-python
%else
Requires: policycoreutils-python-utils
%endif

Requires: python-imaging
%if 0%{?el6}
Requires: gstreamer-python, gstreamer-plugins-good
%else
Requires: pygobject2, gstreamer1-plugins-good
%endif

%description
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.

%prep
%setup -q -n %{modulename}-%{commit}

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
* Tue Jun 12 2018 Cleber Rosa <cleber@redhat.com> - 62.0-0
- New release

* Thu Apr 26 2018 Cleber Rosa <cleber@redhat.com> - 61.0-0
- New release

* Wed Mar 28 2018 Cleber Rosa <cleber@redhat.com> - 60.0-0
- New release

* Wed Feb 28 2018 Cleber Rosa <cleber@redhat.com> - 59.0-0
- New upstream release

* Tue Jan 23 2018 Cleber Rosa <cleber@redhat.com> - 58.0-0
- New upstream release

* Tue Dec 19 2017 Cleber Rosa <cleber@redhat.com> - 57.0-0
- New upstream release

* Tue Nov 21 2017 Cleber Rosa <cleber@redhat.com> - 56.0-0
- New upstream release

* Tue Oct 17 2017 Cleber Rosa <cleber@redhat.com> - 55.0-0
- New upstream release

* Wed Sep 20 2017 Cleber Rosa <cleber@redhat.com> - 54.0-0
- New upstream release

* Tue Aug 15 2017 Cleber Rosa <cleber@redhat.com> - 53.0-0
- New upstream release

* Mon Jul 10 2017 Cleber Rosa <cleber@redhat.com> - 51.0-2
- Satisfy avocado requirement with EPEL package

* Wed Jun 14 2017 Cleber Rosa <cleber@redhat.com> - 51.0-1
- Replace aexpect dependency with python-aexpect

* Mon Jun 12 2017 Cleber Rosa <cleber@redhat.com> - 51.0-0
- New upstream release

* Wed May 17 2017 Cleber Rosa <cleber@redhat.com> - 50.1-0
- New minor upstream release with VT JobLock fix

* Tue May 16 2017 Cleber Rosa <cleber@redhat.com> - 50.0-0
- New upstream release

* Tue Apr 25 2017 Cleber Rosa <cleber@redhat.com> - 49.0-0
- New upstream release
- Used latest avocado LTS as mininum required version

* Mon Apr  3 2017 Cleber Rosa <cleber@redhat.com> - 48.0-0
- New upstream release

* Sat Mar 18 2017 Cleber Rosa <cleber@redhat.com> - 47.0-1
- Replaced 7z dependency for xz

* Tue Mar  7 2017 Cleber Rosa <cleber@redhat.com> - 47.0-0
- New upstream release

* Thu Mar  2 2017 Cleber Rosa <cleber@redhat.com> - 46.0-2
- Allow Avocado LTS version (or later) with avocado-plugins-vt
- Fixed URL of Source0 (and modulename variable)
- Fixed date of previous release

* Wed Feb 15 2017 Radek Duda <rduda@redhat.com> - 46.0-1
- Added python-netifaces to requires

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
