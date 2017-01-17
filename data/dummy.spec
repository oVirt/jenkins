Name:		dummy
Version:	%{?_version}%{!?_version:0.0.0}
Release:	%{?_release}%{!?_release:0.0.0}%{?dist}
Summary:	Dummy package for testing purposed
BuildArch:	noarch

Group:		System Environment/Libraries
License:	GPLv2+

BuildRequires:	git

%description
A dummy package built to check package handling code

%prep
# Nothing to do here

%build
# Nothing to do here

%install
install -d $RPM_BUILD_ROOT/var/lib/dummy
(
	echo 'This is a useless dummy file'
	echo 'Installed by dummy-%{version}-%{release}'
) > $RPM_BUILD_ROOT/var/lib/dummy/dummy.txt

%files
/var/lib/dummy/*

%changelog
