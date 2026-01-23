"""
Per-Project Playbook Customization Resolver (BB-017).

Implements three-layer playbook resolution:
1. Global - Default playbooks for all projects
2. Project-Type - Type-specific overrides (python, typescript, go, etc.)
3. Local - Project-specific customizations (.playbooks/ in project root)

Features:
- Inheritance chain tracking for debugging
- Deep merge for configuration overrides
- "extends" syntax for playbook inheritance
- Auto-detection of project type
- List available playbooks per layer
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import yaml
from copy import deepcopy
import logging

logger = logging.getLogger(__name__)


@dataclass
class ResolvedPlaybook:
    """Result of resolving a playbook through all layers."""
    id: str
    layers_applied: List[str]
    final_config: Dict[str, Any]
    inheritance_chain: List[str]
    resolution_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "layers_applied": self.layers_applied,
            "final_config": self.final_config,
            "inheritance_chain": self.inheritance_chain,
            "resolution_path": str(self.resolution_path) if self.resolution_path else None,
        }


class PlaybookResolver:
    """Resolve playbooks across global, project-type, and local layers."""

    GLOBAL_DIR = Path("/home/pook/engineer-team/playbooks/global")
    PROJECT_TYPE_DIR = Path("/home/pook/engineer-team/playbooks")

    # Supported project types
    PROJECT_TYPE_INDICATORS = {
        "python": ["pyproject.toml", "setup.py", "requirements.txt"],
        "typescript": ["tsconfig.json", "package.json"],
        "go": ["go.mod", "go.sum"],
        "rust": ["Cargo.toml"],
        "java": ["pom.xml", "build.gradle"],
    }

    def __init__(
        self,
        project_root: Optional[Path] = None,
        project_type: Optional[str] = None,
    ):
        """
        Initialize resolver.

        Args:
            project_root: Root directory of the project. Defaults to cwd.
            project_type: Explicit project type. Auto-detected if not provided.
        """
        self.project_root = project_root or Path.cwd()
        self.project_type = project_type or self.detect_project_type()
        self.local_dir = self.project_root / ".playbooks"
        self._resolution_cache: Dict[str, ResolvedPlaybook] = {}

    def resolve(self, playbook_id: str) -> ResolvedPlaybook:
        """
        Resolve a playbook through all layers.

        Resolution order: global → project-type → local
        Later layers override earlier ones.

        Args:
            playbook_id: ID of playbook to resolve

        Returns:
            ResolvedPlaybook with final config and resolution metadata

        Raises:
            FileNotFoundError: If playbook not found in any layer
        """
        # Check cache
        if playbook_id in self._resolution_cache:
            return self._resolution_cache[playbook_id]

        layers_applied: List[str] = []
        inheritance_chain: List[str] = []
        config: Optional[Dict[str, Any]] = None
        resolution_path: Optional[Path] = None

        # Layer 1: Global
        global_config, global_path = self._load_layer(self.GLOBAL_DIR, playbook_id)
        if global_config:
            config = global_config
            layers_applied.append("global")
            inheritance_chain.append(f"global/{playbook_id}")
            resolution_path = global_path
            logger.debug(f"Loaded global playbook: {playbook_id}")

        # Layer 2: Project-Type
        if self.project_type:
            type_dir = self.PROJECT_TYPE_DIR / self.project_type
            type_config, type_path = self._load_layer(type_dir, playbook_id)
            if type_config:
                config = self._merge_configs(config or {}, type_config)
                layers_applied.append(f"project-type:{self.project_type}")
                inheritance_chain.append(f"{self.project_type}/{playbook_id}")
                resolution_path = type_path
                logger.debug(
                    f"Applied project-type override: {self.project_type}/{playbook_id}"
                )

        # Layer 3: Local
        local_config, local_path = self._load_layer(self.local_dir, playbook_id)
        if local_config:
            config = self._merge_configs(config or {}, local_config)
            layers_applied.append("local")
            inheritance_chain.append(f"local/{playbook_id}")
            resolution_path = local_path
            logger.debug(f"Applied local override: {playbook_id}")

        # If no config found, raise error
        if config is None:
            raise FileNotFoundError(
                f"Playbook '{playbook_id}' not found in any layer "
                f"(project_type={self.project_type})"
            )

        # Handle extends syntax for playbook inheritance
        if "extends" in config:
            extends_id = config.pop("extends")
            logger.debug(f"Playbook {playbook_id} extends {extends_id}")

            try:
                base = self.resolve(extends_id)
                config = self._merge_configs(base.final_config, config)
                # Prepend base inheritance chain
                inheritance_chain = base.inheritance_chain + inheritance_chain
            except FileNotFoundError as e:
                logger.error(f"Failed to resolve extends for {playbook_id}: {e}")
                raise

        result = ResolvedPlaybook(
            id=playbook_id,
            layers_applied=layers_applied,
            final_config=config,
            inheritance_chain=inheritance_chain,
            resolution_path=resolution_path,
        )

        # Cache result
        self._resolution_cache[playbook_id] = result
        return result

    def resolve_multi(self, playbook_ids: List[str]) -> Dict[str, ResolvedPlaybook]:
        """
        Resolve multiple playbooks.

        Args:
            playbook_ids: List of playbook IDs

        Returns:
            Dictionary mapping playbook_id to ResolvedPlaybook
        """
        results = {}
        for pb_id in playbook_ids:
            try:
                results[pb_id] = self.resolve(pb_id)
            except FileNotFoundError as e:
                logger.warning(f"Failed to resolve {pb_id}: {e}")
        return results

    def _load_layer(
        self, layer_dir: Path, playbook_id: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
        """
        Load playbook from a specific layer.

        Args:
            layer_dir: Directory to load from
            playbook_id: ID of playbook

        Returns:
            Tuple of (config_dict, path) or (None, None) if not found
        """
        playbook_path = layer_dir / f"{playbook_id}.yaml"

        if playbook_path.exists():
            try:
                with open(playbook_path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    return config, playbook_path
            except Exception as e:
                logger.error(f"Failed to load {playbook_path}: {e}")
                raise

        return None, None

    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge override into base.

        Rules:
        - Scalars: override replaces base
        - Lists: override replaces base (not concatenate)
        - Dicts: recursive merge
        - Special key 'merge_lists': if True, concatenate lists instead of replacing

        Args:
            base: Base configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        result = deepcopy(base)

        for key, value in override.items():
            if key in result:
                base_value = result[key]

                # Check for explicit list merge instruction
                merge_key = f"{key}_merge_lists"
                if isinstance(override.get(merge_key), bool) and override[merge_key]:
                    if isinstance(base_value, list) and isinstance(value, list):
                        result[key] = base_value + value
                        continue

                # Default merge behavior
                if isinstance(base_value, dict) and isinstance(value, dict):
                    result[key] = self._merge_configs(base_value, value)
                else:
                    result[key] = deepcopy(value)
            else:
                result[key] = deepcopy(value)

        return result

    def list_available(self) -> Dict[str, List[str]]:
        """
        List available playbooks per layer.

        Returns:
            Dictionary with keys 'global', 'project_type', 'local'
        """
        available = {"global": [], "project_type": [], "local": []}

        # Global
        if self.GLOBAL_DIR.exists():
            available["global"] = sorted(
                [p.stem for p in self.GLOBAL_DIR.glob("*.yaml")]
            )

        # Project type
        if self.project_type:
            type_dir = self.PROJECT_TYPE_DIR / self.project_type
            if type_dir.exists():
                available["project_type"] = sorted(
                    [p.stem for p in type_dir.glob("*.yaml")]
                )

        # Local
        if self.local_dir.exists():
            available["local"] = sorted([p.stem for p in self.local_dir.glob("*.yaml")])

        return available

    def list_available_all_types(self) -> Dict[str, List[str]]:
        """
        List available playbooks for all project types.

        Returns:
            Dictionary mapping project_type to list of playbook IDs
        """
        all_playbooks = {}

        # Global playbooks apply to all types
        if self.GLOBAL_DIR.exists():
            global_pbs = [p.stem for p in self.GLOBAL_DIR.glob("*.yaml")]
            for ptype in self.PROJECT_TYPE_INDICATORS.keys():
                all_playbooks[ptype] = global_pbs.copy()

        # Add type-specific playbooks
        for ptype in self.PROJECT_TYPE_INDICATORS.keys():
            type_dir = self.PROJECT_TYPE_DIR / ptype
            if type_dir.exists():
                type_pbs = [p.stem for p in type_dir.glob("*.yaml")]
                if ptype not in all_playbooks:
                    all_playbooks[ptype] = type_pbs
                else:
                    # Merge, removing duplicates
                    all_playbooks[ptype] = sorted(list(set(all_playbooks[ptype] + type_pbs)))

        return all_playbooks

    def detect_project_type(self) -> Optional[str]:
        """
        Auto-detect project type from files in project_root.

        Checks for type indicators in priority order.

        Returns:
            Detected project type or None
        """
        for ptype, files in self.PROJECT_TYPE_INDICATORS.items():
            for f in files:
                if (self.project_root / f).exists():
                    logger.debug(f"Detected project type: {ptype}")
                    return ptype

        logger.debug("Could not detect project type")
        return None

    def validate_playbook_config(
        self, playbook_id: str, schema: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate a resolved playbook against optional schema.

        Args:
            playbook_id: ID of playbook to validate
            schema: Optional validation schema (future enhancement)

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            resolved = self.resolve(playbook_id)
            config = resolved.final_config

            errors = []

            # Basic validation
            if not isinstance(config, dict):
                errors.append("Playbook must be a dictionary")
                return False, errors

            # Check for required fields if schema provided
            if schema:
                required_fields = schema.get("required", [])
                for field in required_fields:
                    if field not in config:
                        errors.append(f"Missing required field: {field}")

            return len(errors) == 0, errors

        except FileNotFoundError as e:
            return False, [str(e)]
        except Exception as e:
            return False, [f"Validation error: {e}"]

    def get_resolution_info(self, playbook_id: str) -> Dict[str, Any]:
        """
        Get detailed resolution information for a playbook.

        Useful for debugging and understanding resolution chain.

        Args:
            playbook_id: ID of playbook

        Returns:
            Dictionary with resolution details
        """
        try:
            resolved = self.resolve(playbook_id)
            return {
                "id": resolved.id,
                "layers_applied": resolved.layers_applied,
                "inheritance_chain": resolved.inheritance_chain,
                "resolution_path": str(resolved.resolution_path) if resolved.resolution_path else None,
                "project_type": self.project_type,
                "project_root": str(self.project_root),
                "config_keys": list(resolved.final_config.keys()),
            }
        except FileNotFoundError as e:
            return {"error": str(e)}

    def clear_cache(self) -> None:
        """Clear resolution cache."""
        self._resolution_cache.clear()
        logger.debug("Cleared playbook resolution cache")

    def export_resolved_playbook(
        self, playbook_id: str, output_path: Path
    ) -> bool:
        """
        Export a resolved playbook to a YAML file.

        Args:
            playbook_id: ID of playbook to export
            output_path: Path to write resolved playbook

        Returns:
            True if successful
        """
        try:
            resolved = self.resolve(playbook_id)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Add metadata
            export_data = {
                "id": resolved.id,
                "metadata": {
                    "layers_applied": resolved.layers_applied,
                    "inheritance_chain": resolved.inheritance_chain,
                    "project_type": self.project_type,
                },
                "playbook": resolved.final_config,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(export_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Exported resolved playbook to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export playbook: {e}")
            return False
