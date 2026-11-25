    target = Path(GUIX_TARGET_MOUNTPOINT).resolve(strict=False)
    if destination == target or target in destination.parents:
        raise DeployCliError(
            "configuration output must be outside the target mountpoint "
            "to avoid writing to the target filesystem"
        )


def _decode_mountinfo_field(value: str) -> str:
    """Decode the octal escapes used by /proc/self/mountinfo path fields."""
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue

        escaped = value[index + 1:index + 4]
        if len(escaped) != 3 or any(digit not in "01234567" for digit in escaped):
            raise DeployCliError("mountinfo contains an invalid octal path escape")
        decoded.append(chr(int(escaped, 8)))
        index += 4
    return "".join(decoded)


def _target_mount_is_present(target: Path) -> bool:
    """Check the exact target mountpoint in Linux mountinfo, including bind mounts."""
    mountinfo = Path("/proc/self/mountinfo")
    try:
        content = mountinfo.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeployCliError(f"cannot read target mount table: {exc}") from exc

    target_mountpoint = str(target.absolute())
    target_found = False
    for line_number, line in enumerate(content.splitlines(), start=1):
        fields = line.split()
        if len(fields) < 10 or "-" not in fields[6:]:
            raise DeployCliError(
                f"mountinfo line {line_number} is malformed; refusing filesystem identity check"
            )
        if not re.fullmatch(r"[0-9]+:[0-9]+", fields[2]):
            raise DeployCliError(
                f"mountinfo line {line_number} has invalid device identity"
            )
        mountpoint = _decode_mountinfo_field(fields[4])
        if mountpoint == target_mountpoint:
            target_found = True
    return target_found


def _ensure_output_not_on_target_filesystem(destination: Path) -> None:
    """Reject bind-mount aliases of a mounted target filesystem.

    os.path.ismount() cannot reliably detect same-filesystem bind mounts.
    The exact mountpoint is therefore found in /proc/self/mountinfo first.
    Comparing st_dev is deliberately conservative: a subvolume on the same
    filesystem is refused as well.
    """
    target = Path(GUIX_TARGET_MOUNTPOINT)
    if not _target_mount_is_present(target):
        return

    try:
        target_device = target.stat().st_dev
        output_device = destination.parent.stat().st_dev
    except OSError as exc:
        raise DeployCliError(f"cannot verify output filesystem identity: {exc}") from exc

    if output_device == target_device:
        raise DeployCliError(
            "configuration output must not share the mounted target filesystem "
            "(including bind-mount aliases)"
        )


def _resolve_output(
    output_value: str,
    protected_inputs: tuple[Path, ...],
) -> Path:
    requested = Path(output_value)
    if not requested.is_absolute():
        raise DeployCliError("configuration output path must be absolute")
    if requested.suffix != ".scm" or not requested.name:
        raise DeployCliError("configuration output must use the .scm suffix")

    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise DeployCliError(f"configuration output parent is unavailable: {exc}") from exc
    if not parent.is_dir():
        raise DeployCliError("configuration output parent is not a directory")

    destination = parent / requested.name
    for protected in protected_inputs:
        if destination == protected:
            raise DeployCliError("configuration output must not overwrite an input file")

    for special_root in (Path("/dev"), Path("/proc"), Path("/sys")):
        try:
            special = special_root.resolve(strict=True)
        except OSError:
            continue
        if destination == special or special in destination.parents:
            raise DeployCliError(f"configuration output is not allowed under {special}")

    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass