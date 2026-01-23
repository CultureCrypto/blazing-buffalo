#!/usr/bin/env python3
"""
Input validation framework for engineer-team scripts.

Provides safe input validation and sanitization functions to prevent
shell injection, path traversal, and other security vulnerabilities.

Usage:
    from lib.validators import validate_path, validate_event_type, sanitize_description

    # Validate event type against whitelist
    if not validate_event_type("task_completion"):
        raise ValueError("Invalid event type")

    # Sanitize description for shell safety
    safe_desc = sanitize_description(user_input)

    # Validate file paths
    safe_path = validate_path("/some/path/file.json", must_exist=False)
"""

import re
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import json


# Whitelist of allowed event types
ALLOWED_EVENT_TYPES = {
    "task_completion",
    "pattern_discovered",
    "best_practice",
    "integration_pattern",
    "optimization",
    "security_fix",
    "architecture_decision",
    "test_coverage",
    "bug_discovery",
    "performance_improvement",
}

# Maximum input lengths to prevent DoS
MAX_DESCRIPTION_LENGTH = 10000
MAX_TAG_LENGTH = 100
MAX_ID_LENGTH = 200
MAX_TAGS_COUNT = 50


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_event_type(event_type: str) -> str:
    """
    Validate event type against whitelist.

    Args:
        event_type: Event type string to validate

    Returns:
        The validated event type (same as input)

    Raises:
        ValidationError: If event type is not in whitelist
    """
    if not isinstance(event_type, str):
        raise ValidationError(f"Event type must be string, got {type(event_type)}")

    event_type = event_type.strip().lower()

    if not event_type:
        raise ValidationError("Event type cannot be empty")

    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValidationError(
            f"Invalid event type: '{event_type}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_EVENT_TYPES))}"
        )

    return event_type


def sanitize_description(description: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """
    Sanitize description text for safe shell usage.

    Removes/escapes characters that could be used for shell injection.
    Preserves readability while ensuring security.

    Args:
        description: Description text to sanitize
        max_length: Maximum allowed length (default: 10000)

    Returns:
        Sanitized description string

    Raises:
        ValidationError: If input is invalid
    """
    if not isinstance(description, str):
        raise ValidationError(f"Description must be string, got {type(description)}")

    # Remove null bytes
    description = description.replace('\x00', '')

    # Limit length
    if len(description) > max_length:
        raise ValidationError(
            f"Description exceeds maximum length of {max_length} characters "
            f"(got {len(description)})"
        )

    if not description.strip():
        raise ValidationError("Description cannot be empty")

    # Remove control characters except newline and tab
    sanitized = ''.join(
        char for char in description
        if char in '\n\t' or (ord(char) >= 32 and ord(char) != 127)
    )

    # Escape shell-dangerous characters for JSON
    # We use Python's json.dumps to properly escape for JSON
    # This handles quotes, backslashes, etc. safely
    try:
        # This will properly escape the string
        json_safe = json.dumps(sanitized)[1:-1]  # Remove outer quotes
        return json_safe
    except Exception as e:
        raise ValidationError(f"Failed to sanitize description: {e}")


def validate_tags(tags_str: str) -> List[str]:
    """
    Validate and parse comma-separated tags.

    Args:
        tags_str: Comma-separated tag string

    Returns:
        List of validated tag strings

    Raises:
        ValidationError: If tags are invalid
    """
    if not isinstance(tags_str, str):
        raise ValidationError(f"Tags must be string, got {type(tags_str)}")

    if not tags_str.strip():
        return []

    # Split and clean tags
    tags = [tag.strip() for tag in tags_str.split(',')]
    tags = [tag for tag in tags if tag]  # Remove empty tags

    if len(tags) > MAX_TAGS_COUNT:
        raise ValidationError(
            f"Too many tags: {len(tags)} (maximum: {MAX_TAGS_COUNT})"
        )

    validated_tags = []
    tag_pattern = re.compile(r'^[a-zA-Z0-9_\-]+$')

    for tag in tags:
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"Tag '{tag[:50]}...' exceeds maximum length of {MAX_TAG_LENGTH}"
            )

        if not tag_pattern.match(tag):
            raise ValidationError(
                f"Invalid tag '{tag}': tags must contain only alphanumeric "
                f"characters, underscores, and hyphens"
            )

        validated_tags.append(tag)

    return validated_tags


def validate_id(id_str: str, id_type: str = "ID") -> str:
    """
    Validate ID strings (event_id, task_id, agent_id, etc.).

    Args:
        id_str: ID string to validate
        id_type: Type of ID for error messages (default: "ID")

    Returns:
        Validated ID string

    Raises:
        ValidationError: If ID is invalid
    """
    if not isinstance(id_str, str):
        raise ValidationError(f"{id_type} must be string, got {type(id_str)}")

    id_str = id_str.strip()

    if not id_str:
        raise ValidationError(f"{id_type} cannot be empty")

    if len(id_str) > MAX_ID_LENGTH:
        raise ValidationError(
            f"{id_type} exceeds maximum length of {MAX_ID_LENGTH} characters"
        )

    # Allow alphanumeric, underscore, hyphen, and period
    id_pattern = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
    if not id_pattern.match(id_str):
        raise ValidationError(
            f"Invalid {id_type} '{id_str}': must contain only alphanumeric "
            f"characters, underscores, hyphens, and periods"
        )

    return id_str


def validate_path(
    path_str: str,
    must_exist: bool = False,
    must_be_file: bool = False,
    must_be_dir: bool = False,
    base_dir: Optional[str] = None
) -> Path:
    """
    Validate file system paths to prevent path traversal attacks.

    Args:
        path_str: Path string to validate
        must_exist: If True, path must exist on filesystem
        must_be_file: If True, path must be a file
        must_be_dir: If True, path must be a directory
        base_dir: If provided, path must be within this directory

    Returns:
        Validated Path object

    Raises:
        ValidationError: If path is invalid or unsafe
    """
    if not isinstance(path_str, str):
        raise ValidationError(f"Path must be string, got {type(path_str)}")

    path_str = path_str.strip()

    if not path_str:
        raise ValidationError("Path cannot be empty")

    # Remove null bytes
    if '\x00' in path_str:
        raise ValidationError("Path contains null bytes")

    try:
        path = Path(path_str).resolve()
    except (ValueError, OSError) as e:
        raise ValidationError(f"Invalid path: {e}")

    # Check for path traversal if base_dir specified
    if base_dir:
        try:
            base = Path(base_dir).resolve()
            # Check if path is within base_dir
            path.relative_to(base)
        except (ValueError, OSError):
            raise ValidationError(
                f"Path '{path}' is outside allowed directory '{base_dir}'"
            )

    # Existence checks
    if must_exist and not path.exists():
        raise ValidationError(f"Path does not exist: {path}")

    if must_be_file:
        if not path.exists():
            raise ValidationError(f"File does not exist: {path}")
        if not path.is_file():
            raise ValidationError(f"Path is not a file: {path}")

    if must_be_dir:
        if not path.exists():
            raise ValidationError(f"Directory does not exist: {path}")
        if not path.is_dir():
            raise ValidationError(f"Path is not a directory: {path}")

    return path


def validate_json(json_str: str) -> Dict[str, Any]:
    """
    Validate and parse JSON string.

    Args:
        json_str: JSON string to validate

    Returns:
        Parsed JSON as dictionary

    Raises:
        ValidationError: If JSON is invalid
    """
    if not isinstance(json_str, str):
        raise ValidationError(f"JSON must be string, got {type(json_str)}")

    json_str = json_str.strip()

    if not json_str:
        return {}

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise ValidationError(f"JSON must be object/dict, got {type(data)}")

    return data


def validate_url(url: str, allowed_schemes: Optional[List[str]] = None) -> str:
    """
    Validate URL format and scheme.

    Args:
        url: URL string to validate
        allowed_schemes: List of allowed schemes (default: ['http', 'https', 'bolt'])

    Returns:
        Validated URL string

    Raises:
        ValidationError: If URL is invalid
    """
    if allowed_schemes is None:
        allowed_schemes = ['http', 'https', 'bolt']

    if not isinstance(url, str):
        raise ValidationError(f"URL must be string, got {type(url)}")

    url = url.strip()

    if not url:
        raise ValidationError("URL cannot be empty")

    # Basic URL pattern validation
    url_pattern = re.compile(
        r'^(?P<scheme>[a-z][a-z0-9+.-]*):\/\/'  # scheme
        r'(?P<host>[a-zA-Z0-9._-]+)'  # host
        r'(?::(?P<port>\d+))?'  # optional port
        r'(?P<path>\/[^\s]*)?$'  # optional path
    )

    match = url_pattern.match(url.lower())
    if not match:
        raise ValidationError(f"Invalid URL format: {url}")

    scheme = match.group('scheme')
    if scheme not in allowed_schemes:
        raise ValidationError(
            f"Invalid URL scheme '{scheme}'. Allowed: {', '.join(allowed_schemes)}"
        )

    return url


# CLI interface for bash scripts
def main():
    """Command-line interface for validation functions."""
    if len(sys.argv) < 3:
        print("Usage: validators.py <function> <value> [options]", file=sys.stderr)
        print("\nFunctions:", file=sys.stderr)
        print("  event_type <type>", file=sys.stderr)
        print("  description <text>", file=sys.stderr)
        print("  tags <comma,separated,tags>", file=sys.stderr)
        print("  id <id_string> [type_name]", file=sys.stderr)
        print("  path <path> [--must-exist] [--must-be-file] [--base-dir DIR]", file=sys.stderr)
        print("  json <json_string>", file=sys.stderr)
        print("  url <url>", file=sys.stderr)
        sys.exit(1)

    function = sys.argv[1]
    value = sys.argv[2]

    try:
        if function == "event_type":
            result = validate_event_type(value)
            print(result)

        elif function == "description":
            result = sanitize_description(value)
            print(result)

        elif function == "tags":
            result = validate_tags(value)
            print(','.join(result))

        elif function == "id":
            id_type = sys.argv[3] if len(sys.argv) > 3 else "ID"
            result = validate_id(value, id_type)
            print(result)

        elif function == "path":
            must_exist = "--must-exist" in sys.argv
            must_be_file = "--must-be-file" in sys.argv
            must_be_dir = "--must-be-dir" in sys.argv
            base_dir = None
            if "--base-dir" in sys.argv:
                idx = sys.argv.index("--base-dir")
                if idx + 1 < len(sys.argv):
                    base_dir = sys.argv[idx + 1]

            result = validate_path(value, must_exist, must_be_file, must_be_dir, base_dir)
            print(result)

        elif function == "json":
            result = validate_json(value)
            print(json.dumps(result))

        elif function == "url":
            result = validate_url(value)
            print(result)

        else:
            print(f"Unknown function: {function}", file=sys.stderr)
            sys.exit(1)

    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
