"""Inode-bound filesystem primitives for observer-only diagnostics.

All child operations are relative to an opened diagnostic directory.  The
directory inode captured at initialization is checked before an operation,
and the opened descriptor pins that inode across the operation.  Replacing a
path component therefore fails closed or continues on the already-opened
directory; it can never redirect a diagnostic read or write elsewhere.
"""
from __future__ import annotations

import fcntl
import os
import secrets
import stat
from pathlib import Path


DirectoryIdentity = tuple[int, int]


def _basename(name: str) -> str:
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or Path(name).name != name):
        raise ValueError("diagnostic child name must be one basename")
    return name


def _directory_fd(
    directory: Path,
    expected: DirectoryIdentity | None = None,
) -> tuple[int, DirectoryIdentity]:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(directory, flags)
    try:
        current = os.fstat(descriptor)
        identity = (current.st_dev, current.st_ino)
        named = os.stat(directory, follow_symlinks=False)
        if (not stat.S_ISDIR(current.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or (named.st_dev, named.st_ino) != identity):
            raise ValueError("diagnostic root is not a directory")
        if expected is not None and identity != expected:
            raise RuntimeError("diagnostic directory changed concurrently")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, identity


def bind_directory(directory: Path) -> DirectoryIdentity:
    """Capture one non-symlink directory identity."""
    descriptor, identity = _directory_fd(directory)
    os.close(descriptor)
    return identity


def open_child(
    path: Path,
    flags: int,
    mode: int = 0o600,
    *,
    directory_identity: DirectoryIdentity,
) -> int:
    """Open exactly one child of the bound directory without following it."""
    name = _basename(path.name)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    directory_fd, _current = _directory_fd(
        path.parent, directory_identity)
    try:
        descriptor = os.open(name, flags, mode, dir_fd=directory_fd)
        try:
            opened = os.fstat(descriptor)
            named = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False)
            if ((opened.st_dev, opened.st_ino)
                    != (named.st_dev, named.st_ino)):
                raise ValueError("diagnostic child is a symlink or changed")
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor
    finally:
        os.close(directory_fd)


def acquire_lock(
    path: Path,
    *,
    directory_identity: DirectoryIdentity,
) -> int:
    """Open and exclusively lock one regular child for the caller's lifetime."""
    descriptor = open_child(
        path, os.O_RDWR | os.O_CREAT, 0o600,
        directory_identity=directory_identity)
    try:
        current = os.fstat(descriptor)
        if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
            raise ValueError("diagnostic lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def release_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def atomic_write(
    path: Path,
    data: bytes,
    *,
    durable: bool = True,
    directory_identity: DirectoryIdentity,
) -> None:
    """Replace one regular child atomically within the bound directory."""
    if not isinstance(data, bytes):
        raise TypeError("diagnostic persistence needs bytes")
    target = _basename(path.name)
    directory_fd, _current = _directory_fd(
        path.parent, directory_identity)
    temporary: str | None = None
    descriptor: int | None = None
    try:
        try:
            existing = os.stat(
                target, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (not stat.S_ISREG(existing.st_mode)
                    or existing.st_nlink != 1):
                raise ValueError(
                    "diagnostic output child is not a private regular file")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for _attempt in range(128):
            candidate = f".{target}.{secrets.token_hex(12)}.tmp"
            try:
                descriptor = os.open(
                    candidate, flags, 0o600, dir_fd=directory_fd)
            except FileExistsError:
                continue
            temporary = candidate
            break
        if descriptor is None or temporary is None:
            raise FileExistsError(
                "cannot allocate a diagnostic atomic-write temporary")
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(data)
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        os.replace(
            temporary, target,
            src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
        if durable:
            os.fsync(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


__all__ = [
    "DirectoryIdentity", "acquire_lock", "atomic_write", "bind_directory",
    "open_child", "release_lock",
]
