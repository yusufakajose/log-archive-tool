from __future__ import annotations

import argparse
import sys
from pathlib import Path
import os
import tarfile
import time
from datetime import datetime, timezone
from typing import Iterable, List, Set, Any, Dict

try:
	import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
	try:
		import tomli as tomllib  # type: ignore
	except ModuleNotFoundError:
		tomllib = None  # type: ignore


ARCHIVE_PREFIX = "logs_archive_"
ARCHIVE_EXT = ".tar.gz"
DEFAULT_OUTPUT_DIR_NAME = "archives"
AUDIT_LOG_NAME = "archive.log"


def parse_args(argv: List[str]) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Archive logs into a timestamped tar.gz and append an audit entry.",
	)
	parser.add_argument(
		"--config",
		type=Path,
		help="Path to a TOML config file. If omitted, searches XDG paths.",
	)
	parser.add_argument(
		"log_directory",
		type=Path,
		nargs="?",
		help="Directory containing logs to archive (optional if provided via config)",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		help="Directory where archives and audit log will be stored (default: <log_directory>/archives)",
	)
	group = parser.add_mutually_exclusive_group()
	group.add_argument("--retention-days", type=int, help="Delete archives older than N days")
	group.add_argument("--retention-count", type=int, help="Keep only the most recent N archives")
	parser.add_argument("--include", type=str, help="Comma-separated glob patterns to include")
	parser.add_argument("--exclude", type=str, help="Comma-separated glob patterns to exclude")
	parser.add_argument("--dry-run", action="store_true", help="Show planned actions without writing")
	parser.add_argument("--verbose", action="store_true", help="Verbose console output")
	return parser.parse_args(argv)


def _now() -> datetime:
	return datetime.now().astimezone()


def build_archive_name(now: datetime) -> str:
	return f"{ARCHIVE_PREFIX}{now.strftime('%Y%m%d_%H%M%S')}{ARCHIVE_EXT}"


def resolve_output_dir(log_directory: Path, output_dir: Path | None) -> Path:
	return (output_dir or (log_directory / DEFAULT_OUTPUT_DIR_NAME)).resolve()


def split_patterns(csv: str | None) -> List[str]:
	if not csv:
		return []
	return [p.strip() for p in csv.split(",") if p.strip()]


def load_config(explicit_path: Path | None) -> Dict[str, Any]:
	"""Load TOML config from explicit path or XDG defaults.

	Order of precedence:
	1) --config path if provided
	2) $LOG_ARCHIVE_CONFIG if set (file path)
	3) $XDG_CONFIG_HOME/log-archive/config.toml
	4) ~/.config/log-archive/config.toml
	"""
	paths: List[Path] = []
	if explicit_path:
		paths.append(explicit_path)
	else:
		env_path = os.environ.get("LOG_ARCHIVE_CONFIG")
		if env_path:
			paths.append(Path(env_path))
		xdg = os.environ.get("XDG_CONFIG_HOME")
		if xdg:
			paths.append(Path(xdg) / "log-archive" / "config.toml")
		paths.append(Path.home() / ".config" / "log-archive" / "config.toml")

	for p in paths:
		if p and p.is_file():
			if tomllib is None:
				return {}
			with p.open("rb") as fh:
				try:
					data = tomllib.load(fh)  # type: ignore[arg-type]
					d = data if isinstance(data, dict) else {}
					return d
				except Exception:
					return {}
	return {}


def should_exclude(path: Path, root: Path, builtin_exclusions: Set[Path], include_patterns: List[str], exclude_patterns: List[str]) -> bool:
	# Built-in exclusions take precedence
	for excl in builtin_exclusions:
		try:
			path.relative_to(excl)
			return True
		except ValueError:
			pass

	rel = path.relative_to(root)
	# Exclude patterns
	for pat in exclude_patterns:
		if rel.match(pat):
			return True
	# Include patterns (if any were provided): if provided, only include if matches any include pattern
	if include_patterns:
		for pat in include_patterns:
			if rel.match(pat):
				return False
		return True
	return False


def enumerate_files(log_directory: Path, output_dir: Path, audit_log_path: Path, include_patterns: List[str], exclude_patterns: List[str]) -> List[Path]:
	builtin_exclusions: Set[Path] = {output_dir, audit_log_path}
	files: List[Path] = []
	for path in log_directory.rglob("*"):
		if path.is_dir():
			# Skip excluded directories quickly
			if should_exclude(path, log_directory, builtin_exclusions, include_patterns, exclude_patterns):
				continue
			continue
		if should_exclude(path, log_directory, builtin_exclusions, include_patterns, exclude_patterns):
			continue
		files.append(path)
	return files


def create_archive(source_root: Path, files: Iterable[Path], dest_archive: Path) -> int:
	start = time.perf_counter()
	with tarfile.open(dest_archive, mode="w:gz") as tar:
		count = 0
		for f in files:
			arcname = f.relative_to(source_root)
			tar.add(f, arcname=str(arcname), recursive=False)
			count += 1
	elapsed_ms = int((time.perf_counter() - start) * 1000)
	return elapsed_ms


def human_size(num_bytes: int) -> str:
	units = ["B", "KB", "MB", "GB", "TB"]
	size = float(num_bytes)
	for unit in units:
		if size < 1024.0 or unit == units[-1]:
			return f"{size:.1f}{unit}"
		size /= 1024.0
	return f"{size:.1f}TB"


def compute_file_count_and_size(archive_path: Path) -> tuple[int, int]:
	# Count members and report final archive size on disk
	count = 0
	with tarfile.open(archive_path, mode="r:gz") as tar:
		for _ in tar:
			count += 1
	size = archive_path.stat().st_size
	return count, size


def write_audit_line(audit_log_path: Path, now: datetime, archive_name: str, file_count: int, size_bytes: int, duration_ms: int, error: str | None = None) -> None:
	iso = now.isoformat()
	local_str = now.strftime("%Y-%m-%d %H:%M:%S")
	if error:
		line = f"{iso} | local={local_str} | archive={archive_name} | ERROR={error}\n"
	else:
		size_h = human_size(size_bytes)
		line = (
			f"{iso} | local={local_str} | archive={archive_name} | files={file_count} | "
			f"size={size_h} | duration_ms={duration_ms}\n"
		)
	with audit_log_path.open("a", encoding="utf-8") as fh:
		fh.write(line)


def apply_retention(output_dir: Path, retention_days: int | None, retention_count: int | None, dry_run: bool, verbose: bool) -> None:
	archives = sorted(
		[p for p in output_dir.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_EXT}") if p.is_file()],
		key=lambda p: p.stat().st_mtime,
	)
	to_delete: List[Path] = []
	if retention_days is not None:
		cutoff = _now().timestamp() - (retention_days * 86400)
		to_delete = [p for p in archives if p.stat().st_mtime < cutoff]
	elif retention_count is not None and len(archives) > retention_count:
		to_delete = archives[:-retention_count]

	for p in to_delete:
		if verbose or dry_run:
			print(f"Retention: delete {p}")
		if not dry_run:
			try:
				p.unlink(missing_ok=True)
			except Exception as exc:  # pragma: no cover
				print(f"Warning: failed to delete {p}: {exc}", file=sys.stderr)


def main(argv: List[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	config = load_config(args.config)

	# Determine log directory: CLI overrides config
	config_log_dir = config.get("log_directory") if isinstance(config.get("log_directory"), str) else None
	if args.log_directory is None and not config_log_dir:
		print("Error: log_directory not provided (CLI or config)", file=sys.stderr)
		return 2
	log_dir = (args.log_directory or Path(config_log_dir)).resolve()  # type: ignore[arg-type]
	# Validate retention parameters
	if args.retention_days is not None and args.retention_days <= 0:
		print("--retention-days must be a positive integer", file=sys.stderr)
		return 2
	if args.retention_count is not None and args.retention_count <= 0:
		print("--retention-count must be a positive integer", file=sys.stderr)
		return 2
	if not log_dir.exists() or not log_dir.is_dir():
		print(f"Error: {log_dir} is not a directory", file=sys.stderr)
		return 2

	# Output dir: CLI overrides config
	config_output_dir = config.get("output_dir") if isinstance(config.get("output_dir"), str) else None
	output_dir = resolve_output_dir(log_dir, args.output_dir or (Path(config_output_dir) if config_output_dir else None))
	audit_log_path = output_dir / AUDIT_LOG_NAME

	# Patterns: merge config defaults with CLI overrides
	cfg_include = config.get("include") if isinstance(config.get("include"), list) else []
	cfg_exclude = config.get("exclude") if isinstance(config.get("exclude"), list) else []
	include_patterns = split_patterns(args.include) or [str(x) for x in cfg_include if isinstance(x, str)]
	exclude_patterns = split_patterns(args.exclude) or [str(x) for x in cfg_exclude if isinstance(x, str)]

	# Ensure output directory exists
	if not args.dry_run:
		output_dir.mkdir(parents=True, exist_ok=True)

	now = _now()
	archive_name = build_archive_name(now)
	archive_path = output_dir / archive_name

	# Enumerate files to include
	files = enumerate_files(log_dir, output_dir, audit_log_path, include_patterns, exclude_patterns)
	if args.verbose:
		print(f"Found {len(files)} files to archive")
		for f in files[:50]:
			print(f"  + {f.relative_to(log_dir)}")
		if len(files) > 50:
			print("  + ...")

	# Retention from config if CLI not provided
	if args.retention_days is None and args.retention_count is None:
		cfg_days = config.get("retention_days") if isinstance(config.get("retention_days"), int) else None
		cfg_count = config.get("retention_count") if isinstance(config.get("retention_count"), int) else None
		if cfg_days is not None and cfg_days > 0:
			args.retention_days = cfg_days
		elif cfg_count is not None and cfg_count > 0:
			args.retention_count = cfg_count

	if args.dry_run:
		# Show retention effect as well
		apply_retention(output_dir, args.retention_days, args.retention_count, dry_run=True, verbose=args.verbose)
		print("Dry run complete. No changes made.")
		return 0

	try:
		duration_ms = create_archive(log_dir, files, archive_path)
		file_count, size_bytes = compute_file_count_and_size(archive_path)
		write_audit_line(audit_log_path, now, archive_name, file_count, size_bytes, duration_ms)
		if args.verbose:
			print(f"Created {archive_path} ({file_count} files, {human_size(size_bytes)}, {duration_ms} ms)")
		# Apply retention policy after successful archive
		apply_retention(output_dir, args.retention_days, args.retention_count, dry_run=False, verbose=args.verbose)
		return 0
	except PermissionError as exc:
		write_audit_line(audit_log_path, now, archive_name, 0, 0, 0, error=str(exc))
		print(f"Permission error: {exc}", file=sys.stderr)
		return 3
	except Exception as exc:  # pragma: no cover
		try:
			write_audit_line(audit_log_path, now, archive_name, 0, 0, 0, error=str(exc))
		except Exception:
			pass
		print(f"Error: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
