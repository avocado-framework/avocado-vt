Summary: Avocado Virt Test Compatibility Plugin
Name: avocado-plugins-vt
Version: 0.24.0
Release: 2%{?dist}
License: GPLv2
Group: Development/Tools
URL: http://avocado-framework.readthedocs.org/
Source: avocado-plugins-vt-%{version}.tar.gz
BuildRequires: python2-devel
BuildArch: noarch
Requires: python, avocado

%description
Avocado Virt Test Compatibility is a plugin that lets you
execute tests from the virt test suite
(http://virt-test.readthedocs.org/en/latest/), with all
the avocado convenience features, such as HTML report,
Xunit output, among others.

%prep
%setup -q

%build
%{__python} setup.py build

%install
%{__python} setup.py install --root %{buildroot} --skip-build

%files
%defattr(-,root,root,-)
%doc README.md LICENSE
%{python_sitelib}/avocado*

%changelog
* Wed Jun 3 2015 Lucas Meneghel Rodrigues <lmr@redhat.com> - 0.24.0-2
- First version of the compatibility layer plugin
