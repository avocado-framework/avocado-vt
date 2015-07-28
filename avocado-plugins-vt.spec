Summary: Avocado Virt Test Plugin
Name: avocado-plugins-vt
Version: 0.26.0
Release: 1%{?dist}
License: GPLv2
Group: Development/Tools
URL: http://avocado-framework.readthedocs.org/
Source: avocado-plugins-vt-%{version}.tar.gz
BuildRequires: python2-devel
BuildArch: noarch
Requires: python, avocado, autotest-framework, p7zip, tcpdump, nmap-ncat, iproute, iputils, gcc, glibc-headers, python-devel

%description
Avocado Virt Test is a plugin that lets you execute virt-tests
with all the avocado convenience features, such as HTML report,
Xunit output, among others.

%prep
%setup -q

%build
%{__python} setup.py build

%install
%{__python} setup.py install --root %{buildroot} --skip-build

%files
%defattr(-,root,root,-)
%dir /etc/avocado
%dir /etc/avocado/conf.d
%config(noreplace)/etc/avocado/conf.d/virt-test.conf
%doc README.rst LICENSE
%{python_sitelib}/avocado*
%{python_sitelib}/virttest*
%{_datadir}/avocado-plugins-vt/backends/*
%{_datadir}/avocado-plugins-vt/shared/*
%{_datadir}/avocado-plugins-vt/test-providers.d/*


%changelog
* Thu Jul 30 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.26.0-2
- Merge with virt-test/updated package dependencies

* Mon Jul 6 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.26.0-1
- Update to upstream version 0.26.0

* Tue Jun 16 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.25.0-1
- Update to upstream version 0.25.0

* Wed Jun 3 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.24.0-2
- First version of the compatibility layer plugin
