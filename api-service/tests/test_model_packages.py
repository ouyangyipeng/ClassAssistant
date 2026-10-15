import zipfile
from pathlib import Path

import pytest

from classfox.downloads import DownloadError
from classfox.model_packages import import_asset, validate_package
from tests.test_downloads import asset


@pytest.mark.parametrize("name", ["../escape", "/absolute", "dir/file", "C:\\bad"])
def test_package_rejects_path_entries(tmp_path: Path, name: str) -> None:
    package = tmp_path / "model.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("model.bin", b"model")
        archive.writestr(name, b"bad")
    with pytest.raises(DownloadError, match="路径"):
        validate_package(package, [asset(b"model")])
    assert not (tmp_path / "escape").exists()


def test_package_bounds_expansion_and_requires_correct_model(tmp_path: Path) -> None:
    package = tmp_path / "model.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("model.bin", b"model")
        archive.writestr("extra.txt", b"x" * (5 * 1024**2))
    with pytest.raises(DownloadError, match="体积"):
        validate_package(package, [asset(b"model")])
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("wrong-model.bin", b"model")
    with pytest.raises(DownloadError, match="不匹配"):
        validate_package(package, [asset(b"model")])


def test_import_does_not_replace_verified_file_with_bad_bytes(tmp_path: Path) -> None:
    package = tmp_path / "model.zip"
    destination = tmp_path / "cached" / "model.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"previous")
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("model.bin", b"wrong")
    with pytest.raises(DownloadError, match="校验"):
        import_asset(package, asset(b"model"), destination)
    assert destination.read_bytes() == b"previous"
    assert not destination.with_suffix(".bin.importing").exists()


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "model.zip"
    with zipfile.ZipFile(package, "w") as archive:
        link = zipfile.ZipInfo("model.bin")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, b"model")
    with pytest.raises(DownloadError, match="链接"):
        validate_package(package, [asset(b"model")])


def test_import_reports_incremental_progress_before_completion(tmp_path: Path) -> None:
    payload = b"m" * (3 * 1024**2)
    package = tmp_path / "model.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("model.bin", payload)
    updates: list[int] = []
    destination = tmp_path / "cached" / "model.bin"
    import_asset(package, asset(payload), destination, updates.append)
    assert updates == [1024**2, 2 * 1024**2, 3 * 1024**2]
    assert destination.read_bytes() == payload
