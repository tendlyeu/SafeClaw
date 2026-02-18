"""Tenant provisioning - auto-creates org, ontologies, default policies."""

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger("safeclaw.cloud.tenant")

# Policy templates for onboarding wizard
POLICY_TEMPLATES = {
    "software_development": {
        "name": "Software Development",
        "description": "Policies for coding assistants working on software projects",
        "policies": [
            "NoForcePush", "NoResetHard", "NoEnvFiles", "NoCredentialFiles",
            "TestBeforePush", "NoRootDelete",
        ],
    },
    "data_analysis": {
        "name": "Data Analysis",
        "description": "Policies for agents working with data and notebooks",
        "policies": [
            "NoEnvFiles", "NoCredentialFiles", "NoRootDelete",
        ],
    },
    "devops": {
        "name": "DevOps / Infrastructure",
        "description": "Policies for agents managing infrastructure and deployments",
        "policies": [
            "NoForcePush", "NoResetHard", "NoEnvFiles", "NoCredentialFiles",
            "TestBeforePush", "NoRootDelete",
        ],
    },
    "general": {
        "name": "General Purpose",
        "description": "Balanced policies for general-purpose AI assistants",
        "policies": [
            "NoEnvFiles", "NoCredentialFiles", "NoRootDelete",
        ],
    },
}

AUTONOMY_LEVELS = {
    "cautious": "Agent asks for confirmation on most actions",
    "moderate": "Agent asks for confirmation on risky/irreversible actions",
    "autonomous": "Agent operates independently, blocked only by hard constraints",
}


@dataclass
class TenantConfig:
    """Configuration for a provisioned tenant."""
    org_id: str
    org_name: str
    policy_template: str
    autonomy_level: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data_dir: str = ""


class TenantProvisioner:
    """Handles tenant provisioning for SafeClaw Cloud.

    On signup:
    1. Creates org directory structure
    2. Copies default ontologies
    3. Applies selected policy template
    4. Sets autonomy level
    5. Generates first API key
    """

    def __init__(self, base_dir: Path, bundled_ontologies_dir: Path):
        self.base_dir = base_dir
        self.bundled_ontologies_dir = bundled_ontologies_dir

    def provision(
        self,
        org_name: str,
        policy_template: str = "general",
        autonomy_level: str = "moderate",
    ) -> TenantConfig:
        """Provision a new tenant with ontologies and policies."""
        if autonomy_level not in AUTONOMY_LEVELS:
            raise ValueError(f"Invalid autonomy level: {autonomy_level}")
        org_id = str(uuid4())
        org_dir = self.base_dir / "tenants" / org_id
        ontology_dir = org_dir / "ontologies"

        # Create directory structure
        ontology_dir.mkdir(parents=True, exist_ok=True)
        (org_dir / "audit").mkdir(exist_ok=True)

        # Copy bundled ontologies
        if self.bundled_ontologies_dir.exists():
            for ttl_file in self.bundled_ontologies_dir.glob("*.ttl"):
                shutil.copy2(ttl_file, ontology_dir / ttl_file.name)
            # Copy shapes
            shapes_src = self.bundled_ontologies_dir / "shapes"
            shapes_dst = ontology_dir / "shapes"
            if shapes_src.exists():
                shutil.copytree(shapes_src, shapes_dst, dirs_exist_ok=True)
            # Copy user defaults
            users_src = self.bundled_ontologies_dir / "users"
            users_dst = ontology_dir / "users"
            if users_src.exists():
                shutil.copytree(users_src, users_dst, dirs_exist_ok=True)

        # Apply autonomy level to user preferences
        self._set_autonomy_level(ontology_dir, autonomy_level)

        config = TenantConfig(
            org_id=org_id,
            org_name=org_name,
            policy_template=policy_template,
            autonomy_level=autonomy_level,
            data_dir=str(org_dir),
        )

        logger.info(f"Provisioned tenant {org_id} ({org_name}) with template '{policy_template}'")
        return config

    def _set_autonomy_level(self, ontology_dir: Path, level: str) -> None:
        """Update the user preferences file with the selected autonomy level."""
        user_file = ontology_dir / "users" / "user-default.ttl"
        if not user_file.exists():
            return
        content = user_file.read_text()
        content = re.sub(
            r'su:autonomyLevel\s+"[^"]*"',
            f'su:autonomyLevel "{level}"',
            content,
        )
        user_file.write_text(content)

    @staticmethod
    def get_templates() -> dict:
        """Get available policy templates for the onboarding wizard."""
        return POLICY_TEMPLATES

    @staticmethod
    def get_autonomy_levels() -> dict:
        """Get available autonomy levels."""
        return AUTONOMY_LEVELS
