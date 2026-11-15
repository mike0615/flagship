# Internal build metadata; source after root and major have been validated.
app_version=$(PYTHONPATH="$root" python3 -c 'from flagship import __version__; print(__version__)')
rpm_version=$(awk '/^Version:/ {print $2; exit}' "$root/packaging/flagship.spec")
if [[ ! $app_version =~ ^[0-9A-Za-z.+-]+$ || ! $rpm_version =~ ^[0-9.]+$ ]]; then
    echo 'Invalid build version metadata' >&2
    exit 2
fi
archive_name="flagship-$rpm_version"
out="$root/dist/$app_version/el$major"
