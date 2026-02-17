"""Phase 7 tests: tenant provisioning, config, policy templates, autonomy levels."""

import pytest

from safeclaw.cloud.tenant import (
    AUTONOMY_LEVELS,
    POLICY_TEMPLATES,
    TenantConfig,
    TenantProvisioner,
)


# --- Fixtures ---

@pytest.fixture
def bundled_ontologies(tmp_path):
    """Create a fake bundled ontologies directory with .ttl files, shapes, and users."""
    ont_dir = tmp_path / "bundled"
    ont_dir.mkdir()

    # Top-level .ttl files
    (ont_dir / "actions.ttl").write_text("@prefix sa: <urn:safeclaw:actions#> .\n")
    (ont_dir / "policies.ttl").write_text("@prefix sp: <urn:safeclaw:policies#> .\n")

    # shapes subdirectory
    shapes = ont_dir / "shapes"
    shapes.mkdir()
    (shapes / "action-shape.ttl").write_text("@prefix sh: <urn:safeclaw:shapes#> .\n")

    # users subdirectory with user-default.ttl containing autonomyLevel
    users = ont_dir / "users"
    users.mkdir()
    (users / "user-default.ttl").write_text(
        '@prefix su: <urn:safeclaw:user#> .\n'
        'su:defaultUser su:autonomyLevel "moderate" .\n'
    )

    return ont_dir


@pytest.fixture
def provisioner(tmp_path, bundled_ontologies):
    """TenantProvisioner with real base dir and bundled ontologies."""
    base = tmp_path / "data"
    base.mkdir()
    return TenantProvisioner(base_dir=base, bundled_ontologies_dir=bundled_ontologies)


# --- TenantProvisioner Tests ---

class TestTenantProvisioner:
    def test_provision_creates_directory_structure(self, provisioner, tmp_path):
        config = provisioner.provision("Acme Corp")
        org_dir = tmp_path / "data" / "tenants" / config.org_id
        assert org_dir.is_dir()
        assert (org_dir / "ontologies").is_dir()
        assert (org_dir / "audit").is_dir()

    def test_provision_copies_ttl_files(self, provisioner, tmp_path):
        config = provisioner.provision("Acme Corp")
        ont_dir = tmp_path / "data" / "tenants" / config.org_id / "ontologies"
        assert (ont_dir / "actions.ttl").exists()
        assert (ont_dir / "policies.ttl").exists()
        # Verify content was copied correctly
        assert "safeclaw:actions" in (ont_dir / "actions.ttl").read_text()

    def test_provision_copies_shapes_subdirectory(self, provisioner, tmp_path):
        config = provisioner.provision("Acme Corp")
        shapes = tmp_path / "data" / "tenants" / config.org_id / "ontologies" / "shapes"
        assert shapes.is_dir()
        assert (shapes / "action-shape.ttl").exists()

    def test_provision_copies_users_subdirectory(self, provisioner, tmp_path):
        config = provisioner.provision("Acme Corp")
        users = tmp_path / "data" / "tenants" / config.org_id / "ontologies" / "users"
        assert users.is_dir()
        assert (users / "user-default.ttl").exists()

    def test_provision_applies_autonomy_level(self, provisioner, tmp_path):
        config = provisioner.provision("Acme Corp", autonomy_level="cautious")
        user_file = (
            tmp_path / "data" / "tenants" / config.org_id
            / "ontologies" / "users" / "user-default.ttl"
        )
        content = user_file.read_text()
        assert 'su:autonomyLevel "cautious"' in content
        assert 'su:autonomyLevel "moderate"' not in content

    def test_provision_returns_correct_config(self, provisioner):
        config = provisioner.provision(
            "Acme Corp",
            policy_template="devops",
            autonomy_level="autonomous",
        )
        assert isinstance(config, TenantConfig)
        assert config.org_name == "Acme Corp"
        assert config.policy_template == "devops"
        assert config.autonomy_level == "autonomous"
        assert len(config.org_id) == 8
        assert config.data_dir != ""

    def test_provision_with_missing_bundled_ontologies_dir(self, tmp_path):
        """Provisioning with a nonexistent bundled dir should not crash."""
        base = tmp_path / "data"
        base.mkdir()
        missing = tmp_path / "does_not_exist"
        prov = TenantProvisioner(base_dir=base, bundled_ontologies_dir=missing)
        config = prov.provision("NoBundled Inc")
        # Directories should still be created
        org_dir = base / "tenants" / config.org_id
        assert org_dir.is_dir()
        assert (org_dir / "ontologies").is_dir()
        assert (org_dir / "audit").is_dir()
        # But no .ttl files copied
        assert list((org_dir / "ontologies").glob("*.ttl")) == []

    def test_provision_generates_unique_org_ids(self, provisioner):
        config1 = provisioner.provision("Org A")
        config2 = provisioner.provision("Org B")
        assert config1.org_id != config2.org_id

    def test_get_templates_returns_policy_templates(self):
        templates = TenantProvisioner.get_templates()
        assert templates is POLICY_TEMPLATES
        assert "software_development" in templates
        assert "data_analysis" in templates
        assert "devops" in templates
        assert "general" in templates

    def test_get_autonomy_levels_returns_levels(self):
        levels = TenantProvisioner.get_autonomy_levels()
        assert levels is AUTONOMY_LEVELS
        assert "cautious" in levels
        assert "moderate" in levels
        assert "autonomous" in levels


# --- TenantConfig Tests ---

class TestTenantConfig:
    def test_created_at_auto_populated(self):
        config = TenantConfig(
            org_id="abc123",
            org_name="Test Org",
            policy_template="general",
            autonomy_level="moderate",
        )
        assert config.created_at != ""
        # ISO format contains 'T' separator
        assert "T" in config.created_at

    def test_default_data_dir_is_empty(self):
        config = TenantConfig(
            org_id="abc123",
            org_name="Test Org",
            policy_template="general",
            autonomy_level="moderate",
        )
        assert config.data_dir == ""


# --- Edge Cases ---

class TestTenantEdgeCases:
    def test_set_autonomy_level_when_user_file_missing(self, tmp_path):
        """_set_autonomy_level should not crash if user-default.ttl doesn't exist."""
        base = tmp_path / "data"
        base.mkdir()
        bundled = tmp_path / "bundled_empty"
        bundled.mkdir()
        # No users/ subdirectory, so user-default.ttl won't be copied
        prov = TenantProvisioner(base_dir=base, bundled_ontologies_dir=bundled)
        config = prov.provision("NoUserFile Inc", autonomy_level="autonomous")
        # Should complete without error
        assert config.org_id is not None

    def test_provision_default_autonomy_is_moderate(self, provisioner, tmp_path):
        """Default autonomy level should be moderate when not specified."""
        config = provisioner.provision("Default Corp")
        user_file = (
            tmp_path / "data" / "tenants" / config.org_id
            / "ontologies" / "users" / "user-default.ttl"
        )
        content = user_file.read_text()
        assert 'su:autonomyLevel "moderate"' in content

    def test_provision_default_policy_template_is_general(self, provisioner):
        config = provisioner.provision("Default Corp")
        assert config.policy_template == "general"

    def test_policy_templates_have_required_fields(self):
        for key, tmpl in POLICY_TEMPLATES.items():
            assert "name" in tmpl, f"Template '{key}' missing 'name'"
            assert "description" in tmpl, f"Template '{key}' missing 'description'"
            assert "policies" in tmpl, f"Template '{key}' missing 'policies'"
            assert isinstance(tmpl["policies"], list)

    def test_autonomy_levels_have_descriptions(self):
        for key, desc in AUTONOMY_LEVELS.items():
            assert isinstance(desc, str)
            assert len(desc) > 0
