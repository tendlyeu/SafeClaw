"""Phase 4 tests: audit reporter formats, statistics, graph builder, compliance."""

import json
from pathlib import Path

import pytest

from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
    PreferenceApplied,
)
from safeclaw.audit.reporter import AuditReporter
from safeclaw.engine.graph_builder import GraphBuilder
from safeclaw.engine.knowledge_graph import KnowledgeGraph


# --- Fixtures ---


@pytest.fixture
def kg():
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


@pytest.fixture
def sample_records():
    """Create sample audit records for testing."""
    return [
        DecisionRecord(
            id="r1",
            session_id="s1",
            user_id="default",
            action=ActionDetail(
                tool_name="read",
                params={"file_path": "/src/main.py"},
                ontology_class="ReadFile",
                risk_level="LowRisk",
                is_reversible=True,
                affects_scope="LocalOnly",
            ),
            decision="allowed",
            justification=Justification(elapsed_ms=1.5),
        ),
        DecisionRecord(
            id="r2",
            session_id="s1",
            user_id="default",
            action=ActionDetail(
                tool_name="exec",
                params={"command": "git push --force"},
                ontology_class="ForcePush",
                risk_level="CriticalRisk",
                is_reversible=False,
                affects_scope="SharedState",
            ),
            decision="blocked",
            justification=Justification(
                constraints_checked=[
                    ConstraintCheck(
                        constraint_uri="sp:NoForcePush",
                        constraint_type="Prohibition",
                        result="violated",
                        reason="Force push can destroy shared history",
                    )
                ],
                elapsed_ms=2.3,
            ),
        ),
        DecisionRecord(
            id="r3",
            session_id="s1",
            user_id="default",
            action=ActionDetail(
                tool_name="exec",
                params={"command": "rm -rf /tmp/old"},
                ontology_class="DeleteFile",
                risk_level="CriticalRisk",
                is_reversible=False,
                affects_scope="LocalOnly",
            ),
            decision="blocked",
            justification=Justification(
                preferences_applied=[
                    PreferenceApplied(
                        preference_uri="su:confirmBeforeDelete",
                        value="true",
                        effect="User preference requires confirmation before file deletion",
                    )
                ],
                elapsed_ms=1.1,
            ),
        ),
    ]


# --- Reporter Tests ---


class TestAuditReporter:
    def test_markdown_report(self, tmp_path, sample_records):
        from safeclaw.audit.logger import AuditLogger

        logger = AuditLogger(tmp_path)
        for r in sample_records:
            logger.log(r)
        reporter = AuditReporter(logger)
        report = reporter.generate_session_report("s1", format="markdown")
        assert "# SafeClaw Audit Report" in report
        assert "**Total decisions**: 3" in report
        assert "**Allowed**: 1" in report
        assert "**Blocked**: 2" in report
        assert "ForcePush" in report

    def test_json_report(self, tmp_path, sample_records):
        from safeclaw.audit.logger import AuditLogger

        logger = AuditLogger(tmp_path)
        for r in sample_records:
            logger.log(r)
        reporter = AuditReporter(logger)
        report = reporter.generate_session_report("s1", format="json")
        data = json.loads(report)
        assert data["session_id"] == "s1"
        assert data["total"] == 3
        assert data["allowed"] == 1
        assert data["blocked"] == 2
        assert len(data["decisions"]) == 3

    def test_csv_report(self, tmp_path, sample_records):
        from safeclaw.audit.logger import AuditLogger

        logger = AuditLogger(tmp_path)
        for r in sample_records:
            logger.log(r)
        reporter = AuditReporter(logger)
        report = reporter.generate_session_report("s1", format="csv")
        lines = report.strip().split("\n")
        assert lines[0].startswith("timestamp")  # header
        assert len(lines) == 4  # header + 3 records
        assert "ForcePush" in report
        assert "blocked" in report.lower()

    def test_no_records(self, tmp_path):
        from safeclaw.audit.logger import AuditLogger

        logger = AuditLogger(tmp_path)
        reporter = AuditReporter(logger)
        report = reporter.generate_session_report("unknown")
        assert "No audit records found" in report

    def test_statistics(self, tmp_path, sample_records):
        from safeclaw.audit.logger import AuditLogger

        reporter = AuditReporter(AuditLogger(tmp_path))
        stats = reporter.get_statistics(sample_records)
        assert stats["total"] == 3
        assert stats["allowed"] == 1
        assert stats["blocked"] == 2
        assert stats["block_rate"] == pytest.approx(66.7, abs=0.1)
        assert "CriticalRisk" in stats["risk_distribution"]
        assert stats["risk_distribution"]["CriticalRisk"] == 2
        assert "sp:NoForcePush" in stats["top_violated_constraints"]

    def test_empty_statistics(self, tmp_path):
        from safeclaw.audit.logger import AuditLogger

        reporter = AuditReporter(AuditLogger(tmp_path))
        stats = reporter.get_statistics([])
        assert stats["total"] == 0

    def test_compliance_report(self, tmp_path, sample_records):
        from safeclaw.audit.logger import AuditLogger

        reporter = AuditReporter(AuditLogger(tmp_path))
        report = reporter.generate_compliance_report(sample_records)
        assert "# SafeClaw Compliance Report" in report
        assert "## Summary Statistics" in report
        assert "## Risk Distribution" in report
        assert "## Decision Trace" in report
        assert "CriticalRisk" in report

    def test_compliance_report_empty(self, tmp_path):
        from safeclaw.audit.logger import AuditLogger

        reporter = AuditReporter(AuditLogger(tmp_path))
        report = reporter.generate_compliance_report([])
        assert "No records" in report


# --- GraphBuilder Tests ---


class TestGraphBuilder:
    def test_build_graph(self, kg):
        builder = GraphBuilder(kg)
        graph = builder.build_graph()
        assert "nodes" in graph
        assert "edges" in graph
        assert "stats" in graph
        assert graph["stats"]["total_triples"] > 0
        assert len(graph["nodes"]) > 0

    def test_graph_has_policy_nodes(self, kg):
        builder = GraphBuilder(kg)
        graph = builder.build_graph()
        policy_nodes = [n for n in graph["nodes"] if n["type"] == "policy"]
        assert len(policy_nodes) > 0

    def test_graph_has_class_nodes(self, kg):
        builder = GraphBuilder(kg)
        graph = builder.build_graph()
        class_nodes = [n for n in graph["nodes"] if n["type"] == "class"]
        assert len(class_nodes) > 0

    def test_search_nodes(self, kg):
        builder = GraphBuilder(kg)
        results = builder.search_nodes("Prohibition")
        assert len(results) > 0
        assert any("Prohibition" in r["name"] for r in results)

    def test_search_no_results(self, kg):
        builder = GraphBuilder(kg)
        results = builder.search_nodes("NonExistentXYZ123")
        assert results == []
