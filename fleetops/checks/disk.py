from pydantic import BaseModel, Field

IGNORED_FS_TYPES = {
    "tmpfs",
    "devtmpfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "overlay",
    "squashfs",
    "autofs",
    "debugfs",
    "tracefs",
    "securityfs",
    "fusectl",
    "mqueue",
    "pstore",
    "bpf",
}


class FileSystemFacts(BaseModel):
    filesystem: str
    mountpoint: str
    fs_type: str
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)


class DiskFacts(BaseModel):
    filesystems: list[FileSystemFacts]


def parse_df(text: str) -> DiskFacts:
    rows = text.splitlines()
    facts: list[FileSystemFacts] = []
    for row in rows[1:]:
        parts = row.split()
        if len(parts) < 7:
            continue
        filesystem, fs_type, total, used, available, percent, mountpoint = parts[:7]
        if fs_type in IGNORED_FS_TYPES:
            continue
        facts.append(
            FileSystemFacts(
                filesystem=filesystem,
                fs_type=fs_type,
                total_bytes=int(total),
                used_bytes=int(used),
                available_bytes=int(available),
                usage_percent=float(percent.rstrip("%")),
                mountpoint=mountpoint,
            )
        )
    if not facts:
        raise ValueError("no relevant local filesystems found")
    return DiskFacts(filesystems=facts)

