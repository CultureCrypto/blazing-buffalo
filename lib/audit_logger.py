"""
Compliance Audit Logger for Blazing Buffalo Mistake System.

Secure audit logging with:
- Encryption at rest (Fernet)
- Role-based access control
- 1-year retention policy
- Sensitive access alerts
- Thread-safe operations
- Log rotation and archival

Logs all data access events (read, write, delete, export).
"""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import json
import hashlib
from cryptography.fernet import Fernet
import threading
import os


class AuditAction(Enum):
    """Audit event actions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXPORT = "export"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"


class ResourceType(Enum):
    """Resource types for audit tracking."""
    MISTAKE = "mistake"
    PLAYBOOK = "playbook"
    TAXONOMY = "taxonomy"
    CONFIG = "config"
    USER = "user"
    API_KEY = "api_key"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    timestamp: datetime
    action: AuditAction
    resource_type: ResourceType
    resource_id: str
    user_id: str
    user_role: str
    ip_address: Optional[str]
    success: bool
    details: Dict[str, Any]
    session_id: Optional[str] = None
    request_id: Optional[str] = None


class AuditLogger:
    """
    Secure audit logger with encryption and retention policies.

    Features:
    - Encryption at rest using Fernet symmetric encryption
    - Role-based access control for log reading
    - 365-day retention policy
    - Automatic log rotation
    - Thread-safe operations
    - Sensitive access alerting

    Usage:
        logger = AuditLogger()

        # Log an event
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            action=AuditAction.READ,
            resource_type=ResourceType.MISTAKE,
            resource_id="MSTK-001",
            user_id="user123",
            user_role="developer",
            ip_address="192.168.1.1",
            success=True,
            details={"query": "SELECT * FROM mistakes"}
        )
        logger.log(event)

        # Read logs (restricted)
        logs = logger.read_logs("security-engineer", limit=100)

        # Register alert callback
        logger.register_alert_callback(lambda e: send_alert(e))
    """

    LOG_DIR = Path("/var/log/engineer-team")
    LOG_FILE = "mistake-audit.jsonl"
    RETENTION_DAYS = 365
    ALLOWED_ROLES = ["security-engineer", "sre-engineer", "admin"]
    SENSITIVE_RESOURCES = ["config", "user", "api_key"]

    def __init__(self, encryption_key: bytes = None, log_dir: Path = None):
        """
        Initialize audit logger.

        Args:
            encryption_key: Fernet encryption key (generates if None)
            log_dir: Custom log directory (uses default if None)
        """
        self.LOG_DIR = log_dir or self.LOG_DIR
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Set up encryption
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            # Generate and store key securely
            key_path = self.LOG_DIR / ".audit_key"
            if key_path.exists():
                with open(key_path, 'rb') as f:
                    key = f.read()
            else:
                key = Fernet.generate_key()
                with open(key_path, 'wb') as f:
                    f.write(key)
                os.chmod(key_path, 0o600)  # Restrict permissions
            self.cipher = Fernet(key)

        self.alert_callbacks: List[Callable[[AuditEvent], None]] = []

    def log(self, event: AuditEvent) -> str:
        """
        Log an audit event with encryption.

        Args:
            event: AuditEvent to log

        Returns:
            event_id: Unique event identifier
        """
        with self._lock:
            # Generate event ID
            event_id = self._generate_event_id(event)

            # Serialize event
            event_dict = {
                "event_id": event_id,
                "timestamp": event.timestamp.isoformat(),
                "action": event.action.value,
                "resource_type": event.resource_type.value,
                "resource_id": event.resource_id,
                "user_id": event.user_id,
                "user_role": event.user_role,
                "ip_address": event.ip_address,
                "success": event.success,
                "details": event.details,
                "session_id": event.session_id,
                "request_id": event.request_id
            }

            # Encrypt sensitive fields
            encrypted = self._encrypt_event(event_dict)

            # Write to log file
            log_path = self.LOG_DIR / self.LOG_FILE
            with open(log_path, 'a') as f:
                f.write(json.dumps(encrypted) + '\n')

            # Check for sensitive access alerts
            if self._is_sensitive_access(event):
                self._trigger_alert(event)

            return event_id

    def read_logs(self,
                  user_role: str,
                  start_date: Optional[datetime] = None,
                  end_date: Optional[datetime] = None,
                  action: Optional[AuditAction] = None,
                  resource_type: Optional[ResourceType] = None,
                  user_id: Optional[str] = None,
                  limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Read audit logs (restricted to allowed roles).

        Args:
            user_role: Role requesting access
            start_date: Filter events after this date
            end_date: Filter events before this date
            action: Filter by action type
            resource_type: Filter by resource type
            user_id: Filter by user ID
            limit: Maximum number of events to return

        Returns:
            List of decrypted audit events

        Raises:
            PermissionError: If user_role not authorized
        """
        if user_role not in self.ALLOWED_ROLES:
            raise PermissionError(
                f"Role '{user_role}' not authorized to read audit logs. "
                f"Allowed roles: {', '.join(self.ALLOWED_ROLES)}"
            )

        logs = []
        log_path = self.LOG_DIR / self.LOG_FILE

        if not log_path.exists():
            return []

        with self._lock:
            with open(log_path, 'r') as f:
                for line in f:
                    if len(logs) >= limit:
                        break

                    try:
                        encrypted = json.loads(line.strip())
                        event = self._decrypt_event(encrypted)

                        # Apply filters
                        event_time = datetime.fromisoformat(event['timestamp'])
                        if start_date and event_time < start_date:
                            continue
                        if end_date and event_time > end_date:
                            continue
                        if action and event['action'] != action.value:
                            continue
                        if resource_type and event['resource_type'] != resource_type.value:
                            continue
                        if user_id and event['user_id'] != user_id:
                            continue

                        logs.append(event)
                    except (json.JSONDecodeError, KeyError):
                        continue  # Skip corrupted entries

        return logs

    def register_alert_callback(self, callback: Callable[[AuditEvent], None]) -> None:
        """
        Register callback for sensitive access alerts.

        Args:
            callback: Function accepting AuditEvent parameter
        """
        self.alert_callbacks.append(callback)

    def rotate_logs(self) -> None:
        """
        Rotate and archive old logs.

        Creates archive with date stamp and cleans up old archives
        beyond retention period.
        """
        with self._lock:
            log_path = self.LOG_DIR / self.LOG_FILE
            if not log_path.exists():
                return

            # Archive current log
            archive_name = f"mistake-audit-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.jsonl"
            archive_dir = self.LOG_DIR / "archive"
            archive_dir.mkdir(exist_ok=True)
            archive_path = archive_dir / archive_name

            # Move current log to archive
            log_path.rename(archive_path)

            # Clean up old archives beyond retention
            self._cleanup_old_archives()

    def get_stats(self, user_role: str) -> Dict[str, Any]:
        """
        Get audit log statistics.

        Args:
            user_role: Role requesting stats

        Returns:
            Statistics dictionary

        Raises:
            PermissionError: If user_role not authorized
        """
        if user_role not in self.ALLOWED_ROLES:
            raise PermissionError(f"Role '{user_role}' not authorized")

        stats = {
            "total_events": 0,
            "by_action": {},
            "by_resource": {},
            "failures": 0,
            "oldest_event": None,
            "newest_event": None
        }

        log_path = self.LOG_DIR / self.LOG_FILE
        if not log_path.exists():
            return stats

        with self._lock:
            with open(log_path, 'r') as f:
                for line in f:
                    try:
                        encrypted = json.loads(line.strip())
                        event = self._decrypt_event(encrypted)

                        stats["total_events"] += 1

                        # Count by action
                        action = event["action"]
                        stats["by_action"][action] = stats["by_action"].get(action, 0) + 1

                        # Count by resource
                        resource = event["resource_type"]
                        stats["by_resource"][resource] = stats["by_resource"].get(resource, 0) + 1

                        # Count failures
                        if not event["success"]:
                            stats["failures"] += 1

                        # Track date range
                        timestamp = event["timestamp"]
                        if not stats["oldest_event"]:
                            stats["oldest_event"] = timestamp
                        stats["newest_event"] = timestamp

                    except (json.JSONDecodeError, KeyError):
                        continue

        return stats

    def _encrypt_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in event.

        Args:
            event: Event dictionary

        Returns:
            Event with encrypted sensitive fields
        """
        sensitive_fields = ['details', 'ip_address', 'session_id']
        encrypted = event.copy()

        for field in sensitive_fields:
            if field in encrypted and encrypted[field]:
                value = json.dumps(encrypted[field]) if isinstance(encrypted[field], dict) else str(encrypted[field])
                encrypted[field] = self.cipher.encrypt(value.encode()).decode()

        return encrypted

    def _decrypt_event(self, encrypted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in event.

        Args:
            encrypted: Event with encrypted fields

        Returns:
            Event with decrypted fields
        """
        sensitive_fields = ['details', 'ip_address', 'session_id']
        decrypted = encrypted.copy()

        for field in sensitive_fields:
            if field in decrypted and decrypted[field]:
                try:
                    value = self.cipher.decrypt(decrypted[field].encode()).decode()
                    try:
                        decrypted[field] = json.loads(value)
                    except json.JSONDecodeError:
                        decrypted[field] = value
                except Exception:
                    pass  # Already decrypted or invalid

        return decrypted

    def _generate_event_id(self, event: AuditEvent) -> str:
        """
        Generate unique event ID.

        Args:
            event: AuditEvent

        Returns:
            SHA-256 hash prefix (16 chars)
        """
        data = (
            f"{event.timestamp.isoformat()}"
            f"{event.action.value}"
            f"{event.resource_id}"
            f"{event.user_id}"
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _is_sensitive_access(self, event: AuditEvent) -> bool:
        """
        Check if access should trigger alert.

        Args:
            event: AuditEvent to check

        Returns:
            True if sensitive access detected
        """
        # Alert on sensitive resource access
        if event.resource_type.value in self.SENSITIVE_RESOURCES:
            return True

        # Alert on destructive actions
        if event.action in [AuditAction.DELETE, AuditAction.EXPORT]:
            return True

        # Alert on failed login attempts
        if not event.success and event.action == AuditAction.LOGIN:
            return True

        return False

    def _trigger_alert(self, event: AuditEvent) -> None:
        """
        Trigger alert for sensitive access.

        Args:
            event: AuditEvent triggering alert
        """
        for callback in self.alert_callbacks:
            try:
                callback(event)
            except Exception:
                pass  # Don't let callback errors break logging

    def _cleanup_old_archives(self) -> None:
        """Remove archives older than retention period."""
        archive_dir = self.LOG_DIR / "archive"
        if not archive_dir.exists():
            return

        cutoff = datetime.utcnow().timestamp() - (self.RETENTION_DAYS * 86400)

        for archive in archive_dir.glob("*.jsonl"):
            if archive.stat().st_mtime < cutoff:
                archive.unlink()
