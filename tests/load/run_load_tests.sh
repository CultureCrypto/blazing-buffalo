#!/bin/bash
# Load Test Runner for Blazing Buffalo System
#
# Usage:
#   ./run_load_tests.sh              # Run all tests
#   ./run_load_tests.sh --quick      # Run quick validation
#   ./run_load_tests.sh --ci         # CI/CD mode with validation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found"
        exit 1
    fi

    # Check required Python packages
    python3 -c "import asyncio" 2>/dev/null || {
        log_error "asyncio module not found"
        exit 1
    }

    log_info "Dependencies OK"
}

# Run load tests
run_tests() {
    local mode="${1:-full}"

    log_info "Running load tests (mode: $mode)..."

    cd "$PROJECT_ROOT"

    if [ "$mode" = "quick" ]; then
        log_info "Quick validation mode - running minimal tests"
        # Could add environment variable to reduce test counts
        export QUICK_MODE=1
    fi

    python3 tests/load/test_load.py

    if [ $? -eq 0 ]; then
        log_info "Load tests completed successfully"
        return 0
    else
        log_error "Load tests failed"
        return 1
    fi
}

# Validate results against targets
validate_results() {
    log_info "Validating performance against targets..."

    # Find most recent baseline file
    latest_baseline=$(ls -t "$RESULTS_DIR"/baseline-*.json 2>/dev/null | head -1)

    if [ -z "$latest_baseline" ]; then
        log_error "No baseline file found"
        return 1
    fi

    log_info "Checking baseline: $latest_baseline"

    # Extract metrics using python
    python3 -c "
import json
import sys

with open('$latest_baseline') as f:
    data = json.load(f)

failures = []

# Check targets
if data['api_throughput_rps'] < 500:
    failures.append(f\"API throughput too low: {data['api_throughput_rps']:.1f} < 500 req/s\")

if data['api_p99_latency_ms'] > 200:
    failures.append(f\"API P99 latency too high: {data['api_p99_latency_ms']:.2f} > 200ms\")

if data['mistake_detection_per_min'] < 100:
    failures.append(f\"Mistake detection too slow: {data['mistake_detection_per_min']} < 100/min\")

if data['rca_p95_latency_s'] > 30:
    failures.append(f\"RCA latency too high: {data['rca_p95_latency_s']:.2f} > 30s\")

if data['concurrent_playbooks'] < 50:
    failures.append(f\"Concurrent playbooks too low: {data['concurrent_playbooks']} < 50\")

if data['error_rate_pct'] > 1:
    failures.append(f\"Error rate too high: {data['error_rate_pct']:.2f}% > 1%\")

if failures:
    print('${RED}VALIDATION FAILED:${NC}')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
else:
    print('${GREEN}✓ All performance targets met${NC}')
    sys.exit(0)
"

    return $?
}

# Generate report
generate_report() {
    log_info "Performance report available at:"
    echo "  $PROJECT_ROOT/docs/performance-baseline.md"

    if [ -f "$PROJECT_ROOT/docs/performance-baseline.md" ]; then
        echo ""
        echo "Summary:"
        grep -A 10 "^## Summary" "$PROJECT_ROOT/docs/performance-baseline.md" | head -15
    fi
}

# Main execution
main() {
    local mode="full"
    local validate_only=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                mode="quick"
                shift
                ;;
            --ci)
                mode="ci"
                shift
                ;;
            --validate)
                validate_only=true
                shift
                ;;
            --help)
                cat <<EOF
Load Test Runner for Blazing Buffalo System

Usage:
  $0 [OPTIONS]

Options:
  --quick       Run quick validation tests
  --ci          CI/CD mode (fail on target violations)
  --validate    Only validate existing results
  --help        Show this help message

Examples:
  $0                    # Run full load tests
  $0 --quick            # Quick validation
  $0 --ci               # CI/CD mode
  $0 --validate         # Validate existing results
EOF
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    echo "=================================="
    echo "Blazing Buffalo Load Test Runner"
    echo "=================================="
    echo ""

    check_dependencies

    if [ "$validate_only" = false ]; then
        run_tests "$mode" || exit 1
    fi

    if [ "$mode" = "ci" ]; then
        validate_results || exit 1
    fi

    generate_report

    log_info "Done!"
}

main "$@"
