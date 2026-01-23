"""
Test suite for Blazing Buffalo Prometheus alerting rules.

Task: BB-025
Purpose: Validate alert configurations and thresholds
"""

import yaml
import pytest
from pathlib import Path


ALERTS_FILE = Path(__file__).parent.parent / "monitoring" / "alerts.yaml"
REQUIRED_ALERT_FIELDS = ["alert", "expr", "labels", "annotations"]
REQUIRED_ANNOTATION_FIELDS = ["summary", "description", "runbook_url"]
REQUIRED_LABEL_FIELDS = ["severity", "team", "component"]


@pytest.fixture
def alert_rules():
    """Load alert rules from YAML file."""
    with open(ALERTS_FILE, "r") as f:
        config = yaml.safe_load(f)
    return config["groups"][0]["rules"]


def test_alerts_file_exists():
    """Verify alerts.yaml file exists."""
    assert ALERTS_FILE.exists(), f"Alerts file not found: {ALERTS_FILE}"


def test_alerts_yaml_valid(alert_rules):
    """Verify alerts.yaml is valid YAML and has expected structure."""
    assert isinstance(alert_rules, list), "Alert rules should be a list"
    assert len(alert_rules) > 0, "Alert rules should not be empty"


def test_minimum_alert_count(alert_rules):
    """Verify we have at least 10 alert rules as required."""
    assert len(alert_rules) >= 10, f"Expected >= 10 alerts, found {len(alert_rules)}"


def test_alert_structure(alert_rules):
    """Verify each alert has required fields."""
    for rule in alert_rules:
        for field in REQUIRED_ALERT_FIELDS:
            assert field in rule, f"Alert '{rule.get('alert', 'UNNAMED')}' missing field: {field}"


def test_alert_labels(alert_rules):
    """Verify each alert has required labels."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        labels = rule.get("labels", {})

        for field in REQUIRED_LABEL_FIELDS:
            assert field in labels, f"Alert '{alert_name}' missing label: {field}"


def test_alert_annotations(alert_rules):
    """Verify each alert has required annotations."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        annotations = rule.get("annotations", {})

        for field in REQUIRED_ANNOTATION_FIELDS:
            assert field in annotations, f"Alert '{alert_name}' missing annotation: {field}"


def test_severity_levels(alert_rules):
    """Verify severity levels are valid."""
    valid_severities = {"info", "warning", "critical"}

    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        severity = rule.get("labels", {}).get("severity")

        assert severity in valid_severities, (
            f"Alert '{alert_name}' has invalid severity: {severity}. "
            f"Valid values: {valid_severities}"
        )


def test_runbook_urls_format(alert_rules):
    """Verify runbook URLs follow expected format."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        runbook_url = rule.get("annotations", {}).get("runbook_url", "")

        assert runbook_url.startswith("https://docs.internal/runbooks/"), (
            f"Alert '{alert_name}' has invalid runbook URL format: {runbook_url}"
        )


def test_circuit_breaker_alerts_present(alert_rules):
    """Verify circuit breaker alerts are defined."""
    circuit_breaker_alerts = [
        "PlaybookCircuitBreakerOpen",
        "MultipleCircuitBreakersOpen",
        "CircuitBreakerFlapping",
    ]

    alert_names = [rule.get("alert") for rule in alert_rules]

    for alert in circuit_breaker_alerts:
        assert alert in alert_names, f"Missing circuit breaker alert: {alert}"


def test_false_positive_alerts_present(alert_rules):
    """Verify false positive detection alerts are defined."""
    false_positive_alerts = [
        "HighFalsePositiveRate",
        "LowPlaybookSuccessRate",
    ]

    alert_names = [rule.get("alert") for rule in alert_rules]

    for alert in false_positive_alerts:
        assert alert in alert_names, f"Missing false positive alert: {alert}"


def test_rca_latency_alerts_present(alert_rules):
    """Verify RCA latency alerts are defined."""
    rca_alerts = [
        "RCALatencyHigh",
        "RCALatencyCritical",
    ]

    alert_names = [rule.get("alert") for rule in alert_rules]

    for alert in rca_alerts:
        assert alert in alert_names, f"Missing RCA latency alert: {alert}"


def test_backup_alerts_present(alert_rules):
    """Verify backup alerts are defined."""
    backup_alerts = [
        "BackupFailed",
        "BackupAgeWarning",
    ]

    alert_names = [rule.get("alert") for rule in alert_rules]

    for alert in backup_alerts:
        assert alert in alert_names, f"Missing backup alert: {alert}"


def test_for_duration_defined(alert_rules):
    """Verify alerts have 'for' duration to prevent flapping."""
    # Exclude info-level alerts from this requirement
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        severity = rule.get("labels", {}).get("severity")

        if severity in ["warning", "critical"]:
            assert "for" in rule, f"Alert '{alert_name}' missing 'for' duration"


def test_critical_alerts_have_short_duration(alert_rules):
    """Verify critical alerts have short evaluation duration."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        severity = rule.get("labels", {}).get("severity")

        if severity == "critical" and "for" in rule:
            duration = rule["for"]
            # Parse duration (e.g., "5m", "1h")
            if duration.endswith("m"):
                minutes = int(duration[:-1])
                assert minutes <= 10, (
                    f"Critical alert '{alert_name}' has too long duration: {duration}"
                )


def test_metric_names_consistency(alert_rules):
    """Verify all metrics follow blazing_buffalo_ naming convention."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        expr = rule.get("expr", "")

        # Check for metric references in expression
        if "blazing_buffalo_" not in expr and "time()" not in expr and "count(" not in expr:
            # Some expressions may use functions without direct metric references
            continue

        # Basic check: if metric is referenced, it should use our namespace
        if "_total" in expr or "_seconds" in expr or "_bytes" in expr or "_state" in expr:
            assert "blazing_buffalo_" in expr or "kg_" in expr, (
                f"Alert '{alert_name}' uses metric without blazing_buffalo_ prefix"
            )


def test_team_assignments(alert_rules):
    """Verify team assignments are valid."""
    valid_teams = {"engineering", "platform", "ml-team"}

    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        team = rule.get("labels", {}).get("team")

        assert team in valid_teams, (
            f"Alert '{alert_name}' has invalid team: {team}. "
            f"Valid teams: {valid_teams}"
        )


def test_component_labels(alert_rules):
    """Verify component labels are defined."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        component = rule.get("labels", {}).get("component")

        assert component is not None, f"Alert '{alert_name}' missing component label"
        assert len(component) > 0, f"Alert '{alert_name}' has empty component label"


def test_category_labels(alert_rules):
    """Verify category labels are defined for organization."""
    valid_categories = {
        "reliability",
        "accuracy",
        "effectiveness",
        "performance",
        "capacity",
        "data-protection",
        "system-health",
        "resources",
        "data-quality",
        "consistency",
        "maintenance",
    }

    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        category = rule.get("labels", {}).get("category")

        if category:  # Category is optional but recommended
            assert category in valid_categories, (
                f"Alert '{alert_name}' has invalid category: {category}. "
                f"Valid categories: {valid_categories}"
            )


def test_descriptions_not_empty(alert_rules):
    """Verify alert descriptions are not empty."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        description = rule.get("annotations", {}).get("description", "")

        assert len(description.strip()) > 0, (
            f"Alert '{alert_name}' has empty description"
        )


def test_summaries_not_empty(alert_rules):
    """Verify alert summaries are not empty."""
    for rule in alert_rules:
        alert_name = rule.get("alert", "UNNAMED")
        summary = rule.get("annotations", {}).get("summary", "")

        assert len(summary.strip()) > 0, (
            f"Alert '{alert_name}' has empty summary"
        )


def test_alert_names_unique(alert_rules):
    """Verify alert names are unique."""
    alert_names = [rule.get("alert") for rule in alert_rules]
    duplicates = [name for name in alert_names if alert_names.count(name) > 1]

    assert len(duplicates) == 0, f"Duplicate alert names found: {set(duplicates)}"


def test_playbook_lifecycle_alerts_present(alert_rules):
    """Verify playbook lifecycle alerts are defined."""
    lifecycle_alerts = [
        "PlaybookVersionMismatch",
        "PlaybookDeprecationOverdue",
    ]

    alert_names = [rule.get("alert") for rule in alert_rules]

    for alert in lifecycle_alerts:
        assert alert in alert_names, f"Missing playbook lifecycle alert: {alert}"


def test_alert_count_by_severity():
    """Report distribution of alerts by severity for documentation."""
    with open(ALERTS_FILE, "r") as f:
        config = yaml.safe_load(f)

    rules = config["groups"][0]["rules"]

    severity_counts = {"info": 0, "warning": 0, "critical": 0}

    for rule in rules:
        severity = rule.get("labels", {}).get("severity")
        if severity in severity_counts:
            severity_counts[severity] += 1

    print(f"\nAlert Distribution by Severity:")
    print(f"  Critical: {severity_counts['critical']}")
    print(f"  Warning:  {severity_counts['warning']}")
    print(f"  Info:     {severity_counts['info']}")
    print(f"  Total:    {sum(severity_counts.values())}")

    # This is informational, not a failure
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
