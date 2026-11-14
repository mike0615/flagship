# XenAdmin Rocky

Native Linux desktop management client inspired by XCP-ng Center 25.04.
Targets Rocky Linux 9 and 10 desktops. Public project maintained by Mike Anderson;
not an official XCP-ng or XenServer product.

**Status: development tree 1.0.0.dev3; dev.2 remains available under Releases. No qualified v1.0 release yet.**
A successful RPM build is not proof of working pool management or an offline install.
Get the [dev.2 candidate downloads](https://github.com/mike0615/xenadmin-rocky/releases/tag/v1.0.0-dev.2); use the matching Rocky major.
See [qualification status](docs/QUALIFICATION.md) and [feature matrix](docs/FEATURE_MATRIX.md).

The interface uses a resource tree, inventory tabs and VM action buttons. Python/Tk
and the standard library replace WinForms, .NET Framework, COM and Windows installers.
The creation wizard supports installer templates and installed-template disk copies,
selected storage/network/ISO, confirmed task outcomes and recovery reports. A
halted-VM editor provides vCPU and fixed-memory settings. Device management adds
disk/DVD/NIC lifecycle controls. Private persistent journals and read-only UUID
inspection support investigation after interruptions.
TLS certificate and hostname verification are mandatory; passwords are not saved.

## Run from source

On a connected Rocky desktop, install `python3 python3-tkinter ca-certificates`.
From this directory:

```sh
python3 -m xenadmin_rocky
python3 -m unittest discover -s tests -v
```

Use Connect, enter the HTTPS pool coordinator address, username, password and
optionally a PEM CA file. Start with a test pool and a read-only account.
The desktop requires a graphical session; the application is not a web server.

## Documentation

- [User guide and built-in help](docs/USER_GUIDE.md)
- [Installation and airgap operation](docs/INSTALL.md)
- [Build instructions](docs/BUILD.md)
- [Source analysis](docs/SOURCE_ANALYSIS.md)
- [Feature matrix and limitations](docs/FEATURE_MATRIX.md)
- [Security and troubleshooting](docs/OPERATIONS.md)
- [Persistent history and recovery](docs/RECOVERY.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Qualification and evidence](docs/QUALIFICATION.md)

Original application copyright/license notices are preserved in `upstream/LICENSE.xcp-ng`.
The supplied Windows source is inventoried in `upstream/SHA256SUMS`; this repository
contains the new native client, not the Wine wrapper found in the older private fork.
