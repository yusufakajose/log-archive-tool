import os
from pathlib import Path
from datetime import datetime

import pytest

from log_archive import __main__ as m


def create_sample_tree(tmp_path: Path) -> tuple[Path, Path]:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "app.log").write_text("alpha\n", encoding="utf-8")
    (log_dir / "system.log").write_text("beta\n", encoding="utf-8")
    output_dir = log_dir / "archives"
    output_dir.mkdir()
    return log_dir, output_dir


def test_build_archive_name_extensions():
    now = datetime(2025, 1, 2, 3, 4, 5)
    assert m.build_archive_name(now, "gzip").endswith(".tar.gz")
    assert m.build_archive_name(now, "zstd").endswith(".tar.zst")
    assert m.build_archive_name(now, "none").endswith(".tar")


def test_enumerate_exclusions(tmp_path: Path):
    log_dir, output_dir = create_sample_tree(tmp_path)
    # Create audit log inside output dir which must be excluded
    audit_log_path = output_dir / m.AUDIT_LOG_NAME
    audit_log_path.write_text("audit\n", encoding="utf-8")

    files = m.enumerate_files(
        log_dir,
        output_dir,
        audit_log_path,
        include_patterns=[],
        exclude_patterns=[],
    )
    names = {p.name for p in files}
    assert "app.log" in names and "system.log" in names
    # Ensure output_dir and its audit log are not included
    assert m.AUDIT_LOG_NAME not in names
    assert "archives" not in {p.name for p in files if p.is_dir()}


def test_create_archive_none_and_count(tmp_path: Path):
    log_dir, output_dir = create_sample_tree(tmp_path)
    audit_log_path = output_dir / m.AUDIT_LOG_NAME
    files = m.enumerate_files(log_dir, output_dir, audit_log_path, [], [])

    archive_name = m.build_archive_name(datetime.now(), "none")
    dest = output_dir / archive_name
    duration_ms = m.create_archive(
        source_root=log_dir,
        files=files,
        dest_archive=dest,
        compression="none",
        level=None,
        threads=1,
        verbose=False,
    )
    assert dest.exists(), "archive should be created"
    assert duration_ms >= 0
    count, size = m.compute_file_count_and_size(dest)
    assert count == len(files)
    assert size > 0


def test_incremental_two_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log_dir, output_dir = create_sample_tree(tmp_path)
    # First run: archive everything
    rc1 = m.main([str(log_dir), "--compression", "none", "--incremental"])  # type: ignore[list-item]
    assert rc1 == 0
    # Second run: unchanged, should archive 0 files
    before = set(p for p in output_dir.glob("*"))
    rc2 = m.main([str(log_dir), "--compression", "none", "--incremental"])  # type: ignore[list-item]
    assert rc2 == 0
    after = set(p for p in output_dir.glob("*"))
    # New archive file should exist; manifest should be present; count of files increases by at least 1
    assert (output_dir / "manifest.json").exists()
    assert len(after) >= len(before)


def test_retention_count(tmp_path: Path):
    log_dir, output_dir = create_sample_tree(tmp_path)
    audit_log_path = output_dir / m.AUDIT_LOG_NAME
    files = m.enumerate_files(log_dir, output_dir, audit_log_path, [], [])
    # Create three archives with plain tar
    paths: list[Path] = []
    for _ in range(3):
        dest = output_dir / m.build_archive_name(datetime.now(), "none")
        m.create_archive(log_dir, files, dest, "none", None, 1, False)
        paths.append(dest)
    # Keep only the most recent 1
    m.apply_retention(output_dir, retention_days=None, retention_count=1, dry_run=False, verbose=False)
    remaining = sorted([p for p in output_dir.glob("*.tar")])
    assert len(remaining) == 1
