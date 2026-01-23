# Blazing Buffalo Runbooks

This directory contains operational runbooks for responding to Blazing Buffalo alerts.

## Available Runbooks

### Circuit Breaker Alerts
- [circuit-breaker-open.md](circuit-breaker-open.md) - Single playbook circuit breaker opened
- [multiple-circuits-open.md](multiple-circuits-open.md) - Multiple circuit breakers opened (systemic issue)
- [circuit-breaker-flapping.md](circuit-breaker-flapping.md) - Circuit breaker state oscillating

### Detection Accuracy Alerts
- [high-false-positive.md](high-false-positive.md) - False positive rate exceeds threshold
- [low-playbook-success.md](low-playbook-success.md) - Playbook success rate low
- [critical-playbook-failure.md](critical-playbook-failure.md) - Playbook failing most executions
- [increasing-rejections.md](increasing-rejections.md) - User rejection rate trending up

### Performance Alerts
- [rca-latency-high.md](rca-latency-high.md) - RCA pipeline slow
- [rca-latency-critical.md](rca-latency-critical.md) - RCA pipeline critically slow
- [rca-rate-limit.md](rca-rate-limit.md) - Rate limiting active
- [rca-error-rate.md](rca-error-rate.md) - RCA error rate high

### Data Protection Alerts
- [backup-failed.md](backup-failed.md) - Backup system failure (CRITICAL)
- [backup-aging.md](backup-aging.md) - Backup SLA approaching
- [backup-size-anomaly.md](backup-size-anomaly.md) - Unexpected backup size change

### System Health Alerts
- [taxonomy-cluster-explosion.md](taxonomy-cluster-explosion.md) - Too many taxonomy clusters
- [no-mistakes-detected.md](no-mistakes-detected.md) - Detection system quiet
- [playbook-spike.md](playbook-spike.md) - Unusual spike in executions
- [high-memory.md](high-memory.md) - Memory usage high
- [kg-stale.md](kg-stale.md) - Knowledge graph not updated

### Maintenance Alerts
- [playbook-version-mismatch.md](playbook-version-mismatch.md) - Multiple playbook versions active
- [playbook-cleanup.md](playbook-cleanup.md) - Deprecated playbook needs removal

## Runbook Template

Each runbook follows this structure:

1. **Alert Details** - Name, severity, component
2. **Symptoms** - What's happening
3. **Impact** - Why it matters
4. **Investigation** - How to diagnose
5. **Resolution** - How to fix
6. **Prevention** - How to avoid
7. **Escalation** - When and who to notify

## Quick Reference

| Severity | Response Time | Escalation | Channel |
|----------|--------------|------------|---------|
| Critical | Immediate | Page on-call | #incidents |
| Warning | 30 minutes | Notify team | #blazing-buffalo-oncall |
| Info | Next business day | Track in backlog | #blazing-buffalo |

## Emergency Contacts

- **Platform Team**: @platform-oncall
- **Engineering Team**: @engineering-oncall
- **ML Team**: @ml-team
- **CTO**: @cto (critical alerts only)

## Related Documentation

- [Metrics Documentation](/home/pook/engineer-team/lib/metrics.py)
- [Alert Rules](/home/pook/engineer-team/monitoring/alerts.yaml)
- [System Architecture](/home/pook/engineer-team/docs/architecture.mmd)
- [Playbook Lifecycle](/home/pook/engineer-team/docs/PLAYBOOK_RESOLVER.md)
