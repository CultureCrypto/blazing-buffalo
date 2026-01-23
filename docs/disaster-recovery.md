# Disaster Recovery Procedures

**Project:** Blazing Buffalo (Self-Learning Mistake System)
**Phase:** 5 - Hardening
**Version:** 1.0
**Last Updated:** 2026-01-21

## Overview

This document outlines the disaster recovery (DR) procedures for the Blazing Buffalo knowledge graph system, ensuring business continuity with defined Recovery Point Objective (RPO) and Recovery Time Objective (RTO) targets.

### Recovery Objectives

| Metric | Target | Description |
|--------|--------|-------------|
| **RPO** | 24 hours | Maximum acceptable data loss window |
| **RTO** | 2 hours | Maximum acceptable downtime for recovery |

## Architecture

The knowledge graph system consists of three primary components that require backup and recovery:

1. **Neo4j** - Relational knowledge graph database
2. **Qdrant** - Vector database for semantic embeddings
3. **Local Events** - Event logs in `.kg-events/` directory

## Backup Strategy

### Automated Daily Backups

Backups run automatically via cron at the following schedule:

```
0 1 * * * /home/pook/engineer-team/scripts/backup-kg.sh
```

**Schedule:**
- Neo4j: Daily at 1:00 AM UTC
- Qdrant: Daily at 1:00 AM UTC (after Neo4j)
- Local Events: Daily at 1:00 AM UTC (after Qdrant)

### Backup Components

#### 1. Neo4j Backup

**Method:** `neo4j-admin database dump`

```bash
docker exec engineer-team-neo4j \
    neo4j-admin database dump neo4j \
    --to-path=/tmp
```

**Output:**
- File: `backups/neo4j/neo4j-YYYYMMDD.dump.gz`
- Checksum: `backups/neo4j/neo4j-YYYYMMDD.dump.sha256`
- Compression: gzip

**Estimated Size:** 10-500 MB (depends on graph size)

#### 2. Qdrant Backup

**Method:** Snapshot API per collection

```bash
curl -X POST "http://localhost:6333/collections/{collection}/snapshots"
```

**Collections:**
- `mistakes` - Self-learning mistake patterns
- `engineer-team-knowledge` - Team knowledge base

**Output:**
- Files: `backups/qdrant/{collection}-YYYYMMDD.snapshot`
- Checksums: `backups/qdrant/{collection}-YYYYMMDD.snapshot.sha256`
- Metadata: `backups/qdrant/collections-YYYYMMDD.json`

**Estimated Size:** 50-200 MB per collection

#### 3. Local Events Backup

**Method:** Tar archive

```bash
tar -czf backups/events/kg-events-YYYYMMDD.tar.gz \
    /home/pook/engineer-team/.kg-events/
```

**Output:**
- File: `backups/events/kg-events-YYYYMMDD.tar.gz`
- Checksum: `backups/events/kg-events-YYYYMMDD.tar.gz.sha256`

**Estimated Size:** 1-50 MB

### Backup Manifest

Each backup run creates a manifest file with metadata:

```json
{
  "timestamp": "2026-01-21T01:00:00Z",
  "date": "20260121",
  "hostname": "engineer-team-host",
  "backup_type": "knowledge-graph",
  "components": {
    "neo4j": {
      "enabled": true,
      "file": "neo4j/neo4j-20260121.dump.gz"
    },
    "qdrant": {
      "enabled": true,
      "collections": ["mistakes", "engineer-team-knowledge"],
      "path": "qdrant/"
    },
    "events": {
      "enabled": true,
      "file": "events/kg-events-20260121.tar.gz"
    }
  },
  "retention_days": 30,
  "rpo_hours": 24,
  "rto_hours": 2
}
```

### Retention Policy

**Default:** 30 days

Old backups are automatically cleaned up during each backup run:

```bash
find backups/ -type f -mtime +30 -delete
```

**Storage Requirements:**
- Daily backup size: ~100-750 MB
- 30-day retention: ~3-22 GB

## Restore Procedures

### Manual Restore

**Prerequisites:**
- Access to backup directory
- Docker containers running
- Sufficient disk space

**Steps:**

1. **Identify backup date:**
   ```bash
   ls -lah /home/pook/engineer-team/backups/
   ```

2. **Preview restore (dry-run):**
   ```bash
   cd /home/pook/engineer-team
   ./scripts/restore-kg.sh --dry-run 20260121
   ```

3. **Execute restore:**
   ```bash
   ./scripts/restore-kg.sh 20260121
   ```

4. **Verify services:**
   ```bash
   # Check Neo4j
   docker exec engineer-team-neo4j cypher-shell \
       "MATCH (n) RETURN count(n) as nodes"

   # Check Qdrant
   curl http://localhost:6333/collections

   # Check events
   ls -lah .kg-events/
   ```

### Automated Restore

The restore script handles:
- Backup validation (checksums)
- Service shutdown
- Data restoration
- Service startup
- Health verification

**Estimated Restore Time:** 15-45 minutes (well within 2h RTO)

### Restore Options

```bash
# Full restore from specific date
./scripts/restore-kg.sh 20260121

# Dry-run preview
./scripts/restore-kg.sh --dry-run 20260121

# Custom backup directory
BACKUP_DIR=/path/to/backups ./scripts/restore-kg.sh 20260121
```

## Disaster Scenarios

### Scenario 1: Neo4j Data Corruption

**Detection:**
- Container fails to start
- Cypher queries fail
- Data inconsistency errors

**Recovery:**
```bash
# Stop Neo4j
docker stop engineer-team-neo4j

# Restore from latest backup
./scripts/restore-kg.sh $(date +%Y%m%d)

# Verify
docker exec engineer-team-neo4j cypher-shell "MATCH (n) RETURN count(n)"
```

**Expected RTO:** 30-60 minutes

### Scenario 2: Qdrant Collection Loss

**Detection:**
- Collection not found errors
- Empty vector search results
- API errors

**Recovery:**
```bash
# Restore from latest backup
./scripts/restore-kg.sh $(date +%Y%m%d)

# Verify collections
curl http://localhost:6333/collections
```

**Expected RTO:** 15-30 minutes

### Scenario 3: Complete System Failure

**Detection:**
- All containers down
- Host system failure
- Storage corruption

**Recovery:**
```bash
# 1. Restore Docker volumes
docker-compose down
docker volume ls | grep engineer-team

# 2. Full system restore
./scripts/restore-kg.sh $(date +%Y%m%d)

# 3. Start all services
docker-compose up -d

# 4. Verify health
./deployment/health_check.sh
```

**Expected RTO:** 1-2 hours

### Scenario 4: Accidental Data Deletion

**Detection:**
- Missing nodes/relationships
- User reports data loss
- Audit trail shows deletion

**Recovery:**
```bash
# Restore to point before deletion
# (use backup from previous day if deletion occurred today)
./scripts/restore-kg.sh 20260120

# Verify restored data
docker exec engineer-team-neo4j cypher-shell \
    "MATCH (n:Mistake) WHERE n.id = 'deleted-id' RETURN n"
```

**Expected RTO:** 20-40 minutes

## Monitoring and Alerting

### Backup Success Monitoring

**Metrics to Track:**
- Backup completion status (success/failure)
- Backup duration
- Backup file sizes
- Disk space remaining

**Alert Conditions:**
- Backup failure
- Backup duration > 30 minutes
- Disk space < 10% free
- Missing daily backup

**Implementation:**
```bash
# Check last backup status
tail -20 /home/pook/engineer-team/backups/backup-$(date +%Y%m%d).log

# Check backup size
du -sh /home/pook/engineer-team/backups/

# Check disk space
df -h /home/pook/engineer-team/backups/
```

### Recovery Testing

**Quarterly DR Drill Schedule:**
- Q1: Test Neo4j restore
- Q2: Test Qdrant restore
- Q3: Test full system restore
- Q4: Test point-in-time recovery

**DR Drill Procedure:**
```bash
# 1. Create test environment
export BACKUP_DIR=/tmp/dr-test-$(date +%s)

# 2. Run backup
./scripts/backup-kg.sh

# 3. Test restore
./scripts/restore-kg.sh --dry-run $(date +%Y%m%d)

# 4. Verify integrity
./tests/test_backup_restore.sh

# 5. Document results
# Update DR drill log
```

## Validation and Testing

### Automated Tests

Run integration tests to validate backup/restore functionality:

```bash
cd /home/pook/engineer-team
./tests/test_backup_restore.sh
```

**Test Coverage:**
- Backup creation (Neo4j, Qdrant, Events)
- Backup manifest validation
- Checksum verification
- Restore dry-run
- Retention policy
- Performance benchmarks

**Expected Results:**
```
========== TEST SUMMARY ==========
Tests Run:    9
Tests Passed: 9
Tests Failed: 0
Pass Rate:    100%
```

### Manual Validation Checklist

After each restore:

- [ ] Neo4j container healthy
- [ ] Node count matches backup manifest
- [ ] Qdrant collections accessible
- [ ] Vector point counts correct
- [ ] Event files extracted
- [ ] Application queries functional
- [ ] Relationships intact
- [ ] No data corruption warnings

## Troubleshooting

### Common Issues

#### Backup Script Fails

**Symptom:** Script exits with error

**Causes:**
- Container not running
- Insufficient disk space
- Permission errors

**Resolution:**
```bash
# Check container status
docker ps -a | grep engineer-team

# Check disk space
df -h

# Check logs
tail -50 /home/pook/engineer-team/backups/backup-$(date +%Y%m%d).log

# Retry backup
./scripts/backup-kg.sh
```

#### Restore Validation Fails

**Symptom:** Checksum mismatch

**Causes:**
- Corrupted backup file
- Incomplete download
- Storage issues

**Resolution:**
```bash
# Use previous backup
./scripts/restore-kg.sh 20260120

# If all backups corrupted, escalate to manual recovery
```

#### Services Won't Start After Restore

**Symptom:** Containers exit immediately

**Causes:**
- Corrupted data files
- Configuration mismatch
- Volume permission issues

**Resolution:**
```bash
# Check logs
docker logs engineer-team-neo4j
docker logs engineer-team-qdrant

# Reset volumes and retry
docker-compose down -v
./scripts/restore-kg.sh $(date +%Y%m%d)
```

## Maintenance Tasks

### Weekly Tasks

- [ ] Verify latest backup completed successfully
- [ ] Check backup file integrity (checksums)
- [ ] Monitor disk space usage

### Monthly Tasks

- [ ] Review retention policy effectiveness
- [ ] Audit backup logs for failures
- [ ] Test restore in staging environment

### Quarterly Tasks

- [ ] Execute DR drill (see schedule above)
- [ ] Update DR documentation
- [ ] Review and optimize backup scripts
- [ ] Validate RTO/RPO targets

## Contact Information

**DR Coordinator:** Engineering Team
**Escalation Path:**
1. Check automated backups
2. Attempt automated restore
3. Consult this documentation
4. Escalate to senior engineer

## Appendix

### File Locations

```
/home/pook/engineer-team/
├── backups/                           # Backup storage
│   ├── neo4j/                        # Neo4j dumps
│   ├── qdrant/                       # Qdrant snapshots
│   ├── events/                       # Event archives
│   └── *.log                         # Backup logs
├── scripts/
│   ├── backup-kg.sh                  # Backup script
│   └── restore-kg.sh                 # Restore script
├── tests/
│   └── test_backup_restore.sh        # Integration tests
└── docs/
    └── disaster-recovery.md          # This document
```

### Cron Configuration

Install backup cron job:

```bash
# Edit crontab
crontab -e

# Add daily backup at 1 AM UTC
0 1 * * * /home/pook/engineer-team/scripts/backup-kg.sh >> /home/pook/engineer-team/backups/cron.log 2>&1
```

### Environment Variables

```bash
# Backup configuration
export BACKUP_DIR="/home/pook/engineer-team/backups"
export RETENTION_DAYS="30"
export BACKUP_NEO4J="true"
export BACKUP_QDRANT="true"
export BACKUP_EVENTS="true"

# Restore configuration
export DRY_RUN="false"
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-21 | Initial disaster recovery procedures |

---

**Document Status:** Active
**Next Review:** 2026-04-21 (Quarterly)
