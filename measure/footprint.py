from __future__ import annotations

import ctypes
import mmap
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

GIB = float(2 ** 30)
RUSAGE_INFO_V0 = 0
SOURCE_LIBPROC = "libproc_phys_footprint"
SOURCE_PS_RSS = "ps_rss_fallback"
SELF_TEST_BYTES = 256 * 1024 * 1024
SELF_TEST_PAGE = 4096


class RUsageInfoV0(ctypes.Structure):
    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
    ]


@dataclass(frozen=True)
class Totals:
    pids: tuple[int, ...]
    rss_gib: float
    footprint_gib: float
    source: str


def _load_libproc() -> ctypes.CDLL | None:
    if sys.platform != "darwin":
        return None
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    except OSError:
        return None
    entry = getattr(library, "proc_pid_rusage", None)
    if entry is None:
        return None
    entry.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    entry.restype = ctypes.c_int
    return library


LIBPROC = _load_libproc()


def phys_footprint(pid: int) -> int | None:
    if LIBPROC is None:
        return None
    info = RUsageInfoV0()
    status = LIBPROC.proc_pid_rusage(
        int(pid), RUSAGE_INFO_V0, ctypes.byref(info))
    if status != 0:
        return None
    return int(info.ri_phys_footprint)


def resident_size(pid: int) -> int | None:
    if LIBPROC is None:
        return None
    info = RUsageInfoV0()
    status = LIBPROC.proc_pid_rusage(
        int(pid), RUSAGE_INFO_V0, ctypes.byref(info))
    if status != 0:
        return None
    return int(info.ri_resident_size)


def ps_rows(needle: str) -> tuple[tuple[int, int], ...]:
    out = subprocess.run(["ps", "-Ao", "pid,rss,command"],
                         capture_output=True, text=True).stdout
    rows: list[tuple[int, int]] = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) != 3 or needle not in parts[2]:
            continue
        if parts[2].startswith("ps -Ao"):
            continue
        rows.append((int(parts[0]), int(parts[1]) * 1024))
    return tuple(rows)


def process_totals(needle: str) -> Totals:
    rows = ps_rows(needle)
    pids = tuple(pid for pid, _rss in rows)
    rss = sum(rss_bytes for _pid, rss_bytes in rows)
    measured = tuple(phys_footprint(pid) for pid in pids)
    if LIBPROC is None or any(value is None for value in measured):
        return Totals(pids, rss / GIB, rss / GIB, SOURCE_PS_RSS)
    footprint = sum(value for value in measured if value is not None)
    return Totals(pids, rss / GIB, footprint / GIB, SOURCE_LIBPROC)


def mapped_file_deltas(pid: int) -> tuple[int, int]:
    handle, path = tempfile.mkstemp()
    os.write(handle, bytes(range(256)) * 4096)
    os.ftruncate(handle, SELF_TEST_BYTES)
    os.fsync(handle)
    footprint_before = phys_footprint(pid)
    resident_before = resident_size(pid)
    mapping = mmap.mmap(handle, SELF_TEST_BYTES, access=mmap.ACCESS_READ)
    touched = 0
    for offset in range(0, SELF_TEST_BYTES, SELF_TEST_PAGE):
        touched += mapping[offset]
    footprint_after = phys_footprint(pid)
    resident_after = resident_size(pid)
    mapping.close()
    os.close(handle)
    os.unlink(path)
    return (int(footprint_after or 0) - int(footprint_before or 0),
            int(resident_after or 0) - int(resident_before or 0))


def self_test() -> int:
    pid = os.getpid()
    before = phys_footprint(pid)
    if before is None:
        print(f"libproc unavailable on {sys.platform}: "
              f"process_totals reports {SOURCE_PS_RSS}")
        totals = process_totals("footprint")
        print(f"self totals {totals}")
        return 0 if totals.source == SOURCE_PS_RSS else 1
    block = bytearray(SELF_TEST_BYTES)
    for offset in range(0, SELF_TEST_BYTES, SELF_TEST_PAGE):
        block[offset] = 1
    after = phys_footprint(pid)
    grew = 0 if after is None else after - before
    del block
    mapped_footprint, mapped_resident = mapped_file_deltas(pid)
    totals = process_totals("footprint")
    print(f"pid {pid} anonymous {SELF_TEST_BYTES / GIB:.3f} GiB touched: "
          f"footprint +{grew / GIB:.3f} GiB")
    print(f"pid {pid} file-backed {SELF_TEST_BYTES / GIB:.3f} GiB read: "
          f"footprint +{mapped_footprint / GIB:.3f} GiB, "
          f"resident +{mapped_resident / GIB:.3f} GiB")
    print(f"self totals {totals}")
    failures = []
    if grew < SELF_TEST_BYTES * 0.75:
        failures.append("footprint did not track a touched allocation")
    if mapped_resident < SELF_TEST_BYTES * 0.75:
        failures.append("resident size did not track mapped file pages")
    if mapped_footprint > SELF_TEST_BYTES * 0.10:
        failures.append("footprint counted reclaimable page cache")
    if totals.source != SOURCE_LIBPROC or pid not in totals.pids:
        failures.append("process_totals did not resolve this process")
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(self_test())
