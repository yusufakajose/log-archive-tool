## Log Archive Tool — Planning

### Goals
- **Build a simple CLI** that archives logs from a specified directory.
- **Create compressed archives** (`.tar.gz`) named with date/time.
- **Store archives in a new directory** separate from active logs.
- **Record each archive operation** with timestamp and basic stats in a log file.
- **Make it schedulable** via cron/systemd (run once per invocation; external scheduler triggers it).

### Requirements (recap)
- CLI usage: `log-archive <log-directory>`
- Output archive format: `logs_archive_YYYYMMDD_HHMMSS.tar.gz`
- Must write a record of the archive (date/time at minimum) to a file.
- Default logs location is often `/var/log`, but tool should accept any path.

### Assumptions
- The tool will be implemented in **Python 3.10+** for portability and standard library support (`argparse`, `pathlib`, `tarfile`, `logging`).
- Archives will be placed in `<log-directory>/archives` by default (created if missing).
- The archive includes files and subdirectories under `<log-directory>`, excluding the `archives` directory itself and the archive log file.
- Timestamps use the **local timezone** in the filename; the audit log will include both local and ISO 8601 forms for clarity.
- Permissions for `/var/log` may require `sudo`; the tool will not escalate privileges itself.

### CLI UX
- **Name**: `log-archive`
- **Usage**:
```bash
log-archive <log-directory> [--output-dir <dir>] [--retention-days N | --retention-count N] \
  [--include "pattern1,pattern2"] [--exclude "pattern3,pattern4"] [--dry-run] [--verbose]
```
- **Arguments**:
  - **positional `log_directory`**: Source directory to archive.
  - **`--output-dir`**: Destination for archives and audit log (default: `<log_directory>/archives`).
  - **`--retention-days`**: Remove archives older than N days after creating the new one.
  - **`--retention-count`**: Keep only the most recent N archives.
  - **`--include`**: Comma-separated glob patterns to include (default: include everything except excluded items).
  - **`--exclude`**: Comma-separated glob patterns to exclude (in addition to built-ins like the output dir and audit log).
  - **`--dry-run`**: Show what would be archived and what would be deleted by retention without writing files.
  - **`--verbose`**: More detailed console output.
- **Exit codes**:
  - `0` success; `1` general error; `2` invalid arguments; `3` permission issues.

### Archive behavior
- **Archive name**: `logs_archive_YYYYMMDD_HHMMSS.tar.gz` (local time).
- **Included paths**: All files/subdirectories under `<log_directory>` except:
  - `<output_dir>` (the archives directory),
  - the audit log file (see below),
  - any user-specified `--exclude` patterns.
- **Empty or missing files**: Tool succeeds even if there are no files to archive, producing an empty tarball (or optionally skip archive if truly nothing changed in the future enhancement).
- **Symlinks**: Store symlinks as links by default; a future `--follow-symlinks` flag can alter this.

### Directory layout
- Given `log_directory=/var/log` and default `output_dir`:
```
/var/log/
  ... active logs ...
  archives/
    logs_archive_20240816_100648.tar.gz
    archive.log
```

### Audit logging
- **Audit file**: `<output_dir>/archive.log`
- **Record format**: One line per run, e.g.:
```
2024-08-16T10:06:48+02:00 | local=2024-08-16 10:06:48 | archive=logs_archive_20240816_100648.tar.gz | files=152 | size=12.3MB | duration_ms=842
```
- **On error**: Write an error line with message and non-zero exit.

### Scheduling (external)
- The tool runs once per invocation. Scheduling is done externally.
- **Cron example** (daily at 02:00):
```bash
0 2 * * * /usr/local/bin/log-archive /var/log >> /var/log/archives/cron.log 2>&1
```
- **systemd timer** (outline):
  - Service unit runs `log-archive /var/log`
  - Timer unit with `OnCalendar=daily` (document exact unit files in README when implemented)

### Retention policy
- Optional; controlled by flags.
- Two modes (mutually exclusive):
  - **Time-based**: `--retention-days N` deletes archives older than N days.
  - **Count-based**: `--retention-count N` keeps only newest N archives.
- Deletions apply only to files matching `logs_archive_*.tar.gz` in `output_dir`.

### Error handling & validations
- Verify `log_directory` exists and is a directory.
- Create `output_dir` if missing.
- Ensure `output_dir` is not inside an excluded path conflict.
- Handle permission errors gracefully with clear messages and exit code 3.
- Validate mutually exclusive flags and numeric ranges.

### Implementation plan
1. **Scaffold**
   - Create project structure: `log_archive/` package, `__main__.py`, and `pyproject.toml` with console script `log-archive`.
2. **Argument parsing**
   - Implement `argparse` schema and validations (exclusive retention flags, parsing patterns).
3. **Discovery & filtering**
   - Walk `log_directory` and compute set of paths to include, respecting include/exclude and built-in exclusions.
4. **Archiving**
   - Build archive name using formatted local timestamp.
   - Create `.tar.gz` via `tarfile` with safe relative paths.
   - Measure duration and size.
5. **Audit log**
   - Append structured line to `archive.log` (create file if missing).
6. **Retention**
   - Apply selected retention policy (time- or count-based).
7. **Dry run & verbosity**
   - Print planned operations without writing, when `--dry-run` is set.
8. **Packaging & install**
   - Provide `pyproject.toml` and `README.md` for `pipx`/pip install and usage.
9. **Testing**
   - Create a sample log tree under `samples/logs/` and add a small test script.
   - Manual tests for empty directory, deep trees, permission errors, and retention.

### Testing plan (manual + scripted)
- Create temporary directories with fake `.log` files and rotated logs.
- Run once without retention; verify archive contents and audit log line.
- Run with `--retention-count 2`; verify only 2 newest remain.
- Run with include/exclude patterns; verify filtering.
- Attempt run on `/var/log` in a safe environment to validate permissions.

### Acceptance criteria
- Running `log-archive /some/logs` produces a `logs_archive_YYYYMMDD_HHMMSS.tar.gz` in an `archives` directory.
- An `archive.log` line is appended with timestamp, archive name, file count, size, and duration.
- Excluding the `archives` directory and audit log from the archive is guaranteed.
- Optional retention removes old archives per provided flag.
- Tool exits with appropriate codes and helpful messages.

### Future enhancements
- `--follow-symlinks` behavior toggle.
- Detect unchanged input and skip new archive if nothing changed since last run.
- Parallel compression for large trees.
- JSON audit output option for machine parsing.
- Native Windows support (paths and permissions nuances).
