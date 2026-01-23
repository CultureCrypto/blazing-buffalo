#!/bin/bash
#
# Blazing Buffalo - Knowledge Graph Restore Script
# Restore Neo4j, Qdrant, and local events from backup
# Target RTO: 2h
#

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

BACKUP_DIR="${BACKUP_DIR:-/home/pook/engineer-team/backups}"
RESTORE_DATE="${1:-$(date +%Y%m%d)}"
LOG_FILE="${BACKUP_DIR}/restore-${RESTORE_DATE}-$(date +%H%M%S).log"
DRY_RUN="${DRY_RUN:-false}"

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
# VALIDATION FUNCTIONS
# ============================================================================

validate_backup_files() {
    log_info "Validating backup files for date: ${RESTORE_DATE}"

    local valid=true

    # Check Neo4j backup
    if [ -f "${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump.gz" ]; then
        log_info "Found Neo4j backup: neo4j-${RESTORE_DATE}.dump.gz"

        # Verify checksum if available
        if [ -f "${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump.sha256" ]; then
            log_info "Verifying Neo4j checksum..."
            # Decompress for checksum verification
            gunzip -k "${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump.gz" 2>/dev/null || true
            if [ -f "${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump" ]; then
                cd "${BACKUP_DIR}/neo4j" && sha256sum -c "neo4j-${RESTORE_DATE}.dump.sha256" || {
                    log_warn "Neo4j checksum verification failed"
                    valid=false
                }
            fi
        fi
    else
        log_warn "Neo4j backup not found for ${RESTORE_DATE}"
    fi

    # Check Qdrant backups
    local qdrant_found=false
    for collection in mistakes engineer-team-knowledge; do
        if [ -f "${BACKUP_DIR}/qdrant/${collection}-${RESTORE_DATE}.snapshot" ]; then
            log_info "Found Qdrant backup: ${collection}-${RESTORE_DATE}.snapshot"
            qdrant_found=true

            # Verify checksum if available
            if [ -f "${BACKUP_DIR}/qdrant/${collection}-${RESTORE_DATE}.snapshot.sha256" ]; then
                cd "${BACKUP_DIR}/qdrant" && sha256sum -c "${collection}-${RESTORE_DATE}.snapshot.sha256" || {
                    log_warn "Qdrant checksum verification failed for $collection"
                    valid=false
                }
            fi
        fi
    done

    if [ "$qdrant_found" = false ]; then
        log_warn "No Qdrant backups found for ${RESTORE_DATE}"
    fi

    # Check events backup
    if [ -f "${BACKUP_DIR}/events/kg-events-${RESTORE_DATE}.tar.gz" ]; then
        log_info "Found events backup: kg-events-${RESTORE_DATE}.tar.gz"

        # Verify checksum if available
        if [ -f "${BACKUP_DIR}/events/kg-events-${RESTORE_DATE}.tar.gz.sha256" ]; then
            cd "${BACKUP_DIR}/events" && sha256sum -c "kg-events-${RESTORE_DATE}.tar.gz.sha256" || {
                log_warn "Events checksum verification failed"
                valid=false
            }
        fi
    else
        log_warn "Events backup not found for ${RESTORE_DATE}"
    fi

    if [ "$valid" = true ]; then
        log_success "Backup validation passed"
        return 0
    else
        log_error "Backup validation failed"
        return 1
    fi
}

# ============================================================================
# RESTORE FUNCTIONS
# ============================================================================

restore_neo4j() {
    log_info "Starting Neo4j restore..."

    local dump_file="${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump.gz"

    if [ ! -f "$dump_file" ]; then
        log_warn "Neo4j backup not found, skipping"
        return 0
    fi

    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY RUN] Would restore Neo4j from: $dump_file"
        return 0
    fi

    # Decompress if needed
    if [ ! -f "${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump" ]; then
        log_info "Decompressing Neo4j backup..."
        gunzip -k "$dump_file"
    fi

    local dump_path="${BACKUP_DIR}/neo4j/neo4j-${RESTORE_DATE}.dump"

    # Stop Neo4j
    log_info "Stopping Neo4j container..."
    docker stop engineer-team-neo4j || true
    sleep 5

    # Load database dump
    log_info "Loading Neo4j database dump..."

    docker run --rm \
        -v engineer-team_neo4j-data:/data \
        -v "$(dirname "$dump_path"):/backups:ro" \
        --user 7474:7474 \
        neo4j:5.26-community \
        neo4j-admin database load neo4j \
        --from-path=/backups/$(basename "$dump_path") \
        --overwrite-destination=true 2>&1 | tee -a "$LOG_FILE" || {
        log_error "Neo4j restore failed"
        docker start engineer-team-neo4j
        return 1
    }

    # Start Neo4j
    log_info "Starting Neo4j container..."
    docker start engineer-team-neo4j
    sleep 10

    # Wait for Neo4j to be ready
    log_info "Waiting for Neo4j to become ready..."
    local attempt=0
    while [ $attempt -lt 60 ]; do
        if docker exec engineer-team-neo4j cypher-shell \
            "MATCH (n) RETURN count(n) as count" > /dev/null 2>&1; then
            local node_count=$(docker exec engineer-team-neo4j cypher-shell \
                "MATCH (n) RETURN count(n) as count" 2>/dev/null | tail -n 1 || echo "0")
            log_success "Neo4j restored successfully - Node count: $node_count"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_error "Neo4j failed to become ready after restore"
    return 1
}

restore_qdrant() {
    log_info "Starting Qdrant restore..."

    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY RUN] Would restore Qdrant snapshots"
        return 0
    fi

    # Check if Qdrant is accessible
    if ! curl -sf http://localhost:6333/health > /dev/null 2>&1; then
        log_info "Starting Qdrant container..."
        docker start engineer-team-qdrant || true
        sleep 10
    fi

    # Restore each collection
    local collections=("mistakes" "engineer-team-knowledge")

    for collection in "${collections[@]}"; do
        local snapshot_file="${BACKUP_DIR}/qdrant/${collection}-${RESTORE_DATE}.snapshot"

        if [ ! -f "$snapshot_file" ]; then
            log_warn "Snapshot not found for $collection, skipping"
            continue
        fi

        log_info "Restoring collection: $collection"

        # Copy snapshot to container
        docker cp "$snapshot_file" \
            "engineer-team-qdrant:/qdrant/storage/snapshots/${collection}/$(basename "$snapshot_file")" || {
            log_error "Failed to copy snapshot for $collection"
            continue
        }

        # Trigger snapshot recovery
        local snapshot_name=$(basename "$snapshot_file")
        curl -sf -X PUT \
            "http://localhost:6333/collections/${collection}/snapshots/recover" \
            -H "Content-Type: application/json" \
            -d "{\"location\": \"${snapshot_name}\"}" || {
            log_warn "Failed to restore snapshot for $collection"
            continue
        }

        log_success "Qdrant collection restored: $collection"

        # Verify collection
        local point_count=$(curl -sf "http://localhost:6333/collections/${collection}" | \
            jq -r '.result.points_count' 2>/dev/null || echo "0")
        log_info "Collection $collection point count: $point_count"
    done

    return 0
}

restore_events() {
    log_info "Starting local events restore..."

    local events_file="${BACKUP_DIR}/events/kg-events-${RESTORE_DATE}.tar.gz"

    if [ ! -f "$events_file" ]; then
        log_warn "Events backup not found, skipping"
        return 0
    fi

    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY RUN] Would restore events from: $events_file"
        return 0
    fi

    local events_dir="/home/pook/engineer-team/.kg-events"

    # Backup current events if they exist
    if [ -d "$events_dir" ]; then
        log_info "Backing up current events..."
        mv "$events_dir" "${events_dir}.pre-restore-$(date +%Y%m%d-%H%M%S)"
    fi

    # Extract events
    log_info "Extracting events archive..."
    tar -xzf "$events_file" -C "$(dirname "$events_dir")" || {
        log_error "Failed to extract events"
        return 1
    }

    local event_count=$(find "$events_dir" -type f -name "*.json" | wc -l)
    log_success "Events restored: $event_count files"

    return 0
}

verify_restore() {
    log_info "Verifying restore..."

    local errors=0

    # Verify Neo4j
    if docker exec engineer-team-neo4j cypher-shell \
        "MATCH (n) RETURN count(n) as count" > /dev/null 2>&1; then
        local node_count=$(docker exec engineer-team-neo4j cypher-shell \
            "MATCH (n) RETURN count(n) as count" 2>/dev/null | tail -n 1 || echo "0")
        log_success "Neo4j verification passed - Nodes: $node_count"
    else
        log_error "Neo4j verification failed"
        errors=$((errors + 1))
    fi

    # Verify Qdrant
    if curl -sf http://localhost:6333/health > /dev/null 2>&1; then
        log_success "Qdrant verification passed"

        # Check collections
        for collection in mistakes engineer-team-knowledge; do
            local count=$(curl -sf "http://localhost:6333/collections/${collection}" | \
                jq -r '.result.points_count' 2>/dev/null || echo "0")
            log_info "Qdrant collection $collection: $count points"
        done
    else
        log_error "Qdrant verification failed"
        errors=$((errors + 1))
    fi

    # Verify events
    local events_dir="/home/pook/engineer-team/.kg-events"
    if [ -d "$events_dir" ]; then
        local event_count=$(find "$events_dir" -type f -name "*.json" | wc -l)
        log_success "Events verification passed - Files: $event_count"
    else
        log_warn "Events directory not found"
    fi

    if [ $errors -eq 0 ]; then
        log_success "All verifications passed"
        return 0
    else
        log_error "Verification failed with $errors errors"
        return 1
    fi
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_info "========== KNOWLEDGE GRAPH RESTORE STARTED =========="
    log_info "Restore date: ${RESTORE_DATE}"
    log_info "Dry run: ${DRY_RUN}"

    # Validate backup files
    validate_backup_files || {
        log_error "Backup validation failed, aborting restore"
        exit 1
    }

    if [ "$DRY_RUN" != "true" ]; then
        log_warn "This will restore knowledge graph from backup dated ${RESTORE_DATE}"
        log_warn "Current data will be overwritten. Press Ctrl+C to cancel."
        sleep 5
    fi

    # Execute restore
    local neo4j_status=0
    local qdrant_status=0
    local events_status=0

    restore_neo4j || neo4j_status=$?
    restore_qdrant || qdrant_status=$?
    restore_events || events_status=$?

    # Verify restore
    local verify_status=0
    verify_restore || verify_status=$?

    # Print summary
    log_info "========== RESTORE SUMMARY =========="
    log_info "Neo4j:   $([ $neo4j_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Qdrant:  $([ $qdrant_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Events:  $([ $events_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Verify:  $([ $verify_status -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
    log_info "Log file: $LOG_FILE"

    if [ $neo4j_status -eq 0 ] && [ $qdrant_status -eq 0 ] && [ $events_status -eq 0 ] && [ $verify_status -eq 0 ]; then
        log_success "========== RESTORE COMPLETED SUCCESSFULLY =========="
        return 0
    else
        log_error "========== RESTORE COMPLETED WITH ERRORS =========="
        return 1
    fi
}

# ============================================================================
# ERROR HANDLER
# ============================================================================

trap 'log_error "Restore script failed at line $LINENO"' ERR

# ============================================================================
# USAGE
# ============================================================================

show_usage() {
    cat << EOF
Usage: restore-kg.sh [OPTIONS] [DATE]

Arguments:
  DATE            Backup date to restore (format: YYYYMMDD, default: today)

Options:
  --dry-run       Show what would be done without making changes
  --help          Show this help message

Environment Variables:
  BACKUP_DIR      Backup directory (default: /home/pook/engineer-team/backups)
  DRY_RUN         Set to 'true' for dry run (default: false)

Examples:
  ./restore-kg.sh 20260121              # Restore from Jan 21, 2026 backup
  ./restore-kg.sh --dry-run 20260121    # Preview restore
  DRY_RUN=true ./restore-kg.sh          # Dry run with today's date

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            RESTORE_DATE="$1"
            shift
            ;;
    esac
done

# Run main
main "$@"
