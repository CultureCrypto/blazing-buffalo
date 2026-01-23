#!/bin/bash
#
# Blazing Buffalo - Knowledge Graph Backup Script
# Daily automated backup of Neo4j, Qdrant, and local events
# RPO: 24h, RTO: 2h
#

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

BACKUP_DIR="${BACKUP_DIR:-/home/pook/engineer-team/backups}"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
LOG_FILE="${BACKUP_DIR}/backup-${DATE}.log"

# Component flags
BACKUP_NEO4J="${BACKUP_NEO4J:-true}"
BACKUP_QDRANT="${BACKUP_QDRANT:-true}"
BACKUP_EVENTS="${BACKUP_EVENTS:-true}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
    log "INFO" "$*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
    log "SUCCESS" "$*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
    log "WARN" "$*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
    log "ERROR" "$*"
}

# ============================================================================
# BACKUP FUNCTIONS
# ============================================================================

backup_neo4j() {
    if [ "$BACKUP_NEO4J" != "true" ]; then
        log_info "Neo4j backup disabled"
        return 0
    fi

    log_info "Starting Neo4j backup..."

    local backup_path="${BACKUP_DIR}/neo4j"
    mkdir -p "$backup_path"

    # Check if Neo4j is running
    if ! docker ps | grep -q engineer-team-neo4j; then
        log_error "Neo4j container not running"
        return 1
    fi

    # Create database dump using neo4j-admin
    log_info "Creating Neo4j database dump..."

    # Dump to temp location inside container
    docker exec engineer-team-neo4j \
        neo4j-admin database dump neo4j \
        --to-path=/tmp 2>&1 | tee -a "$LOG_FILE" || {
        log_error "Neo4j dump failed"
        return 1
    }

    # Copy dump from container to backup directory
    docker cp engineer-team-neo4j:/tmp/neo4j.dump \
        "${backup_path}/neo4j-${DATE}.dump" || {
        log_error "Failed to copy Neo4j dump"
        return 1
    }

    # Create checksum
    sha256sum "${backup_path}/neo4j-${DATE}.dump" > \
        "${backup_path}/neo4j-${DATE}.dump.sha256"

    # Compress backup
    gzip -f "${backup_path}/neo4j-${DATE}.dump"

    log_success "Neo4j backup completed: neo4j-${DATE}.dump.gz"
    return 0
}

backup_qdrant() {
    if [ "$BACKUP_QDRANT" != "true" ]; then
        log_info "Qdrant backup disabled"
        return 0
    fi

    log_info "Starting Qdrant backup..."

    local backup_path="${BACKUP_DIR}/qdrant"
    mkdir -p "$backup_path"

    # Check if Qdrant is accessible
    if ! curl -sf http://localhost:6333/health > /dev/null 2>&1; then
        log_error "Qdrant not accessible"
        return 1
    fi

    # Create snapshots for each collection
    local collections=("mistakes" "engineer-team-knowledge")

    for collection in "${collections[@]}"; do
        log_info "Creating snapshot for collection: $collection"

        # Trigger snapshot creation
        snapshot_name=$(curl -sf -X POST \
            "http://localhost:6333/collections/${collection}/snapshots" | \
            jq -r '.result.name' 2>/dev/null) || {
            log_warn "Failed to create snapshot for $collection"
            continue
        }

        log_info "Snapshot created: $snapshot_name"

        # Wait for snapshot to be ready
        sleep 2

        # Download snapshot from container
        docker cp "engineer-team-qdrant:/qdrant/storage/snapshots/${collection}/${snapshot_name}" \
            "${backup_path}/${collection}-${DATE}.snapshot" || {
            log_warn "Failed to copy snapshot for $collection"
            continue
        }

        # Create checksum
        sha256sum "${backup_path}/${collection}-${DATE}.snapshot" > \
            "${backup_path}/${collection}-${DATE}.snapshot.sha256"

        log_success "Qdrant snapshot backed up: ${collection}-${DATE}.snapshot"
    done

    # Save collections metadata
    curl -sf http://localhost:6333/collections > \
        "${backup_path}/collections-${DATE}.json"

    return 0
}

backup_events() {
    if [ "$BACKUP_EVENTS" != "true" ]; then
        log_info "Local events backup disabled"
        return 0
    fi

    log_info "Starting local events backup..."

    local backup_path="${BACKUP_DIR}/events"
    mkdir -p "$backup_path"

    local events_dir="/home/pook/engineer-team/.kg-events"

    if [ ! -d "$events_dir" ]; then
        log_warn "Events directory not found: $events_dir"
        return 0
    fi

    # Count events to backup
    local event_count=$(find "$events_dir" -type f -name "*.json" | wc -l)
    log_info "Backing up $event_count event files..."

    # Create tar archive
    tar -czf "${backup_path}/kg-events-${DATE}.tar.gz" \
        -C "$(dirname "$events_dir")" \
        "$(basename "$events_dir")" 2>&1 | tee -a "$LOG_FILE" || {
        log_error "Events backup failed"
        return 1
    }

    # Create checksum
    sha256sum "${backup_path}/kg-events-${DATE}.tar.gz" > \
        "${backup_path}/kg-events-${DATE}.tar.gz.sha256"

    log_success "Events backup completed: kg-events-${DATE}.tar.gz ($event_count files)"
    return 0
}

cleanup_old_backups() {
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."

    local deleted=0

    # Clean Neo4j backups
    if [ -d "${BACKUP_DIR}/neo4j" ]; then
        find "${BACKUP_DIR}/neo4j" -type f -mtime +${RETENTION_DAYS} -delete
        deleted=$((deleted + $(find "${BACKUP_DIR}/neo4j" -type f -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)))
    fi

    # Clean Qdrant backups
    if [ -d "${BACKUP_DIR}/qdrant" ]; then
        find "${BACKUP_DIR}/qdrant" -type f -mtime +${RETENTION_DAYS} -delete
        deleted=$((deleted + $(find "${BACKUP_DIR}/qdrant" -type f -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)))
    fi

    # Clean events backups
    if [ -d "${BACKUP_DIR}/events" ]; then
        find "${BACKUP_DIR}/events" -type f -mtime +${RETENTION_DAYS} -delete
        deleted=$((deleted + $(find "${BACKUP_DIR}/events" -type f -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)))
    fi

    # Clean old logs
    find "${BACKUP_DIR}" -name "backup-*.log" -mtime +${RETENTION_DAYS} -delete

    log_success "Cleanup complete: $deleted files removed"
}

create_backup_manifest() {
    local manifest_file="${BACKUP_DIR}/backup-manifest-${DATE}.json"

    cat > "$manifest_file" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "date": "${DATE}",
  "hostname": "$(hostname)",
  "backup_type": "knowledge-graph",
  "components": {
    "neo4j": {
      "enabled": $BACKUP_NEO4J,
      "file": "neo4j/neo4j-${DATE}.dump.gz"
    },
    "qdrant": {
      "enabled": $BACKUP_QDRANT,
      "collections": ["mistakes", "engineer-team-knowledge"],
      "path": "qdrant/"
    },
    "events": {
      "enabled": $BACKUP_EVENTS,
      "file": "events/kg-events-${DATE}.tar.gz"
    }
  },
  "retention_days": ${RETENTION_DAYS},
  "rpo_hours": 24,
  "rto_hours": 2
}
EOF

    log_success "Backup manifest created: $manifest_file"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_info "========== KNOWLEDGE GRAPH BACKUP STARTED =========="
    log_info "Backup date: ${DATE}"

    # Create backup directories
    mkdir -p "${BACKUP_DIR}"/{neo4j,qdrant,events}

    # Execute backups
    local neo4j_status=0
    local qdrant_status=0
    local events_status=0

    backup_neo4j || neo4j_status=$?
    backup_qdrant || qdrant_status=$?
    backup_events || events_status=$?

    # Cleanup old backups
    cleanup_old_backups

    # Create manifest
    create_backup_manifest

    # Print summary
    log_info "========== BACKUP SUMMARY =========="
    log_info "Neo4j:   $([ $neo4j_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Qdrant:  $([ $qdrant_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Events:  $([ $events_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Log file: $LOG_FILE"

    # Calculate total backup size
    local total_size=$(du -sh "${BACKUP_DIR}" | cut -f1)
    log_info "Total backup size: $total_size"

    if [ $neo4j_status -eq 0 ] && [ $qdrant_status -eq 0 ] && [ $events_status -eq 0 ]; then
        log_success "========== BACKUP COMPLETED SUCCESSFULLY =========="
        return 0
    else
        log_error "========== BACKUP COMPLETED WITH ERRORS =========="
        return 1
    fi
}

# ============================================================================
# ERROR HANDLER
# ============================================================================

trap 'log_error "Backup script failed at line $LINENO"; exit 1' ERR

# Run main
main "$@"
