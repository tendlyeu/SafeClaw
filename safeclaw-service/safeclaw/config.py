"""SafeClaw configuration via Pydantic settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class SafeClawConfig(BaseSettings):
    model_config = {"env_prefix": "SAFECLAW_"}

    host: str = "127.0.0.1"
    port: int = 8420

    # Paths
    data_dir: Path = Path.home() / ".safeclaw"
    ontology_dir: Path | None = None  # defaults to bundled ontologies
    audit_dir: Path | None = None  # defaults to data_dir / "audit"

    # CORS
    cors_origin_regex: str = r"https?://localhost:\d+"

    # Auth
    require_auth: bool = False

    # Logging
    log_level: str = "INFO"

    # Admin dashboard
    admin_password: str = ""

    # LLM layer (passive observer — all features gated on mistral_api_key)
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_model_large: str = "mistral-large-latest"
    mistral_timeout_ms: int = 3000
    llm_security_review_enabled: bool = True
    llm_classification_observe: bool = True

    def get_ontology_dir(self) -> Path:
        if self.ontology_dir:
            return self.ontology_dir
        return Path(__file__).parent / "ontologies"

    def get_audit_dir(self) -> Path:
        if self.audit_dir:
            return self.audit_dir
        return self.data_dir / "audit"

    @property
    def raw(self) -> dict:
        config_path = self.data_dir / "config.json"
        if config_path.exists():
            import json
            with open(config_path) as f:
                return json.load(f)
        return {}
