# Runbook: Backup Failed

**Alert**: Playbook or knowledge graph backup failed

**Severity**: High

**Impact**: Data loss risk if primary storage fails

## Symptoms

- Alert: `backup_failed{type="playbooks|neo4j|qdrant"} == 1`
- Backup script exit code != 0
- Missing files in backup directory
- Backup age >24 hours

## Immediate Actions

### 1. Assess Backup Status (2 minutes)

```bash
# Check last successful backup
ls -lh /backups/blazing_buffalo/

# Check backup ages
find /backups/blazing_buffalo/ -name "*.tar.gz" -mtime +1  # >24 hours

# Check backup sizes (should be consistent)
du -sh /backups/blazing_buffalo/* | tail -10
```

**Decision Point:**
- Last backup >24h old → **Critical - Immediate action**
- Last backup <24h old → **Warning - Investigate**

### 2. Attempt Manual Backup (5 minutes)

```bash
# Try manual backup immediately
cd /home/pook/engineer-team

# Playbooks
./scripts/backup_playbooks.sh

# Neo4j
./scripts/backup_neo4j.sh

# Qdrant
./scripts/backup_qdrant.sh

# Check if successful
ls -lh /backups/blazing_buffalo/ | tail -3
```

## Investigation

### Check Disk Space

```bash
# Check backup destination
df -h /backups

# Check source directories
df -h /home/pook/engineer-team/playbooks
df -h /var/lib/neo4j
df -h /var/lib/qdrant
```

**If disk full:**
```bash
# Clean old backups (keep last 30 days)
find /backups/blazing_buffalo/ -name "*.tar.gz" -mtime +30 -delete

# Or compress older backups
find /backups/blazing_buffalo/ -name "*.tar.gz" -mtime +7 -mtime -30 -exec gzip {} \;
```

### Check Permissions

```bash
# Backup directory should be writable
ls -ld /backups/blazing_buffalo/
# Expected: drwxr-xr-x user user

# Source directories should be readable
ls -ld /home/pook/engineer-team/playbooks/
ls -ld /var/lib/neo4j/data/
ls -ld /var/lib/qdrant/storage/
```

**Fix permissions:**
```bash
chmod 755 /backups/blazing_buffalo/
chown user:user /backups/blazing_buffalo/
```

### Check Backup Script Logs

```bash
# Check script logs
tail -100 /var/log/backup.log

# Or journal if using systemd
journalctl -u backup-playbooks.service -n 100

# Common errors:
# - "Permission denied"
# - "No space left on device"
# - "Connection refused" (for Neo4j/Qdrant)
```

## Resolution by Backup Type

### Playbook Backup Failed

**Script**: `/home/pook/engineer-team/scripts/backup_playbooks.sh`

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/backups/blazing_buffalo/playbooks"
PLAYBOOK_DIR="/home/pook/engineer-team/playbooks"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
tar -czf "$BACKUP_DIR/playbooks_$DATE.tar.gz" \
  -C "$PLAYBOOK_DIR" \
  --exclude="*.pyc" \
  --exclude="__pycache__" \
  .

# Verify backup
tar -tzf "$BACKUP_DIR/playbooks_$DATE.tar.gz" | head -10

# Keep only last 30 days
find "$BACKUP_DIR" -name "playbooks_*.tar.gz" -mtime +30 -delete

echo "Backup successful: playbooks_$DATE.tar.gz"
```

**Test restore:**
```bash
# Extract to temp directory
mkdir -p /tmp/restore_test
tar -xzf /backups/blazing_buffalo/playbooks/playbooks_latest.tar.gz -C /tmp/restore_test

# Verify contents
ls /tmp/restore_test
python3 playbooks/validate_playbooks.py /tmp/restore_test/*.yaml
```

### Neo4j Backup Failed

**Script**: `/home/pook/engineer-team/scripts/backup_neo4j.sh`

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/backups/blazing_buffalo/neo4j"
DATE=$(date +%Y%m%d_%H%M%S)

# Dump database
docker exec neo4j neo4j-admin database dump neo4j \
  --to-path=/backups \
  --overwrite-destination=true

# Copy from container
docker cp neo4j:/backups/neo4j.dump "$BACKUP_DIR/neo4j_$DATE.dump"

# Compress
gzip "$BACKUP_DIR/neo4j_$DATE.dump"

# Keep only last 30 days
find "$BACKUP_DIR" -name "neo4j_*.dump.gz" -mtime +30 -delete

echo "Backup successful: neo4j_$DATE.dump.gz"
```

**Test restore:**
```bash
# Start test Neo4j instance
docker run -d --name neo4j-test neo4j:5.15

# Restore backup
gunzip -c /backups/blazing_buffalo/neo4j/neo4j_latest.dump.gz > /tmp/neo4j.dump
docker cp /tmp/neo4j.dump neo4j-test:/backups/
docker exec neo4j-test neo4j-admin database load neo4j --from-path=/backups

# Verify
docker exec neo4j-test cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n);"

# Cleanup
docker stop neo4j-test && docker rm neo4j-test
```

### Qdrant Backup Failed

**Script**: `/home/pook/engineer-team/scripts/backup_qdrant.sh`

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/backups/blazing_buffalo/qdrant"
DATE=$(date +%Y%m%d_%H%M%S)

# Create snapshot via API
curl -X POST "http://localhost:6333/collections/mistakes/snapshots"

# Wait for snapshot
sleep 5

# Get snapshot name
SNAPSHOT=$(curl -s "http://localhost:6333/collections/mistakes/snapshots" | jq -r '.result[0].name')

# Download snapshot
curl -o "$BACKUP_DIR/qdrant_mistakes_$DATE.snapshot" \
  "http://localhost:6333/collections/mistakes/snapshots/$SNAPSHOT"

# Keep only last 30 days
find "$BACKUP_DIR" -name "qdrant_*.snapshot" -mtime +30 -delete

echo "Backup successful: qdrant_mistakes_$DATE.snapshot"
```

**Test restore:**
```bash
# Upload snapshot
curl -X PUT "http://localhost:6333/collections/mistakes/snapshots/upload" \
  --data-binary @/backups/blazing_buffalo/qdrant/qdrant_mistakes_latest.snapshot

# Verify
curl "http://localhost:6333/collections/mistakes" | jq '.result.points_count'
```

## Automation

### Cron Job Setup

```bash
# Edit crontab
crontab -e

# Add backup jobs (run daily at 3 AM)
0 3 * * * /home/pook/engineer-team/scripts/backup_playbooks.sh >> /var/log/backup.log 2>&1
15 3 * * * /home/pook/engineer-team/scripts/backup_neo4j.sh >> /var/log/backup.log 2>&1
30 3 * * * /home/pook/engineer-team/scripts/backup_qdrant.sh >> /var/log/backup.log 2>&1

# Verify cron is running
systemctl status cron
```

### Systemd Timer (Alternative)

**Service file**: `/etc/systemd/system/backup-blazing-buffalo.service`
```ini
[Unit]
Description=Blazing Buffalo Backup
Wants=backup-blazing-buffalo.timer

[Service]
Type=oneshot
ExecStart=/home/pook/engineer-team/scripts/backup_all.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Timer file**: `/etc/systemd/system/backup-blazing-buffalo.timer`
```ini
[Unit]
Description=Run Blazing Buffalo backup daily
Requires=backup-blazing-buffalo.service

[Timer]
OnCalendar=daily
OnCalendar=03:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable:**
```bash
systemctl daemon-reload
systemctl enable backup-blazing-buffalo.timer
systemctl start backup-blazing-buffalo.timer

# Check status
systemctl status backup-blazing-buffalo.timer
systemctl list-timers backup-blazing-buffalo.timer
```

## Monitoring

### Backup Age Alert

**Prometheus Alert:**
```yaml
- alert: BackupTooOld
  expr: |
    (time() - backup_last_success_timestamp_seconds) > 86400
  for: 1h
  labels:
    severity: critical
  annotations:
    summary: "Backup for {{ $labels.type }} is >24 hours old"
    description: "Last successful backup: {{ $value | humanizeDuration }} ago"
```

### Backup Size Alert

**Prometheus Alert:**
```yaml
- alert: BackupSizeAnomaly
  expr: |
    abs(
      backup_size_bytes - avg_over_time(backup_size_bytes[7d])
    ) / avg_over_time(backup_size_bytes[7d]) > 0.5
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "Backup size changed >50% for {{ $labels.type }}"
```

### Monitoring Script

```bash
#!/bin/bash
# /home/pook/engineer-team/scripts/check_backups.sh

BACKUP_DIR="/backups/blazing_buffalo"
MAX_AGE_HOURS=24

for type in playbooks neo4j qdrant; do
  latest=$(find "$BACKUP_DIR/$type/" -type f -name "${type}_*" -mmin -$((MAX_AGE_HOURS * 60)) | head -1)

  if [ -z "$latest" ]; then
    echo "CRITICAL: No recent $type backup (>$MAX_AGE_HOURS hours)"
    exit 2
  else
    age_hours=$(( ($(date +%s) - $(stat -c %Y "$latest")) / 3600 ))
    size=$(du -h "$latest" | cut -f1)
    echo "OK: $type backup is $age_hours hours old, size: $size"
  fi
done
```

## Recovery Procedures

### Full System Recovery

**Scenario**: Complete data loss, restore from backups

```bash
# 1. Restore playbooks
tar -xzf /backups/blazing_buffalo/playbooks/playbooks_latest.tar.gz \
  -C /home/pook/engineer-team/playbooks/

# 2. Restore Neo4j
gunzip -c /backups/blazing_buffalo/neo4j/neo4j_latest.dump.gz > /tmp/neo4j.dump
docker exec neo4j neo4j-admin database load neo4j --from-path=/tmp --overwrite-destination=true
docker restart neo4j

# 3. Restore Qdrant
curl -X PUT "http://localhost:6333/collections/mistakes/snapshots/upload" \
  --data-binary @/backups/blazing_buffalo/qdrant/qdrant_mistakes_latest.snapshot
curl -X POST "http://localhost:6333/collections/mistakes/snapshots/recover"

# 4. Verify
python3 playbooks/validate_playbooks.py playbooks/**/*.yaml
curl "http://localhost:7474" # Neo4j web UI
curl "http://localhost:6333/collections/mistakes" | jq '.result.points_count'
```

## Prevention

1. **Multiple backup locations**
   - Local: `/backups/blazing_buffalo/`
   - Remote: S3/GCS/Azure Blob
   - Offsite: Different datacenter

2. **Automated monitoring**
   - Backup age checks (Prometheus)
   - Backup size validation
   - Daily email reports

3. **Regular restore testing**
   - Monthly restore test
   - Document recovery time objective (RTO)
   - Document recovery point objective (RPO)

4. **Disk space management**
   - Auto-cleanup old backups
   - Compression of archives
   - Monitor backup volume size

## Post-Incident

### Verify Data Integrity

```bash
# Compare backup with production
diff -r /home/pook/engineer-team/playbooks/ /tmp/restored_playbooks/

# Verify Neo4j counts
docker exec neo4j cypher-shell -u neo4j -p password "MATCH (n) RETURN labels(n), count(n);"

# Verify Qdrant counts
curl "http://localhost:6333/collections/mistakes" | jq '.result.points_count'
```

### Update Documentation

Document what went wrong and how it was fixed.

## Related Runbooks

- [Circuit Breaker Open](circuit-breaker-open.md)
- [High False Positive Rate](high-false-positive.md)
