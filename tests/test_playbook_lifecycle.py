"""Tests for Playbook Lifecycle Manager."""

import pytest
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from lib.playbook_lifecycle import (
    PlaybookLifecycleManager,
    LifecycleState,
    LifecycleEvent
)


@pytest.fixture
def temp_playbook_dir(tmp_path):
    """Create temporary playbook directory."""
    return tmp_path / "playbooks"


@pytest.fixture
def manager(temp_playbook_dir):
    """Create lifecycle manager with temp directory."""
    temp_playbook_dir.mkdir()
    return PlaybookLifecycleManager(playbook_dir=temp_playbook_dir)


@pytest.fixture
def sample_playbook():
    """Create sample playbook."""
    return {
        'id': 'pb_test123',
        'name': 'Test Playbook',
        'metadata': {
            'confidence': 1.0,
            'usage_count': 5,
            'success_rate': 0.9,
            'last_used': datetime.utcnow().isoformat()
        },
        'steps': []
    }


class TestLifecycleState:
    """Tests for lifecycle state checking."""

    def test_active_recently_used(self, manager, sample_playbook):
        """Active playbook recently used."""
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.ACTIVE

    def test_active_no_last_used(self, manager, sample_playbook):
        """Active playbook without last_used timestamp."""
        del sample_playbook['metadata']['last_used']
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.ACTIVE

    def test_needs_revalidation_high_failure_rate(self, manager, sample_playbook):
        """Playbook needs revalidation due to high failure rate."""
        sample_playbook['metadata']['success_rate'] = 0.6  # 40% failure rate
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.NEEDS_REVALIDATION

    def test_needs_revalidation_90_days_unused(self, manager, sample_playbook):
        """Playbook needs revalidation after 90 days unused."""
        old_date = datetime.utcnow() - timedelta(days=95)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.NEEDS_REVALIDATION

    def test_archived_180_days_unused(self, manager, sample_playbook):
        """Playbook archived after 180 days unused."""
        old_date = datetime.utcnow() - timedelta(days=185)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.ARCHIVED

    def test_archived_low_confidence(self, manager, sample_playbook):
        """Playbook archived due to low confidence."""
        sample_playbook['metadata']['confidence'] = 0.2
        state = manager.check_playbook(sample_playbook)
        assert state == LifecycleState.ARCHIVED


class TestConfidenceDecay:
    """Tests for confidence decay mechanism."""

    def test_no_decay_recently_used(self, manager, sample_playbook):
        """No decay for recently used playbook."""
        event = manager.apply_confidence_decay(sample_playbook)
        assert event is None
        assert sample_playbook['metadata']['confidence'] == 1.0

    def test_no_decay_no_last_used(self, manager, sample_playbook):
        """No decay when last_used is missing."""
        del sample_playbook['metadata']['last_used']
        event = manager.apply_confidence_decay(sample_playbook)
        assert event is None

    def test_decay_after_30_days(self, manager, sample_playbook):
        """Confidence decays by 0.1 after 30 days."""
        old_date = datetime.utcnow() - timedelta(days=35)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        event = manager.apply_confidence_decay(sample_playbook)

        assert event is not None
        assert event.event_type == "confidence_decay"
        assert event.old_value == 1.0
        assert event.new_value == 0.9
        assert sample_playbook['metadata']['confidence'] == 0.9

    def test_decay_after_60_days(self, manager, sample_playbook):
        """Confidence decays by 0.2 after 60 days."""
        old_date = datetime.utcnow() - timedelta(days=65)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        event = manager.apply_confidence_decay(sample_playbook)

        assert event is not None
        assert event.new_value == 0.8
        assert sample_playbook['metadata']['confidence'] == 0.8

    def test_decay_floor_at_minimum(self, manager, sample_playbook):
        """Confidence decay stops at minimum threshold."""
        sample_playbook['metadata']['confidence'] = 0.35
        old_date = datetime.utcnow() - timedelta(days=65)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        event = manager.apply_confidence_decay(sample_playbook)

        assert event is not None
        assert sample_playbook['metadata']['confidence'] == 0.3  # MIN_CONFIDENCE

    def test_decay_event_details(self, manager, sample_playbook):
        """Decay event contains correct details."""
        old_date = datetime.utcnow() - timedelta(days=35)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        event = manager.apply_confidence_decay(sample_playbook)

        assert event.playbook_id == 'pb_test123'
        assert "days unused" in event.reason
        assert event.timestamp is not None


class TestArchival:
    """Tests for playbook archival."""

    def test_archive_creates_directory(self, manager, sample_playbook):
        """Archival creates archive directory if missing."""
        assert not manager.archive_dir.exists()
        manager.archive_playbook(sample_playbook, "test reason")
        assert manager.archive_dir.exists()

    def test_archive_moves_file(self, manager, sample_playbook, temp_playbook_dir):
        """Archival moves playbook to archive directory."""
        # Create original file
        active_path = temp_playbook_dir / "pb_test123.yaml"
        with open(active_path, 'w') as f:
            yaml.dump(sample_playbook, f)

        archive_path = manager.archive_playbook(sample_playbook, "test reason")

        assert archive_path.exists()
        assert not active_path.exists()
        assert archive_path == manager.archive_dir / "pb_test123.yaml"

    def test_archive_adds_metadata(self, manager, sample_playbook):
        """Archival adds archive metadata."""
        manager.archive_playbook(sample_playbook, "test reason")

        assert 'archived_at' in sample_playbook['metadata']
        assert 'archive_reason' in sample_playbook['metadata']
        assert sample_playbook['metadata']['archive_reason'] == "test reason"

    def test_archive_creates_event(self, manager, sample_playbook):
        """Archival creates lifecycle event."""
        manager.archive_playbook(sample_playbook, "test reason")

        assert len(manager.events) == 1
        event = manager.events[0]
        assert event.event_type == "archived"
        assert event.playbook_id == "pb_test123"
        assert event.reason == "test reason"


class TestRevalidation:
    """Tests for revalidation workflows."""

    def test_request_revalidation_marks_playbook(self, manager, sample_playbook):
        """Request revalidation marks playbook."""
        event = manager.request_revalidation(sample_playbook)

        assert sample_playbook['metadata']['needs_revalidation'] is True
        assert 'revalidation_requested_at' in sample_playbook['metadata']

    def test_request_revalidation_creates_event(self, manager, sample_playbook):
        """Request revalidation creates event."""
        event = manager.request_revalidation(sample_playbook)

        assert event.event_type == "revalidation_required"
        assert event.playbook_id == "pb_test123"
        assert len(event.reason) > 0

    def test_revalidation_reason_high_failure(self, manager, sample_playbook):
        """Revalidation reason for high failure rate."""
        sample_playbook['metadata']['success_rate'] = 0.6
        event = manager.request_revalidation(sample_playbook)
        assert "failure rate" in event.reason.lower()

    def test_revalidation_reason_unused(self, manager, sample_playbook):
        """Revalidation reason for unused playbook."""
        old_date = datetime.utcnow() - timedelta(days=95)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()
        event = manager.request_revalidation(sample_playbook)
        assert "unused" in event.reason.lower()

    def test_revalidate_updates_confidence(self, manager, sample_playbook):
        """Revalidation updates confidence."""
        sample_playbook['metadata']['needs_revalidation'] = True
        manager.revalidate(sample_playbook, 0.95)

        assert sample_playbook['metadata']['confidence'] == 0.95
        assert sample_playbook['metadata']['needs_revalidation'] is False
        assert 'last_revalidated' in sample_playbook['metadata']


class TestMaintenance:
    """Tests for maintenance run."""

    def test_maintenance_applies_decay(self, manager, sample_playbook, temp_playbook_dir):
        """Maintenance applies confidence decay."""
        old_date = datetime.utcnow() - timedelta(days=35)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()

        playbook_file = temp_playbook_dir / "pb_test123.yaml"
        with open(playbook_file, 'w') as f:
            yaml.dump(sample_playbook, f)

        events = manager.run_maintenance()

        assert len(events) == 1
        assert events[0].event_type == "confidence_decay"

        # Reload and check
        with open(playbook_file) as f:
            updated = yaml.safe_load(f)
        assert updated['metadata']['confidence'] == 0.9

    def test_maintenance_requests_revalidation(self, manager, sample_playbook, temp_playbook_dir):
        """Maintenance requests revalidation when needed."""
        old_date = datetime.utcnow() - timedelta(days=95)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()

        playbook_file = temp_playbook_dir / "pb_test123.yaml"
        with open(playbook_file, 'w') as f:
            yaml.dump(sample_playbook, f)

        events = manager.run_maintenance()

        # Should have decay event and revalidation event
        event_types = [e.event_type for e in events]
        assert "revalidation_required" in event_types

    def test_maintenance_archives_old_playbook(self, manager, sample_playbook, temp_playbook_dir):
        """Maintenance archives very old playbook."""
        old_date = datetime.utcnow() - timedelta(days=185)
        sample_playbook['metadata']['last_used'] = old_date.isoformat()

        playbook_file = temp_playbook_dir / "pb_test123.yaml"
        with open(playbook_file, 'w') as f:
            yaml.dump(sample_playbook, f)

        events = manager.run_maintenance()

        # Playbook should be archived
        assert not playbook_file.exists()
        archive_path = manager.archive_dir / "pb_test123.yaml"
        assert archive_path.exists()

    def test_maintenance_handles_errors_gracefully(self, manager, temp_playbook_dir):
        """Maintenance continues on errors."""
        # Create invalid YAML file
        bad_file = temp_playbook_dir / "bad.yaml"
        with open(bad_file, 'w') as f:
            f.write("invalid: yaml: content: [[[")

        # Should not raise exception
        events = manager.run_maintenance()
        assert isinstance(events, list)

    def test_maintenance_skips_archive_directory(self, manager, sample_playbook):
        """Maintenance skips files in archive directory."""
        manager.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_file = manager.archive_dir / "archived.yaml"
        with open(archive_file, 'w') as f:
            yaml.dump(sample_playbook, f)

        events = manager.run_maintenance()
        # Should process no events since archive dir is skipped
        assert len(events) == 0


class TestSuccessRateCalculation:
    """Tests for success rate calculation."""

    def test_success_rate_with_usage(self, manager, sample_playbook):
        """Calculate success rate with usage history."""
        rate = manager._calculate_success_rate(sample_playbook['metadata'])
        assert rate == 0.9

    def test_success_rate_no_usage(self, manager):
        """Default success rate when no usage."""
        metadata = {'usage_count': 0}
        rate = manager._calculate_success_rate(metadata)
        assert rate == 1.0

    def test_success_rate_missing_data(self, manager):
        """Default success rate with missing data."""
        rate = manager._calculate_success_rate({})
        assert rate == 1.0
