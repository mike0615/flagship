Name:           xenadmin-rocky
Version:        1.0.0
Release:        0.1.dev1%{?dist}
Summary:        Native Linux desktop management client for XAPI pools
License:        BSD-2-Clause
URL:            https://github.com/mike0615/xenadmin-rocky
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
Requires:       python3 >= 3.9
Requires:       python3-tkinter
Requires:       ca-certificates

%description
Native Tk desktop inventory and VM lifecycle client for XAPI hosts.
No Windows runtime, Python package downloads, or hosted service required.
This development build is not qualified for production use.

%prep
%autosetup

%build
# Standard-library-only Python sources; no network build steps.

%install
mkdir -p %{buildroot}%{_datadir}/%{name}/xenadmin_rocky
cp xenadmin_rocky/*.py %{buildroot}%{_datadir}/%{name}/xenadmin_rocky/
mkdir -p %{buildroot}%{_datadir}/%{name}/docs
cp docs/*.md %{buildroot}%{_datadir}/%{name}/docs/
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications
install -m 0755 packaging/xenadmin-rocky %{buildroot}%{_bindir}/xenadmin-rocky
install -m 0644 packaging/xenadmin-rocky.desktop %{buildroot}%{_datadir}/applications/

%files
%license LICENSE upstream/LICENSE.xcp-ng
%doc README.md SOURCE_COMMIT docs/*.md
%{_bindir}/xenadmin-rocky
%{_datadir}/applications/xenadmin-rocky.desktop
%{_datadir}/%{name}/

%changelog
* Sat Nov 14 2026 Mike Anderson <mike0615@users.noreply.github.com> - 1.0.0-0.1.dev1
- Initial native development candidate; qualification pending.
