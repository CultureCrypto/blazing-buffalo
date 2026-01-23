# Playbook Lifecycle

Understand how playbooks age, decay, and get archived to maintain system health.

## Lifecycle States

Playbooks progress through three states based on usage and performance:

```
┌─────────────┐
│   ACTIVE    │  Regular usage, good performance
└─────────────┘
      ↓ (30 days unused OR 90 days unused OR >30% failures)
┌─────────────┐
│   NEEDS     │  Flagged for human review
│ REVALIDATION│
└─────────────┘
      ↓ (180 days unused OR confidence <0.3)
┌─────────────┐
│  ARCHIVED   │  Moved to archived/ directory
└─────────────┘
```

## Lifecycle Rules

| Rule | Threshold | Action | Reversible |
|------|-----------|--------|------------|
| Confidence decay | 30 days unused | Reduce confidence by 0.1 | Auto (on next use) |
| Revalidation flag | 90 days unused OR >30% failure rate | Mark needs_revalidation=true | Manual review |
| Archive | 180 days unused OR confidence <0.3 | Move to playbooks/archived/ | Manual restore |

## State Transitions

### ACTIVE → NEEDS_REVALIDATION

**Triggers:**
- Playbook unused for 90+ days
- Failure rate >30% (failures / total executions)
- Confidence dropped below 0.5

**What happens:**
```yaml
metadata:
  lifecycle_state: "NEEDS_REVALIDATION"
  needs_revalidation: true
  revalidation_reason: "Unused for 92 days"
  flagged_at: "2026-01-21T10:00:00Z"
```

**Playbook still executes**, but logged for review.

### NEEDS_REVALIDATION → ACTIVE

**After manual review:**

```python
from lib.playbook_lifecycle import PlaybookLifecycleManager

manager = PlaybookLifecycleManager()

# Review playbook and update confidence
manager.revalidate(
    playbook_id="pb_a21ad52afbd2",
    new_confidence=0.9,
    reviewed_by="admin",
    notes="Tested manually, works correctly"
)
```

### ACTIVE → ARCHIVED

**Triggers:**
- Playbook unused for 180+ days
- Confidence <0.3
- Manual archival

**What happens:**
```bash
# File moved
mv playbooks/pb_old.yaml playbooks/archived/pb_old.yaml

# Metadata updated
metadata:
  lifecycle_state: "ARCHIVED"
  archived_at: "2026-01-21T10:00:00Z"
  archive_reason: "Unused for 185 days"
```

**Playbook no longer executes automatically.**

### ARCHIVED → ACTIVE

**Manual restore:**

```bash
# Move file back
mv playbooks/archived/pb_old.yaml playbooks/pb_old.yaml

# Update metadata
python3 -c "
import yaml
with open('playbooks/pb_old.yaml') as f:
    pb = yaml.safe_load(f)

del pb['metadata']['archived_at']
del pb['metadata']['archive_reason']
pb['metadata']['lifecycle_state'] = 'ACTIVE'
pb['metadata']['confidence'] = 0.8  # Reset confidence

with open('playbooks/pb_old.yaml', 'w') as f:
    yaml.dump(pb, f)
"
```

## Confidence Decay

### How It Works

Confidence decreases over time to reflect potential staleness:

```python
# Every 30 days of inactivity
new_confidence = max(0.3, current_confidence - 0.1)
```

**Example timeline:**

| Days Unused | Confidence | State |
|-------------|------------|-------|
| 0 | 0.95 | ACTIVE |
| 30 | 0.85 | ACTIVE (decayed) |
| 60 | 0.75 | ACTIVE (decayed) |
| 90 | 0.65 | NEEDS_REVALIDATION |
| 120 | 0.55 | NEEDS_REVALIDATION |
| 150 | 0.45 | NEEDS_REVALIDATION |
| 180 | 0.35 | NEEDS_REVALIDATION |
| 210 | 0.30 | ARCHIVED (min threshold) |

### Reversing Decay

Confidence recovers with successful executions:

```python
# On successful execution
success_boost = 0.05
new_confidence = min(1.0, current_confidence + success_boost)
```

## Failure Rate Monitoring

### Calculation

```python
failure_rate = failure_count / (success_count + failure_count)
```

**Example:**

| Successes | Failures | Rate | Action |
|-----------|----------|------|--------|
| 45 | 5 | 10% | None |
| 35 | 15 | 30% | Flag for revalidation |
| 25 | 25 | 50% | Circuit breaker opens |

### Auto-Revalidation Trigger

```yaml
# When failure_rate > 0.3
metadata:
  success_count: 14
  failure_count: 6
  failure_rate: 0.3
  needs_revalidation: true
  revalidation_reason: "High failure rate: 30%"
```

## Maintenance Automation

### Cron Job Setup

Run daily maintenance to apply lifecycle rules:

```bash
# Add to crontab
crontab -e

# Run daily at 2 AM
0 2 * * * cd /home/pook/engineer-team && python3 scripts/playbook_maintenance.py >> /var/log/playbook_maintenance.log 2>&1
```

### Manual Maintenance

```bash
# Run maintenance script
python3 scripts/playbook_maintenance.py

# Dry run (see what would happen)
python3 scripts/playbook_maintenance.py --dry-run --verbose

# Custom playbook directory
python3 scripts/playbook_maintenance.py --playbook-dir /custom/path
```

### Maintenance Output

```
Running playbook maintenance on: /home/pook/engineer-team/playbooks
Started at: 2026-01-21T10:00:00

Maintenance Summary:
  Total playbooks: 23
  Events generated: 5

Event Types:
  confidence_decay: 3
  revalidation_required: 1
  archived: 1

Event Details:
  pb_old_playbook_1 - confidence_decay
    Reason: 32 days unused
    Change: 0.95 -> 0.85

  pb_old_playbook_2 - confidence_decay
    Reason: 65 days unused
    Change: 0.75 -> 0.65

  pb_failed_playbook - revalidation_required
    Reason: High failure rate: 35%
    Current state: NEEDS_REVALIDATION

  pb_very_old - archived
    Reason: Unused for 185 days
    Moved to: playbooks/archived/pb_very_old.yaml

Completed at: 2026-01-21T10:00:15
```

## Revalidation Workflow

### 1. Identify Playbooks Needing Review

```bash
# List flagged playbooks
curl http://localhost:8200/playbooks?state=NEEDS_REVALIDATION

# Or via file system
grep -l "needs_revalidation: true" playbooks/*.yaml
```

### 2. Review Playbook

```python
import yaml

# Load playbook
with open('playbooks/pb_flagged.yaml') as f:
    playbook = yaml.safe_load(f)

# Check metrics
print(f"Usage count: {playbook['metadata']['usage_count']}")
print(f"Success rate: {playbook['metadata']['success_rate']}")
print(f"Last used: {playbook['metadata']['last_used']}")
print(f"Confidence: {playbook['metadata']['confidence']}")

# Check why flagged
print(f"Reason: {playbook['metadata']['revalidation_reason']}")
```

### 3. Test Manually

```bash
# Execute in dry-run mode
curl -X POST http://localhost:8200/playbooks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "pb_flagged",
    "context": {"file_path": "test.py"},
    "dry_run": true
  }'
```

### 4. Update Confidence

```python
from lib.playbook_lifecycle import PlaybookLifecycleManager

manager = PlaybookLifecycleManager()

# Option A: Approve and boost confidence
manager.revalidate(
    playbook_id="pb_flagged",
    new_confidence=0.9,
    reviewed_by="admin",
    notes="Tested successfully, works as expected"
)

# Option B: Archive if no longer needed
manager.archive_playbook(
    playbook_id="pb_flagged",
    reason="No longer applicable to codebase"
)
```

## Archive Management

### List Archived Playbooks

```bash
# Via filesystem
ls -lh playbooks/archived/

# Via API
curl http://localhost:8200/playbooks?state=ARCHIVED
```

### Restore Archived Playbook

```python
from pathlib import Path
import yaml
import shutil

# Move file
archived_path = Path("playbooks/archived/pb_old.yaml")
active_path = Path("playbooks/pb_old.yaml")
shutil.move(archived_path, active_path)

# Update metadata
with open(active_path) as f:
    playbook = yaml.safe_load(f)

playbook['metadata']['lifecycle_state'] = 'ACTIVE'
playbook['metadata']['confidence'] = 0.8
del playbook['metadata']['archived_at']
del playbook['metadata']['archive_reason']

with open(active_path, 'w') as f:
    yaml.dump(playbook, f)

print(f"Restored: {active_path}")
```

### Permanently Delete Archived Playbooks

```bash
# Review old archives (>1 year)
find playbooks/archived/ -name "*.yaml" -mtime +365

# Delete after review
find playbooks/archived/ -name "*.yaml" -mtime +365 -delete
```

## Configuration

### Adjust Thresholds

Edit `lib/playbook_lifecycle.py`:

```python
class PlaybookLifecycleManager:
    # Confidence decay
    CONFIDENCE_DECAY_DAYS = 30          # Days between decay
    CONFIDENCE_DECAY_AMOUNT = 0.1       # Amount to decay

    # Revalidation
    REVALIDATION_DAYS = 90              # Days until revalidation
    MAX_FAILURE_RATE = 0.3              # Maximum failure rate (30%)

    # Archival
    ARCHIVE_DAYS = 180                  # Days until archival
    MIN_CONFIDENCE = 0.3                # Minimum confidence
```

### Custom Thresholds Per Playbook

```yaml
# Override global thresholds
metadata:
  confidence: 0.95
  custom_thresholds:
    decay_days: 60                     # Decay slower (60 vs 30 days)
    min_confidence: 0.5                # Lower minimum (0.5 vs 0.3)
    archive_days: 365                  # Archive later (365 vs 180 days)
```

## Event Tracking

All lifecycle events are logged:

```python
from lib.playbook_lifecycle import PlaybookLifecycleManager

manager = PlaybookLifecycleManager()

# Run maintenance
events = manager.run_maintenance()

# Analyze events
for event in events:
    print(f"Playbook: {event.playbook_id}")
    print(f"Event: {event.event_type}")
    print(f"Timestamp: {event.timestamp}")
    print(f"Reason: {event.reason}")

    if event.old_value is not None:
        print(f"Change: {event.old_value} -> {event.new_value}")
```

**Event types:**
- `confidence_decay` - Confidence reduced due to age
- `revalidation_required` - Flagged for review
- `archived` - Moved to archive
- `restored` - Restored from archive

## Best Practices

### 1. Regular Maintenance

```bash
# Run daily maintenance
0 2 * * * cd /home/pook/engineer-team && python3 scripts/playbook_maintenance.py

# Weekly reports
0 3 * * 0 cd /home/pook/engineer-team && python3 scripts/playbook_maintenance.py --verbose > /tmp/weekly_report.txt && mail -s "Playbook Report" admin@example.com < /tmp/weekly_report.txt
```

### 2. Monitor Revalidation Queue

```bash
# Check weekly
curl http://localhost:8200/playbooks?state=NEEDS_REVALIDATION
```

### 3. Don't Auto-Archive Critical Playbooks

```yaml
# Mark as critical
metadata:
  critical: true
  custom_thresholds:
    archive_days: 9999  # Effectively disable auto-archive
```

### 4. Track Restoration Reasons

```yaml
# When restoring, note why
metadata:
  restored_at: "2026-01-21T10:00:00Z"
  restored_by: "admin"
  restoration_reason: "Pattern re-emerged in new codebase"
```

### 5. Periodic Archive Cleanup

```bash
# Quarterly review
find playbooks/archived/ -name "*.yaml" -mtime +90 -exec grep -l "confidence" {} \; | while read f; do
  echo "Review: $f"
  # Manual decision: delete or restore
done
```

## Troubleshooting

### Playbook Unexpectedly Archived

Check archive metadata:

```bash
grep -A 5 "archive_reason" playbooks/archived/pb_old.yaml
```

**Common reasons:**
- `Unused for X days` - Increase ARCHIVE_DAYS threshold
- `Low confidence: X` - Confidence decayed below MIN_CONFIDENCE
- `Manual archival` - Archived by user/script

### Confidence Decaying Too Fast

```python
# Adjust decay rate
CONFIDENCE_DECAY_DAYS = 60      # Slower decay (60 vs 30 days)
CONFIDENCE_DECAY_AMOUNT = 0.05  # Smaller decay (0.05 vs 0.1)
```

### Too Many Revalidation Requests

```python
# Increase threshold
REVALIDATION_DAYS = 180         # Later flagging (180 vs 90 days)
MAX_FAILURE_RATE = 0.5          # Higher tolerance (50% vs 30%)
```

### Playbook Not Recovering Confidence

Ensure successful executions are tracked:

```python
# After successful playbook execution
playbook.metadata.success_count += 1
playbook.metadata.confidence = min(1.0, playbook.metadata.confidence + 0.05)
playbook.metadata.last_used = datetime.now()
```

## Metrics & Monitoring

### Lifecycle Health Dashboard

```python
# Get lifecycle stats
stats = {
    "total_playbooks": 23,
    "by_state": {
        "ACTIVE": 18,
        "NEEDS_REVALIDATION": 3,
        "ARCHIVED": 2
    },
    "avg_confidence": 0.84,
    "playbooks_needing_review": 3,
    "avg_days_since_use": 45.2
}
```

### Alerting

```python
# Alert on too many flagged playbooks
if stats["by_state"]["NEEDS_REVALIDATION"] > 5:
    send_alert("5+ playbooks need revalidation")

# Alert on low average confidence
if stats["avg_confidence"] < 0.7:
    send_alert(f"Average confidence low: {stats['avg_confidence']}")
```

## Next Steps

- **[Creating Playbooks](creating.md)** - Build new playbooks
- **[Best Practices](best-practices.md)** - Advanced techniques
- **[Troubleshooting](../troubleshooting.md)** - Common issues
