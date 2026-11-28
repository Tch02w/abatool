"""Keep the Windows result-index writer marker exclusive until its owner exits."""

from __future__ import annotations

import ctypes
import msvcrt
import os
import stat
from _winapi import GENERIC_READ, OPEN_EXISTING, CloseHandle, CreateFile
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO

_CREATE_NEW = 1
_DELETE = 0x10000
_DELETE_ON_CLOSE = 0x04000000
_OPEN_REPARSE_POINT = 0x00200000


def _open_marker(path: Path, disposition: int, flags: int) -> BinaryIO:
    # Share mode zero also keeps older PySide clients from reading a live PID.
    handle = CreateFile(
        str(path), GENERIC_READ | _DELETE, 0, 0, disposition, flags | _OPEN_REPARSE_POINT, 0
    )
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")


def open_index_writer(path: Path, owner_exited: Callable[[bytes], bool]) -> BinaryIO:
    """An open handle owns the marker and deletes it even on process exit."""
    for _ in range(2):
        try:
            return _open_marker(path, _CREATE_NEW, _DELETE_ON_CLOSE)
        except FileExistsError:
            pass
        try:
            marker = _open_marker(path, OPEN_EXISTING, 0)
        except FileNotFoundError:
            continue  # Another writer finished between the two opens.
        try:
            attributes = os.fstat(marker.fileno())
            if (
                not stat.S_ISREG(attributes.st_mode)
                or attributes.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or attributes.st_size > 4096
                or not owner_exited(marker.read())
            ):
                raise BlockingIOError("Result index marker is already owned")
            # Reclaim this exact legacy file under exclusive access. No other
            # writer can replace the path between checking the PID and release.
            set_info = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
            set_info.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
            set_info.restype = wintypes.BOOL
            delete_file = ctypes.c_ubyte(1)
            file_disposition_info = 4
            if not set_info(
                msvcrt.get_osfhandle(marker.fileno()), file_disposition_info,
                ctypes.byref(delete_file), ctypes.sizeof(delete_file)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return marker
        except BaseException:
            marker.close()
            raise
    raise BlockingIOError("Result index marker changed during acquisition")
