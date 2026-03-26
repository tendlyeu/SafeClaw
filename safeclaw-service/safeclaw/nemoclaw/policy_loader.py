"""NemoClaw policy loader - converts NemoClaw YAML policies to RDF triples."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from rdflib import Literal, Namespace, RDF, XSD

from safeclaw.engine.knowledge_graph import KnowledgeGraph

logger = logging.getLogger("safeclaw.nemoclaw")

SP = Namespace("http://safeclaw.uku.ai/ontology/policy#")


class NemoClawPolicyLoader:
    """Reads NemoClaw YAML policy files and inserts RDF triples into the knowledge graph."""

    def __init__(self, policy_dir: Path):
        self.policy_dir = policy_dir

    def load(self, kg: KnowledgeGraph) -> None:
        """Load all YAML policy files from the policy directory into the knowledge graph.

        Missing or non-existent directory is silently skipped. Malformed YAML
        files are logged as warnings and skipped individually.
        """
        if not self.policy_dir or not self.policy_dir.exists():
            return

        yaml_files = sorted(self.policy_dir.glob("*.yaml"))
        if not yaml_files:
            return

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed; NemoClaw policy loading disabled")
            return

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as exc:
                logger.warning("Malformed YAML in %s: %s", yaml_file.name, exc)
                continue

            if not isinstance(data, dict):
                logger.warning("Unexpected YAML structure in %s (expected mapping)", yaml_file.name)
                continue

            self._process_policy(kg, data, yaml_file.name)

    def _process_policy(
        self, kg: KnowledgeGraph, data: dict, filename: str
    ) -> None:
        """Process a single parsed YAML policy document."""
        rules = data.get("rules") or data.get("network", {}).get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    logger.warning("Skipping non-dict rule in %s", filename)
                    continue
                self._process_network_rule(kg, rule)

        fs_rules = data.get("filesystem") or data.get("fs_rules", [])
        if isinstance(fs_rules, list):
            for rule in fs_rules:
                if not isinstance(rule, dict):
                    logger.warning("Skipping non-dict filesystem rule in %s", filename)
                    continue
                self._process_filesystem_rule(kg, rule)

    def _process_network_rule(self, kg: KnowledgeGraph, rule: dict) -> None:
        """Convert a single network rule dict to RDF triples."""
        host = rule.get("host")
        if not host:
            return

        # Deny rules produce no triples (deny-by-default; absence = denied)
        if rule.get("allow") is False or rule.get("deny") is True:
            return

        port = rule.get("port")
        protocol = rule.get("protocol", "")

        rule_node = SP[f"nemo_net_{uuid4().hex}"]
        kg.add_triple(rule_node, RDF.type, SP.NemoNetworkRule)
        kg.add_triple(rule_node, SP.allowsHost, Literal(host, datatype=XSD.string))
        kg.add_triple(rule_node, SP.source, Literal("nemoclaw", datatype=XSD.string))

        if port is not None:
            kg.add_triple(rule_node, SP.allowsPort, Literal(int(port), datatype=XSD.integer))

        if protocol:
            kg.add_triple(
                rule_node, SP.allowsProtocol, Literal(protocol, datatype=XSD.string)
            )

        binary = rule.get("binary")
        if binary:
            kg.add_triple(
                rule_node, SP.binaryRestriction, Literal(binary, datatype=XSD.string)
            )

        # Auto-generate reason
        reason = self._network_reason(host, port, protocol)
        kg.add_triple(rule_node, SP.reason, Literal(reason, datatype=XSD.string))

    def _process_filesystem_rule(self, kg: KnowledgeGraph, rule: dict) -> None:
        """Convert a single filesystem rule dict to RDF triples."""
        path = rule.get("path")
        if not path:
            return

        mode = rule.get("mode") or rule.get("access") or rule.get("accessMode")
        if not mode:
            return

        # Normalize mode values
        mode_lower = mode.lower().replace("_", "-")
        if mode_lower not in ("read-only", "read-write", "denied"):
            logger.warning("Unknown filesystem access mode: %s for path %s", mode, path)
            return

        rule_node = SP[f"nemo_fs_{uuid4().hex}"]
        kg.add_triple(rule_node, RDF.type, SP.NemoFilesystemRule)
        kg.add_triple(rule_node, SP.path, Literal(path, datatype=XSD.string))
        kg.add_triple(rule_node, SP.accessMode, Literal(mode_lower, datatype=XSD.string))
        kg.add_triple(rule_node, SP.source, Literal("nemoclaw", datatype=XSD.string))

        # Auto-generate reason
        reason = self._filesystem_reason(path, mode_lower)
        kg.add_triple(rule_node, SP.reason, Literal(reason, datatype=XSD.string))

    @staticmethod
    def _network_reason(host: str, port: int | None, protocol: str) -> str:
        """Generate human-readable reason for a network rule."""
        parts = [f"NemoClaw: host {host} allowed"]
        if port is not None:
            parts.append(f"on port {port}")
            if protocol:
                parts.append(f"({protocol})")
        elif protocol:
            parts.append(f"({protocol})")
        return " ".join(parts)

    @staticmethod
    def _filesystem_reason(path: str, mode: str) -> str:
        """Generate human-readable reason for a filesystem rule."""
        if mode == "read-only":
            return f"NemoClaw: {path} is read-only (Landlock filesystem policy)"
        elif mode == "read-write":
            return f"NemoClaw: {path} is read-write"
        elif mode == "denied":
            return f"NemoClaw: {path} is denied"
        return f"NemoClaw: {path} has access mode {mode}"
