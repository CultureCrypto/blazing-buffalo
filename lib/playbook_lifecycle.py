"""Playbook Lifecycle Manager.

Manages playbook aging, revalidation, and archival to prevent stale playbooks
from causing issues.

Lifecycle Rules:
- 30 days unused: Reduce confidence by 0.1
- 90 days unused: Require revalidation
- 180 days unused: Archive if still unused
- Failure rate > 30%: Trigger revalidation
- Confidence < 0.3: Archive automatically

Key Features:
- Automated confidence decay based on usage
- Failure rate monitoring
- Archive management
- Revalidation workflows
- Event tracking for auditing
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import yaml


class LifecycleState(Enum):
    """Lifecycle states for playbooks."""
    ACTIVE = "active"
    NEEDS_REVALIDATION = "needs_revalidation"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


@dataclass
class LifecycleEvent:
    """Event tracking lifecycle changes."""
    playbook_id: str
    event_type: str  # confidence_decay, revalidation_required, archived
    timestamp: datetime
    old_value: Optional[float]
    new_value: Optional[float]
    reason: str


class PlaybookLifecycleManager:
    """Manage playbook aging, revalidation, and archival."""

    # Lifecycle thresholds
    CONFIDENCE_DECAY_DAYS = 30
    CONFIDENCE_DECAY_AMOUNT = 0.1
    REVALIDATION_DAYS = 90
    ARCHIVE_DAYS = 180
    MIN_CONFIDENCE = 0.3
    MAX_FAILURE_RATE = 0.3

    def __init__(self, playbook_dir: Path = None):
        """Initialize lifecycle manager.

        Args:
            playbook_dir: Directory containing playbooks (default: /home/pook/engineer-team/playbooks)
        """
        self.playbook_dir = playbook_dir or Path("/home/pook/engineer-team/playbooks")
        self.archive_dir = self.playbook_dir / "archived"
        self.events: List[LifecycleEvent] = []

    def check_playbook(self, playbook: Dict) -> LifecycleState:
        """Check lifecycle state of a playbook.

        Args:
            playbook: Playbook dictionary with metadata

        Returns:
            Current lifecycle state
        """
        metadata = playbook.get('metadata', {})
        last_used = metadata.get('last_used')
        confidence = metadata.get('confidence', 1.0)
        success_rate = self._calculate_success_rate(metadata)

        # Check failure rate
        if success_rate < (1 - self.MAX_FAILURE_RATE):
            return LifecycleState.NEEDS_REVALIDATION

        # Check confidence
        if confidence < self.MIN_CONFIDENCE:
            return LifecycleState.ARCHIVED

        if not last_used:
            return LifecycleState.ACTIVE

        # Parse last_used timestamp
        if isinstance(last_used, str):
            last_used = datetime.fromisoformat(last_used.replace('Z', '+00:00'))

        days_unused = (datetime.utcnow() - last_used).days

        if days_unused >= self.ARCHIVE_DAYS:
            return LifecycleState.ARCHIVED
        elif days_unused >= self.REVALIDATION_DAYS:
            return LifecycleState.NEEDS_REVALIDATION

        return LifecycleState.ACTIVE

    def apply_confidence_decay(self, playbook: Dict) -> Optional[LifecycleEvent]:
        """Apply confidence decay for unused playbooks.

        Reduces confidence by CONFIDENCE_DECAY_AMOUNT every CONFIDENCE_DECAY_DAYS.

        Args:
            playbook: Playbook dictionary with metadata

        Returns:
            LifecycleEvent if decay was applied, None otherwise
        """
        metadata = playbook.get('metadata', {})
        last_used = metadata.get('last_used')
        current_confidence = metadata.get('confidence', 1.0)

        if not last_used:
            return None

        if isinstance(last_used, str):
            last_used = datetime.fromisoformat(last_used.replace('Z', '+00:00'))

        days_unused = (datetime.utcnow() - last_used).days
        decay_periods = days_unused // self.CONFIDENCE_DECAY_DAYS

        if decay_periods > 0:
            new_confidence = max(
                self.MIN_CONFIDENCE,
                current_confidence - (decay_periods * self.CONFIDENCE_DECAY_AMOUNT)
            )

            if new_confidence != current_confidence:
                event = LifecycleEvent(
                    playbook_id=playbook.get('id'),
                    event_type="confidence_decay",
                    timestamp=datetime.utcnow(),
                    old_value=current_confidence,
                    new_value=new_confidence,
                    reason=f"{days_unused} days unused"
                )
                self.events.append(event)
                playbook['metadata']['confidence'] = new_confidence
                return event

        return None

    def archive_playbook(self, playbook: Dict, reason: str) -> Path:
        """Move playbook to archive directory.

        Args:
            playbook: Playbook dictionary
            reason: Reason for archival

        Returns:
            Path to archived playbook file
        """
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        playbook_id = playbook.get('id')
        playbook['metadata']['archived_at'] = datetime.utcnow().isoformat()
        playbook['metadata']['archive_reason'] = reason

        archive_path = self.archive_dir / f"{playbook_id}.yaml"
        with open(archive_path, 'w') as f:
            yaml.dump(playbook, f, default_flow_style=False, sort_keys=False)

        # Remove from active directory
        active_path = self.playbook_dir / f"{playbook_id}.yaml"
        if active_path.exists():
            active_path.unlink()

        event = LifecycleEvent(
            playbook_id=playbook_id,
            event_type="archived",
            timestamp=datetime.utcnow(),
            old_value=None,
            new_value=None,
            reason=reason
        )
        self.events.append(event)

        return archive_path

    def request_revalidation(self, playbook: Dict) -> LifecycleEvent:
        """Mark playbook as needing revalidation.

        Args:
            playbook: Playbook dictionary

        Returns:
            LifecycleEvent for the revalidation request
        """
        playbook_id = playbook.get('id')
        playbook['metadata']['needs_revalidation'] = True
        playbook['metadata']['revalidation_requested_at'] = datetime.utcnow().isoformat()

        event = LifecycleEvent(
            playbook_id=playbook_id,
            event_type="revalidation_required",
            timestamp=datetime.utcnow(),
            old_value=None,
            new_value=None,
            reason=self._get_revalidation_reason(playbook)
        )
        self.events.append(event)

        return event

    def revalidate(self, playbook: Dict, new_confidence: float) -> None:
        """Revalidate a playbook with new confidence score.

        Args:
            playbook: Playbook dictionary
            new_confidence: Updated confidence score (0.0-1.0)
        """
        playbook['metadata']['confidence'] = new_confidence
        playbook['metadata']['needs_revalidation'] = False
        playbook['metadata']['last_revalidated'] = datetime.utcnow().isoformat()

    def run_maintenance(self) -> List[LifecycleEvent]:
        """Run maintenance on all playbooks.

        Applies decay, checks states, archives/revalidates as needed.

        Returns:
            List of lifecycle events generated during maintenance
        """
        events = []

        for playbook_file in self.playbook_dir.glob("*.yaml"):
            if playbook_file.parent == self.archive_dir:
                continue

            try:
                with open(playbook_file) as f:
                    playbook = yaml.safe_load(f)

                if not playbook or 'id' not in playbook:
                    continue

                # Apply decay
                decay_event = self.apply_confidence_decay(playbook)
                if decay_event:
                    events.append(decay_event)

                # Check state
                state = self.check_playbook(playbook)

                if state == LifecycleState.ARCHIVED:
                    self.archive_playbook(playbook, "auto_archived_low_confidence_or_unused")
                elif state == LifecycleState.NEEDS_REVALIDATION:
                    event = self.request_revalidation(playbook)
                    events.append(event)

                # Save updated playbook (if not archived)
                if state != LifecycleState.ARCHIVED:
                    with open(playbook_file, 'w') as f:
                        yaml.dump(playbook, f, default_flow_style=False, sort_keys=False)

            except Exception as e:
                # Log error but continue with other playbooks
                print(f"Error processing {playbook_file}: {e}")
                continue

        return events

    def _calculate_success_rate(self, metadata: Dict) -> float:
        """Calculate playbook success rate.

        Args:
            metadata: Playbook metadata dictionary

        Returns:
            Success rate (0.0-1.0)
        """
        usage_count = metadata.get('usage_count', 0)
        success_rate = metadata.get('success_rate', 1.0)

        if usage_count == 0:
            return 1.0
        return success_rate

    def _get_revalidation_reason(self, playbook: Dict) -> str:
        """Determine reason for revalidation.

        Args:
            playbook: Playbook dictionary

        Returns:
            Human-readable reason string
        """
        metadata = playbook.get('metadata', {})
        success_rate = self._calculate_success_rate(metadata)

        if success_rate < (1 - self.MAX_FAILURE_RATE):
            return f"High failure rate: {1 - success_rate:.0%}"

        last_used = metadata.get('last_used')
        if last_used:
            if isinstance(last_used, str):
                last_used = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
            days = (datetime.utcnow() - last_used).days
            return f"Unused for {days} days"

        return "Scheduled revalidation"
