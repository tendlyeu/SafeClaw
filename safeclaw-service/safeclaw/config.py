"""SafeClaw configuration via Pydantic settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class SafeClawConfig(BaseSettings):
    model_config = {"env_prefix": "SAFECLAW_"}

    host: str = "0.0.0.0"
    port: int = 8420

    # Paths
    data_dir: Path = Path.home() / ".safeclaw"
    ontology_dir: Path | None = None  # defaults to bundled ontologies
    audit_dir: Path | None = None  # defaults to data_dir / "audit"

    # Reasoner
    run_reasoner_on_startup: bool = True

    # Logging
    log_level: str = "INFO"

    def get_ontology_dir(self) -> Path:
        if self.ontology_dir:
            return self.ontology_dir
        return Path(__file__).parent / "ontologies"

    def get_audit_dir(self) -> Path:
        if self.audit_dir:
            return self.audit_dir
        return self.data_dir / "audit"
