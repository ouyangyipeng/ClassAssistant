import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path

from classfox.downloads import Asset, DownloadError, digest_matches


def bundled_assets() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "model-assets"


def validate_package(package: Path, assets: list[Asset]) -> None:
    if not package.is_absolute() or package.is_symlink() or not package.is_file() or package.suffix.lower() != ".zip":
        raise DownloadError("请选择本机的 ClassFox 离线模型 ZIP 包")
    if package.stat().st_size > 10 * 1024**3:
        raise DownloadError("离线模型包超过大小限制")
    try:
        with zipfile.ZipFile(package) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 32 or len(set(names)) != len(names):
                raise DownloadError("离线模型包包含重复或过多文件")
            if sum(entry.file_size for entry in entries) > sum(asset.size for asset in assets) + 4 * 1024**2:
                raise DownloadError("离线模型包展开体积超出限制")
            for entry in entries:
                if (
                    not entry.filename
                    or entry.filename in {".", ".."}
                    or any(character in entry.filename for character in "/\\:")
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or entry.flag_bits & 1
                ):
                    raise DownloadError("离线模型包包含无效路径、链接或加密文件")
            for asset in assets:
                if asset.filename not in names or archive.getinfo(asset.filename).file_size != asset.size:
                    raise DownloadError(f"离线模型包不匹配，缺少或大小不符：{asset.filename}")
    except (OSError, zipfile.BadZipFile) as error:
        raise DownloadError("无法读取离线模型包，请重新下载完整 ZIP 文件") from error


def import_asset(package: Path, asset: Asset, destination: Path) -> None:
    if digest_matches(destination, asset):
        return
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(destination.parent).free < asset.size + 16 * 1024**2:
        raise DownloadError("磁盘空间不足，无法导入模型")
    partial = destination.with_suffix(destination.suffix + ".importing")
    try:
        with zipfile.ZipFile(package) as archive, archive.open(asset.filename) as source, partial.open("wb") as output:
            remaining = asset.size
            while chunk := source.read(min(1024**2, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0:
                    raise DownloadError("离线模型文件超过预期大小")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if not digest_matches(partial, asset):
            raise DownloadError(f"离线模型文件校验失败：{asset.filename}，请重新下载")
        os.replace(partial, destination)
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError, EOFError) as error:
        raise DownloadError("离线模型包读取失败，请重新下载") from error
    finally:
        partial.unlink(missing_ok=True)
