Name:           flagship
Version:        1.1.0
Release:        0.2.dev2%{?dist}
Summary:        Native Linux desktop management client for XAPI pools

License:        BSD-2-Clause
URL:            https://github.com/mike0615/flagship
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
Requires:       python3 >= 3.9
Requires:       python3-tkinter
Requires:       ca-certificates

# Flagship was called XenAdmin Rocky (package xenadmin-rocky) up to 1.0.0.dev4.
# dnf upgrade replaces it; the xenadmin-rocky and xenadmin-rocky-recovery
# commands keep working as compatibility symlinks.
Obsoletes:      xenadmin-rocky < 1.1.0
Provides:       xenadmin-rocky = %{version}-%{release}

%description
Flagship is a native Tk desktop inventory, VM provisioning and lifecycle
client for XAPI hosts, part of the Anderson Computer cyber chief toolset.
No Windows runtime, Python package downloads, or hosted service required.

Formerly XenAdmin Rocky. This development build is not qualified for
production use.

%prep
%autosetup

%build
# Standard-library-only Python sources; no network build steps.

%install
mkdir -p %{buildroot}%{_datadir}/%{name}/flagship/icons
cp flagship/*.py %{buildroot}%{_datadir}/%{name}/flagship/
cp flagship/icons/* %{buildroot}%{_datadir}/%{name}/flagship/icons/
mkdir -p %{buildroot}%{_datadir}/%{name}/xenadmin_rocky
cp xenadmin_rocky/*.py %{buildroot}%{_datadir}/%{name}/xenadmin_rocky/
mkdir -p %{buildroot}%{_datadir}/%{name}/docs
cp docs/*.md %{buildroot}%{_datadir}/%{name}/docs/
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications
install -m 0755 packaging/flagship %{buildroot}%{_bindir}/flagship
install -m 0755 packaging/flagship-recovery %{buildroot}%{_bindir}/flagship-recovery
ln -s flagship %{buildroot}%{_bindir}/xenadmin-rocky
ln -s flagship-recovery %{buildroot}%{_bindir}/xenadmin-rocky-recovery
install -m 0644 packaging/flagship.desktop %{buildroot}%{_datadir}/applications/
install -Dm0644 packaging/flagship.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/flagship.svg
# Ship bytecode owned by the package. Rocky 10 clamps file mtimes to the
# changelog date, so a pyc written by a previous build with the same date and
# source size would otherwise be reused after an upgrade.
%py_byte_compile %{python3} %{buildroot}%{_datadir}/%{name}/

%post
gtk-update-icon-cache -q %{_datadir}/icons/hicolor &>/dev/null || :

%postun
gtk-update-icon-cache -q %{_datadir}/icons/hicolor &>/dev/null || :

%files
%license LICENSE upstream/LICENSE.xcp-ng
%doc README.md CHANGELOG.md SOURCE_COMMIT docs/*.md
%{_bindir}/flagship
%{_bindir}/flagship-recovery
%{_bindir}/xenadmin-rocky
%{_bindir}/xenadmin-rocky-recovery
%{_datadir}/applications/flagship.desktop
%{_datadir}/icons/hicolor/scalable/apps/flagship.svg
%{_datadir}/%{name}/

%changelog
* Sun Nov 15 2026 Mike Anderson <mike@andersoncomputer.us> - 1.1.0-0.2.dev2
- Self-signed certificate handling: trust prompt (Connect once / Always trust
  this certificate / Cancel) with SHA-256 pins per host:port in
  ~/.config/flagship/known_certs.json (0600), checked before credentials or
  console cookies are sent; changed certificates get a red warning and a new
  prompt, never auto-accepted. Covers XML-RPC and the console.
- "Ignore SSL certificate errors (insecure)" checkbox with an Insecure TLS
  status-bar marker; flagship --insecure; flagship-recovery --pin, --insecure
  and --no-saved-pins. Tools > Trusted certificates removes pins.
- Verified-by-default and the CA PEM option unchanged. New help chapter.
- Byte-compile into the package so upgrades never run stale bytecode (el10
  clamps mtimes to the changelog date).

* Sun Nov 15 2026 Mike Anderson <mike@andersoncomputer.us> - 1.1.0-0.1.dev1
- Renamed from XenAdmin Rocky to Flagship: package flagship, commands
  /usr/bin/flagship and flagship-recovery (old xenadmin-rocky and
  xenadmin-rocky-recovery kept as symlinks), new icon, journals in
  ~/.local/state/flagship. Obsoletes xenadmin-rocky < 1.1.0.
- First run copies ~/.local/state/xenadmin-rocky (and ~/.config/xenadmin-rocky
  if present) to the new locations, leaving the originals untouched.
- Help menu with Flagship Help (F1) and About Flagship (name, version,
  cyber chief toolset, GitHub link, BSD-2-Clause license, credits).
- Compatibility import path: python3 -m xenadmin_rocky still starts Flagship.

* Sat Nov 14 2026 Mike Anderson <mike0615@users.noreply.github.com> - 1.0.0-0.4.dev4
- Authenticated native console, display-aware layout and booted qualification tools.
* Sat Nov 14 2026 Mike Anderson <mike0615@users.noreply.github.com> - 1.0.0-0.3.dev3
- Device management, durable operation journals, UUID recovery and indexed help.
* Sat Nov 14 2026 Mike Anderson <mike0615@users.noreply.github.com> - 1.0.0-0.2.dev2
- VM creation, hardware configuration, task monitoring and XAPI wire corrections.
* Sat Nov 14 2026 Mike Anderson <mike0615@users.noreply.github.com> - 1.0.0-0.1.dev1
- Initial native development candidate; qualification pending.
