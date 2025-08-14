# Log Archive Tool

CLI to archive logs from a directory into a timestamped `.tar.gz` and write an audit entry.

## Install (editable local)
```bash
pip install -e .
```

## Usage
```bash
log-archive <log-directory> [--output-dir <dir>] [--retention-days N | --retention-count N] \
  [--include "pat1,pat2"] [--exclude "pat3,pat4"] [--dry-run] [--verbose]
```

Example:
```bash
log-archive /var/log
```

See `PLAN.md` for detailed design.
