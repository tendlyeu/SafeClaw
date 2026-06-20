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

    def __init__(self, policy_dir: Path, workdir: str | None = None):
        """Create a loader.

        ``workdir`` is the resolved NemoClaw sandbox workdir/home path used to
        materialise the implicit read-write rule when a filesystem policy sets
        ``include_workdir: true``. The schema only provides the boolean, never
        the resolved path, so it must be supplied by the caller (runtime config
        / policy context). When ``None``, ``include_workdir`` cannot be honored
        safely and is skipped.
        """
        self.policy_dir = policy_dir
        self.workdir = workdir

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
                logger.warning(
                    "Unexpected YAML structure in %s (expected mapping)",
                    yaml_file.name,
                )
                continue

            self._process_policy(kg, data, yaml_file.name)

    # ------------------------------------------------------------------
    # Format detection and dispatch
    # ------------------------------------------------------------------

    def _process_policy(self, kg: KnowledgeGraph, data: dict, filename: str) -> None:
        """Process a single parsed YAML policy document.

        Detects the real NemoClaw format (``network_policies`` /
        ``filesystem_policy``) vs. the legacy flat format (``rules`` /
        ``filesystem``) and dispatches accordingly.
        """
        if "network_policies" in data or "filesystem_policy" in data:
            self._process_real_format(kg, data, filename)
        else:
            self._process_legacy_format(kg, data, filename)

    # ------------------------------------------------------------------
    # Real NemoClaw format
    # ------------------------------------------------------------------

    def _process_real_format(self, kg: KnowledgeGraph, data: dict, filename: str) -> None:
        """Process real NemoClaw YAML (network_policies + filesystem_policy)."""
        network_policies = data.get("network_policies")
        if isinstance(network_policies, dict):
            for group_name, group in network_policies.items():
                if not isinstance(group, dict):
                    logger.warning(
                        "Skipping non-dict network group %r in %s",
                        group_name,
                        filename,
                    )
                    continue
                self._process_network_group(kg, group_name, group)

        fs_policy = data.get("filesystem_policy")
        if isinstance(fs_policy, dict):
            self._process_real_filesystem(kg, fs_policy)

    def _process_network_group(
        self,
        kg: KnowledgeGraph,
        group_name: str,
        group: dict,
    ) -> None:
        """Process a single named network_policies group."""
        endpoints = group.get("endpoints")
        if not isinstance(endpoints, list):
            return

        binaries = group.get("binaries", [])
        binary_paths: list[str] = []
        if isinstance(binaries, list):
            for b in binaries:
                if isinstance(b, dict) and b.get("path"):
                    binary_paths.append(str(b["path"]))

        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            self._process_real_endpoint(kg, group_name, endpoint, binary_paths)

    def _process_real_endpoint(
        self,
        kg: KnowledgeGraph,
        group_name: str,
        endpoint: dict,
        binary_paths: list[str],
    ) -> None:
        """Convert a single endpoint from the real format to RDF triples."""
        host = endpoint.get("host")
        if not host:
            return

        port = endpoint.get("port")
        protocol = endpoint.get("protocol", "")
        enforcement = endpoint.get("enforcement", "")
        tls = endpoint.get("tls", "")
        # NemoClaw v0.0.65: `access: full` is a separate field (enum ["full"])
        # meaning "no L7 path filtering", NOT a protocol. It is independent of
        # the `protocol` field (rest|websocket).
        access = endpoint.get("access", "")
        allowed_ips = endpoint.get("allowed_ips")
        ws_cred_rewrite = endpoint.get("websocket_credential_rewrite")
        body_cred_rewrite = endpoint.get("request_body_credential_rewrite")

        rule_node = SP[f"nemo_net_{uuid4().hex}"]
        kg.add_triple(rule_node, RDF.type, SP.NemoNetworkRule)
        kg.add_triple(
            rule_node,
            SP.allowsHost,
            Literal(host, datatype=XSD.string),
        )
        kg.add_triple(
            rule_node,
            SP.source,
            Literal("nemoclaw", datatype=XSD.string),
        )
        kg.add_triple(
            rule_node,
            SP.policyGroup,
            Literal(group_name, datatype=XSD.string),
        )

        if port is not None:
            kg.add_triple(
                rule_node,
                SP.allowsPort,
                Literal(int(port), datatype=XSD.integer),
            )

        if protocol:
            kg.add_triple(
                rule_node,
                SP.allowsProtocol,
                Literal(protocol, datatype=XSD.string),
            )

        if enforcement:
            kg.add_triple(
                rule_node,
                SP.enforcement,
                Literal(enforcement, datatype=XSD.string),
            )

        if tls:
            kg.add_triple(
                rule_node,
                SP.tlsMode,
                Literal(tls, datatype=XSD.string),
            )

        if access:
            kg.add_triple(
                rule_node,
                SP.networkAccessMode,
                Literal(access, datatype=XSD.string),
            )

        if isinstance(allowed_ips, list):
            for ip in allowed_ips:
                if isinstance(ip, str) and ip:
                    kg.add_triple(
                        rule_node,
                        SP.allowedIp,
                        Literal(ip, datatype=XSD.string),
                    )

        if ws_cred_rewrite is not None:
            kg.add_triple(
                rule_node,
                SP.websocketCredentialRewrite,
                Literal(bool(ws_cred_rewrite), datatype=XSD.boolean),
            )

        if body_cred_rewrite is not None:
            kg.add_triple(
                rule_node,
                SP.requestBodyCredentialRewrite,
                Literal(bool(body_cred_rewrite), datatype=XSD.boolean),
            )

        # `access: full` + `tls: skip` = raw L4 tunnel: no L7 path filtering and
        # no TLS interception. Flag for elevated scrutiny (#327/#329).
        if access == "full" and tls == "skip":
            kg.add_triple(
                rule_node,
                SP.rawTunnel,
                Literal(True, datatype=XSD.boolean),
            )

        for bp in binary_paths:
            kg.add_triple(
                rule_node,
                SP.binaryRestriction,
                Literal(bp, datatype=XSD.string),
            )

        # L7 allow rules (method + path glob). Each endpoint may declare
        # `rules: [{ allow: { method, path } }]`. Persist each rule as its own
        # node so method and path stay grouped per rule. `access: full`
        # endpoints carry no L7 path filtering, so rules are not expected there.
        self._process_endpoint_allow_rules(kg, rule_node, endpoint.get("rules"))

        reason = self._network_reason(host, port, protocol)
        kg.add_triple(
            rule_node,
            SP.reason,
            Literal(reason, datatype=XSD.string),
        )

    def _process_endpoint_allow_rules(
        self,
        kg: KnowledgeGraph,
        rule_node,
        rules,
    ) -> None:
        """Persist an endpoint's L7 allow rules (method + path glob) as RDF.

        Each entry has the shape ``{ allow: { method, path } }`` per the
        NemoClaw v0.0.65 schema. Each allow rule becomes its own
        ``sp:NemoAllowRule`` node linked to the endpoint via ``sp:allowsRule``,
        so method and path remain grouped per rule. Malformed entries (missing
        ``allow`` or ``path``) are skipped.
        """
        if not isinstance(rules, list):
            return

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            allow = rule.get("allow")
            if not isinstance(allow, dict):
                continue
            path = allow.get("path")
            if not isinstance(path, str) or not path:
                continue
            method = allow.get("method")

            allow_node = SP[f"nemo_allow_{uuid4().hex}"]
            kg.add_triple(allow_node, RDF.type, SP.NemoAllowRule)
            kg.add_triple(rule_node, SP.allowsRule, allow_node)
            kg.add_triple(
                allow_node,
                SP.allowsPathGlob,
                Literal(path, datatype=XSD.string),
            )
            if isinstance(method, str) and method:
                kg.add_triple(
                    allow_node,
                    SP.allowsMethod,
                    Literal(method, datatype=XSD.string),
                )

    def _process_real_filesystem(self, kg: KnowledgeGraph, fs_policy: dict) -> None:
        """Process real NemoClaw filesystem_policy section."""
        # include_workdir: true makes the sandbox workdir/home writable. The
        # schema only gives the boolean, not the resolved path, so we emit the
        # implicit read-write rule only when a workdir was supplied to the
        # loader. Without one we cannot safely guess a path, so we skip it.
        if fs_policy.get("include_workdir") is True:
            if self.workdir:
                self._process_filesystem_rule(kg, {"path": self.workdir, "mode": "read-write"})
            else:
                logger.warning(
                    "filesystem_policy.include_workdir is true but no NemoClaw "
                    "workdir is configured; skipping the implicit read-write "
                    "rule. Set the resolved sandbox workdir to honor it."
                )

        read_only = fs_policy.get("read_only", [])
        if isinstance(read_only, list):
            for path in read_only:
                if isinstance(path, str) and path:
                    self._process_filesystem_rule(kg, {"path": path, "mode": "read-only"})

        read_write = fs_policy.get("read_write", [])
        if isinstance(read_write, list):
            for path in read_write:
                if isinstance(path, str) and path:
                    self._process_filesystem_rule(kg, {"path": path, "mode": "read-write"})

    # ------------------------------------------------------------------
    # Legacy format (backward compatibility)
    # ------------------------------------------------------------------

    def _process_legacy_format(self, kg: KnowledgeGraph, data: dict, filename: str) -> None:
        """Process the legacy flat YAML format (rules / filesystem / fs_rules)."""
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
        """Convert a single legacy network rule dict to RDF triples."""
        host = rule.get("host")
        if not host:
            return

        if rule.get("allow") is False or rule.get("deny") is True:
            return

        port = rule.get("port")
        protocol = rule.get("protocol", "")

        rule_node = SP[f"nemo_net_{uuid4().hex}"]
        kg.add_triple(rule_node, RDF.type, SP.NemoNetworkRule)
        kg.add_triple(
            rule_node,
            SP.allowsHost,
            Literal(host, datatype=XSD.string),
        )
        kg.add_triple(
            rule_node,
            SP.source,
            Literal("nemoclaw", datatype=XSD.string),
        )

        if port is not None:
            kg.add_triple(
                rule_node,
                SP.allowsPort,
                Literal(int(port), datatype=XSD.integer),
            )

        if protocol:
            kg.add_triple(
                rule_node,
                SP.allowsProtocol,
                Literal(protocol, datatype=XSD.string),
            )

        binary = rule.get("binary")
        if binary:
            kg.add_triple(
                rule_node,
                SP.binaryRestriction,
                Literal(binary, datatype=XSD.string),
            )

        self._process_endpoint_allow_rules(kg, rule_node, rule.get("rules"))

        reason = self._network_reason(host, port, protocol)
        kg.add_triple(
            rule_node,
            SP.reason,
            Literal(reason, datatype=XSD.string),
        )

    def _process_filesystem_rule(self, kg: KnowledgeGraph, rule: dict) -> None:
        """Convert a single filesystem rule dict to RDF triples."""
        path = rule.get("path")
        if not path:
            return

        mode = rule.get("mode") or rule.get("access") or rule.get("accessMode")
        if not mode:
            return

        mode_lower = mode.lower().replace("_", "-")
        if mode_lower not in ("read-only", "read-write", "denied"):
            logger.warning("Unknown filesystem access mode: %s for path %s", mode, path)
            return

        rule_node = SP[f"nemo_fs_{uuid4().hex}"]
        kg.add_triple(rule_node, RDF.type, SP.NemoFilesystemRule)
        kg.add_triple(rule_node, SP.path, Literal(path, datatype=XSD.string))
        kg.add_triple(
            rule_node,
            SP.accessMode,
            Literal(mode_lower, datatype=XSD.string),
        )
        kg.add_triple(
            rule_node,
            SP.source,
            Literal("nemoclaw", datatype=XSD.string),
        )

        reason = self._filesystem_reason(path, mode_lower)
        kg.add_triple(
            rule_node,
            SP.reason,
            Literal(reason, datatype=XSD.string),
        )

    # ------------------------------------------------------------------
    # Reason generation helpers
    # ------------------------------------------------------------------

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
