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
log-archive /var/log --retention-count 7
```

- Archives are saved under `<log-directory>/archives` by default.
- Audit log is appended at `<output-dir>/archive.log`.
- Include/exclude accept glob patterns relative to `<log-directory>`.

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
