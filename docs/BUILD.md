# Building reproducible candidates

Use a connected Linux builder with Bash, Git, Podman and network access to Rocky
repositories. This is a standard-library-only Python application; no pip install,
NuGet download or Windows runtime is needed. Container images/repositories are
moving inputs; retain image digests, logs, source commit and PACKAGES.tsv for each
candidate. Current scripts target x86_64 builders and bundles.

```sh
./scripts/build-rpm.sh 9
./scripts/build-rpm.sh 10
./scripts/build-airgap.sh 9
./scripts/build-airgap.sh 10
```

Build outputs, SRPMs, checksums and dependency bundles go under dist/<application-version>/el9 and dist/<application-version>/el10.
They are excluded from Git. Each bundle contains local RPMs, license metadata,
offline installer, help files, build OS identity and file checksums. Build on the
same Rocky major as the target; never mix dependency sets across majors.

Run unit tests using `python3 -m unittest discover -s tests -v`. For GUI construction
use `xvfb-run -a python3 -m xenadmin_rocky --smoke-test` where available.
A GUI smoke test is not a hypervisor workflow test.

After changes, rebuild both bundles and perform the qualification checklist on
fresh disconnected desktops. Production release requires RPM signing, retained
public verification keys and an authenticated delivery procedure. Development
candidate RPMs are unsigned and must not be presented as a signed stable release.

The source archive and SRPM include scripts and tests. SOURCE_COMMIT records the
builder's Git HEAD; use a clean committed checkout for release builds. The application
and source RPM filenames differ by major; their RPM metadata must both be inspected.
CI checks are configured in `.github/workflows/ci.yml`; a configured workflow is
not evidence of a passing remote run. Bundles are generated separately on the builder.

Use `./scripts/test-offline.sh 9` and `./scripts/test-offline.sh 10` for fresh
network-disabled container installation checks. Collect corresponding dependency
SRPMs using `./scripts/collect-dependency-sources.sh 9` and the equivalent for 10.
Source archives can be large (the Rocky 10 Noto font SRPM alone is about 1 GB);
retain them with the binary bundles for offline source access.

Build output is isolated by application version (currently 1.0.0.dev2) so a new
candidate does not overwrite published dev.1 artifacts. CI uploads the complete
versioned dist tree for its Rocky matrix job.

For incremental development source distribution, `collect-source-delta.sh 9
/path/to/authenticated/baseline-sources` collects only source RPMs absent from that
baseline and verifies exact filename coverage. Its SOURCE-COVERAGE.tsv identifies
baseline versus delta sources with SHA-256 values. Retain the authenticated baseline
archive alongside the delta; the delta alone is not a complete source set. Use the
full collector for a self-contained consolidated source archive.
