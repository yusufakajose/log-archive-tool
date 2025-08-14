# Log Archive Tool

CLI to archive logs from a directory into a timestamped `.tar.gz` and write an audit entry.

## Install (editable local)
```bash
pip install -e .
```

## Usage
```bash
log-archive <log-directory> [--output-dir <dir>] [--retention-days N | --retention-count N] \
  [--include "pat1,pat2"] [--exclude "pat3,pat4"] [--dry-run] [--verbose] [--config <path>] \
  [--incremental] [--manifest <path>] [--sha256] [--gpg-encrypt] [--gpg-recipients <csv>] [--gpg-sign]
```

Example:
```bash
log-archive /var/log --retention-count 7
```

- Archives are saved under `<log-directory>/archives` by default.
- Audit log is appended at `<output-dir>/archive.log`.
- Include/exclude accept glob patterns relative to `<log-directory>`.

## Incremental mode
Archive only files that changed since the last run. A manifest file records file size and modified time.

- Enable: `--incremental`
- Default manifest path: `<output_dir>/manifest.json` (override with `--manifest`)

Example:
```bash
log-archive /var/log --incremental
```

## Integrity and security
- `--sha256`: Write a `<archive>.tar.gz.sha256` file with the checksum.
- `--gpg-encrypt --gpg-recipients alice@example.com,bob@example.com`: Encrypt the archive to recipients and delete the plaintext.
- `--gpg-sign`: Create a detached signature `<archive>.sig` (useful for verifying origin).

Note: Requires `gpg` available and configured (keys present).

## Config file (TOML)
You can set defaults so you don’t have to pass flags every time. Precedence: CLI > config > defaults.

Search order if `--config` not provided:
1. `$LOG_ARCHIVE_CONFIG`
2. `$XDG_CONFIG_HOME/log-archive/config.toml`
3. `~/.config/log-archive/config.toml`

Example `~/.config/log-archive/config.toml`:
```toml
log_directory = "/var/log"
output_dir    = "/var/log/archives"

include = ["*.log", "nginx/**"]
exclude = ["archives/**", "*.tmp"]

# choose one:
retention_days  = 14
# retention_count = 7
```

## Scheduling

### Cron (daily at 02:00)
```cron
0 2 * * * /usr/local/bin/log-archive /var/log >> /var/log/archives/cron.log 2>&1
```

### systemd timer (outline)
Create `/etc/systemd/system/log-archive.service`:
```ini
[Unit]
Description=Archive system logs

[Service]
Type=oneshot
ExecStart=/usr/local/bin/log-archive /var/log --retention-count 14
```

Create `/etc/systemd/system/log-archive.timer`:
```ini
[Unit]
Description=Run log archive daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now log-archive.timer
```

## Permissions
Archiving `/var/log` may require elevated permissions to read some files. Use `sudo` if needed:
```bash
sudo log-archive /var/log
```

## Development
- Dry run: `python3 -m log_archive --dry-run samples/logs`
- Real run: `python3 -m log_archive samples/logs`

See `PLAN.md` for detailed design.
