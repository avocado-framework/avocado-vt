%global srcname avocado-vt

# Conditional for release vs. snapshot builds. Set to 1 for release build.
%if ! 0%{?rel_build:1}
    %global rel_build 1
%endif

# Settings used for build from snapshots.
%if 0%{?rel_build}
    %global gittar          %{srcname}-%{version}.tar.gz
%else
    %if ! 0%{?commit:1}
        %global commit      3307b19b35e4becf3342d17a093a335f7aee914a
    %endif
    %if ! 0%{?commit_date:1}
        %global commit_date 20190815
    %endif
    %global shortcommit     %(c=%{commit};echo ${c:0:8})
    %global gitrel          .%{commit_date}git%{shortcommit}
    %global gittar          %{srcname}-%{shortcommit}.tar.gz
%endif

%if 0%{?rhel}
    %global with_python3 0
%else
    %global with_python3 1
%endif

# The Python dependencies are already tracked by the python2
# or python3 "Requires".  This filters out the python binaries
# from the RPM automatic requires/provides scanner.
%global __requires_exclude ^/usr/bin/python[23]$

# Disable the shebangs checks on scripts that currently dont'
# define a Python version
%global __brp_mangle_shebangs_exclude_from multicast_guest.py|netperf_agent.py|ksm_overcommit_guest.py|check_cpu_flag.py|virtio_console_guest.py|boottool.py|VirtIoChannel_guest_send_receive.py|serial_host_send_receive.py

Summary: Avocado Virt Test Plugin
Name: avocado-plugins-vt
Version: 71.0
Release: 0%{?gitrel}%{?dist}
License: GPLv2
Group: Development/Tools
URL: http://avocado-framework.readthedocs.org/
%if 0%{?rel_build}
Source0: https://github.com/avocado-framework/%{srcname}/archive/%{version}.tar.gz#/%{gittar}
%else
Source0: https://github.com/avocado-framework/%{srcname}/archive/%{commit}.tar.gz#/%{gittar}
# old way of retrieving snapshot sources
#Source0: https://github.com/avocado-framework/%{srcname}/archive/%{commit}/%{srcname}-%{version}-%{shortcommit}.tar.gz
%endif
BuildRequires: python2-devel, python2-setuptools, python-six
Requires: python-six
%if %{with_python3}
BuildRequires: python3-devel, python3-setuptools, python3-six
Requires: python3-six
%endif
BuildArch: noarch
Requires: autotest-framework, xz, tcpdump, iproute, iputils, gcc, glibc-headers, nc, git
Requires: attr
%if 0%{?rhel}
Requires: policycoreutils-python
%else
Requires: policycoreutils-python-utils
%endif

Requires: python2-imaging
%if %{with_python3}
Requires: python3-imaging
%endif
%if 0%{?el6}
Requires: gstreamer-python, gstreamer-plugins-good
%else
Requires: pygobject2, gstreamer1-plugins-good
%endif

%description
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.

%package -n python2-%{name}
Summary: %{summary}
Requires: python2, python2-devel, python2-avocado >= 51.0, python2-aexpect
Requires: python2-simplejson
%if 0%{?rhel} == 7
Requires: python-netaddr, python-netifaces
%else
Requires: python2-netaddr, python2-netifaces
%endif

# For compatibility reasons, let's mark this package as one that
# provides the same functionality as the old package name and also
# one that obsoletes the old package name, so that the new name is
# favored.  These could (and should) be removed in the future.
# These changes are backed by the following guidelines:
# https://fedoraproject.org/wiki/Upgrade_paths_%E2%80%94_renaming_or_splitting_packages
Obsoletes: %{name} <= 67.0-1
Provides: %{name} = %{version}-%{release}
%{?python_provide:%python_provide python2-%{srcname}}
%description -n python2-%{name}
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.

%if %{with_python3}
%package -n python3-%{name}
Summary: %{summary}
Requires: python3, python3-devel, python3-avocado >= 51.0, python3-aexpect
Requires: python3-netaddr, python3-netifaces, python3-simplejson
%{?python_provide:%python_provide python3-%{srcname}}
%description -n python3-%{name}
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.
%endif

%prep
%if 0%{?rel_build}
%setup -q -n %{srcname}-%{version}
%else
%setup -q -n %{srcname}-%{commit}
%endif

%build
%{__python2} setup.py build
%if %{with_python3}
%{__python3} setup.py build
%endif

%install
%{__mkdir} -p %{buildroot}/etc/avocado/conf.d
%{__python2} setup.py install --root %{buildroot} --skip-build
%{__mv} %{buildroot}%{python2_sitelib}/avocado_vt/conf.d/* %{buildroot}/etc/avocado/conf.d
%if %{with_python3}
%{__python3} setup.py install --root %{buildroot} --skip-build
%{__mv} %{buildroot}%{python3_sitelib}/avocado_vt/conf.d/* %{buildroot}/etc/avocado/conf.d
%endif

%files -n python2-%{name}
%defattr(-,root,root,-)
%dir %{_sysconfdir}/avocado
%dir %{_sysconfdir}/avocado/conf.d
%config(noreplace)%{_sysconfdir}/avocado/conf.d/*.conf
%doc README.rst LICENSE
%{python2_sitelib}/avocado_vt*
%{python2_sitelib}/avocado_framework_plugins_vt*
%{python2_sitelib}/virttest*
%{_datadir}/avocado-plugins-vt/backends/*
%{_datadir}/avocado-plugins-vt/shared/*
%{_datadir}/avocado-plugins-vt/test-providers.d/*

%if %{with_python3}
%files -n python3-%{name}
%defattr(-,root,root,-)
%dir /etc/avocado
%dir /etc/avocado/conf.d
%config(noreplace)%{_sysconfdir}/avocado/conf.d/*.conf
%doc README.rst LICENSE
%{python3_sitelib}/avocado_vt*
%{python3_sitelib}/avocado_framework_plugins_vt*
%{python3_sitelib}/virttest*
%{_datadir}/avocado-plugins-vt/backends/*
%{_datadir}/avocado-plugins-vt/shared/*
%{_datadir}/avocado-plugins-vt/test-providers.d/*
%endif


%changelog
* Thu Aug 15 2019 Cleber Rosa <cleber@redhat.com> - 71.0-0
- New release

* Thu Aug 15 2019 Cleber Rosa <cleber@redhat.com> - 70.0-4
- Fixed configuration location on Python 2 (only) builds

* Wed Aug 14 2019 Cleber Rosa <cleber@redhat.com> - 70.0-3
- Added six requirement

* Wed Aug 14 2019 Lukas Doktor <ldoktor@redhat.com> - 70.0-2
- Change the way config files are packaged

* Wed Aug 14 2019 Lukas Doktor <ldoktor@redhat.com> - 70.0-1
- Rename package to "avocado_framework_plugins_vt"

* Wed Jun 26 2019 Cleber Rosa <cleber@redhat.com> - 70.0-0
- New release

* Tue Jun 25 2019 Cleber Rosa <cleber@redhat.com> - 69.0-1
- Exclude scripts from shebangs checks

* Tue Feb 26 2019 Cleber Rosa <cleber@redhat.com> - 69.0-0
- New release

* Sat Feb 16 2019 Cleber Rosa <cleber@redhat.com> - 68.0-1
- Use python2 requires on EL7

* Wed Feb 13 2019 Cleber Rosa <cleber@redhat.com> - 68.0-0
- New release

* Sat Jan 5 2019 Plamen Dimitrov <pdimitrov@pevogam.com> - 67.0-1
- Add support for release builds in addition to snapshot builds
- Add python 3 package and thus support for python 3 RPMs

* Mon Dec 17 2018 Cleber Rosa <cleber@redhat.com> - 67.0-0
- New release

* Tue Nov 20 2018 Cleber Rosa <cleber@redhat.com> - 66.0-0
- New release

* Mon Nov 19 2018 Cleber Rosa <cleber@redhat.com> - 65.0-1
- Updated macros to Python 2

* Tue Oct  2 2018 Cleber Rosa <cleber@redhat.com> - 65.0-0
- New release

* Mon Aug 27 2018 Cleber Rosa <cleber@redhat.com> - 64.0-0
- New release

* Tue Jul 17 2018 Cleber Rosa <cleber@redhat.com> - 63.0-0
- New release

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
