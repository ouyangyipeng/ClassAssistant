import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DataDirectoryInUse(RuntimeError):
    pass


@contextmanager
def data_directory_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Keep the inode after release: unlinking allows two owners to lock different files.
    descriptor = os.open(directory / ".service.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise DataDirectoryInUse("此数据目录已由另一个课狐窗口使用，请返回原窗口") from exc
            raise
        yield
    finally:
        # Kernel locks also release on a crash; stale PID files are never trusted.
        os.close(descriptor)
