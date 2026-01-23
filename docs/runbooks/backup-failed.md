# Runbook: Backup Failed

**Alert**: `BackupFailed`
**Severity**: Critical
**Component**: Backup System

## Symptoms

No successful knowledge graph backup in the last 24 hours.

## Impact

- **CRITICAL**: Risk of data loss if system failure occurs
- No point-in-time recovery available
- Compliance violations (data retention policy)
- Cannot restore to known-good state

## Investigation

### 1. Check backup job status

```bash
# Check last backup attempt
systemctl status blazing-buffalo-backup

# View backup logs
journalctl -u blazing-buffalo-backup --since "24 hours ago" | tail -100

# Check backup script execution
tail -f /var/log/blazing-buffalo/backup.log
```

### 2. Verify backup destination

```bash
# Check disk space on backup volume
df -h /backup/blazing-buffalo

# List recent backups
ls -lth /backup/blazing-buffalo/*.tar.gz | head -20

# Check S3 backup status (if applicable)
aws s3 ls s3://blazing-buffalo-backups/ --recursive | tail -20
```

### 3. Check database connectivity

```bash
# Test Neo4j connection
curl -u neo4j:password http://localhost:7474/db/data/

# Check Qdrant connection
curl http://localhost:6333/collections

# Verify PostgreSQL
psql -d blazing_buffalo -c "SELECT COUNT(*) FROM mistakes;"
```

## Resolution

### Immediate Actions (URGENT)

1. **Attempt manual backup NOW**:
   ```bash
   # Run backup script manually
   sudo -u backup /home/pook/engineer-team/scripts/backup_knowledge_graph.sh

   # Check if successful
   echo $?  # Should be 0
   ```

2. **Verify backup integrity**:
   ```bash
   # Test restore to separate location
   mkdir -p /tmp/backup-test
   tar -xzf /backup/blazing-buffalo/latest.tar.gz -C /tmp/backup-test

   # Verify contents
   ls -la /tmp/backup-test
   ```

### Fix Backup System

#### Issue: Disk space full

```bash
# Clean up old backups (keep last 30 days)
find /backup/blazing-buffalo -name "*.tar.gz" -mtime +30 -delete

# Compress existing backups further
gzip -9 /backup/blazing-buffalo/*.tar
```

#### Issue: Permissions problem

```bash
# Fix ownership
sudo chown -R backup:backup /backup/blazing-buffalo

# Fix permissions
sudo chmod 750 /backup/blazing-buffalo
sudo chmod 640 /backup/blazing-buffalo/*.tar.gz
```

#### Issue: Backup script failing

```bash
# Check script syntax
bash -n /home/pook/engineer-team/scripts/backup_knowledge_graph.sh

# Run in debug mode
bash -x /home/pook/engineer-team/scripts/backup_knowledge_graph.sh
```

#### Issue: Database dump failing

```bash
# Test Neo4j backup directly
neo4j-admin backup --backup-dir=/tmp/neo4j-test --name=test-backup

# Test Qdrant snapshot
curl -X POST "http://localhost:6333/collections/mistakes/snapshots"

# Test PostgreSQL dump
pg_dump -U postgres blazing_buffalo > /tmp/test_dump.sql
```

### Re-enable Automated Backups

```bash
# Restart backup timer
systemctl restart blazing-buffalo-backup.timer

# Verify schedule
systemctl list-timers | grep backup

# Monitor next execution
journalctl -u blazing-buffalo-backup -f
```

## Prevention

1. **Implement backup monitoring**:
   ```bash
   # Add healthcheck endpoint
   curl http://localhost:8000/api/backup/health
   ```

2. **Set up backup redundancy**:
   - Primary: Local disk backups
   - Secondary: S3/object storage
   - Tertiary: Off-site replication

3. **Automated backup testing**:
   ```bash
   # Schedule weekly restore tests
   crontab -e
   # Add: 0 2 * * 0 /scripts/test_backup_restore.sh
   ```

4. **Increase backup frequency during high-activity periods**:
   ```bash
   # Edit backup schedule
   vim /etc/systemd/system/blazing-buffalo-backup.timer
   # Change OnCalendar from daily to every 12h
   ```

## Recovery Procedure (If Data Loss Occurred)

1. **Stop all services**:
   ```bash
   systemctl stop blazing-buffalo-api
   systemctl stop blazing-buffalo-rca
   ```

2. **Restore from latest backup**:
   ```bash
   /home/pook/engineer-team/scripts/restore_knowledge_graph.sh /backup/blazing-buffalo/latest.tar.gz
   ```

3. **Verify restoration**:
   ```bash
   # Check record counts
   psql -d blazing_buffalo -c "SELECT COUNT(*) FROM mistakes;"
   curl http://localhost:6333/collections/mistakes
   ```

4. **Restart services**:
   ```bash
   systemctl start blazing-buffalo-api
   systemctl start blazing-buffalo-rca
   ```

## Escalation

**ESCALATE IMMEDIATELY - This is a critical alert**

- Notify: @platform-team, @cto
- Channel: #incidents (not #blazing-buffalo)
- Page: On-call SRE
- Include:
  - Time of last successful backup
  - Current backup status
  - Root cause analysis
  - Data at risk estimation
