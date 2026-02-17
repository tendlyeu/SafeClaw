"""Audit reporter - generates reports from audit logs in multiple formats."""

import csv
import io
import json
from datetime import datetime, timezone

from safeclaw.audit.logger import AuditLogger
from safeclaw.audit.models import DecisionRecord


class AuditReporter:
    """Generates structured audit reports in markdown, JSON, and CSV formats."""

    def __init__(self, audit_logger: AuditLogger):
        self.logger = audit_logger

    def generate_session_report(self, session_id: str, format: str = "markdown") -> str:
        """Generate a session report in the specified format."""
        records = self.logger.get_session_records(session_id)
        if not records:
            return f"No audit records found for session {session_id}"

        if format == "json":
            return self._to_json(records, session_id)
        elif format == "csv":
            return self._to_csv(records)
        else:
            return self._to_markdown(records, session_id)

    def generate_compliance_report(self, records: list[DecisionRecord]) -> str:
        """Generate a structured compliance report suitable for SOC 2 / ISO 27001 review."""
        if not records:
            return "No records for compliance report."

        lines = [
            "# SafeClaw Compliance Report",
            f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
            f"**Total decisions**: {len(records)}",
            "",
            "## Summary Statistics",
            "",
            f"- Allowed: {sum(1 for r in records if r.decision == 'allowed')}",
            f"- Blocked: {sum(1 for r in records if r.decision == 'blocked')}",
            "",
        ]

        # Risk distribution
        risk_counts: dict[str, int] = {}
        for r in records:
            risk_counts[r.action.risk_level] = risk_counts.get(r.action.risk_level, 0) + 1
        lines.append("## Risk Distribution")
        lines.append("")
        for risk, count in sorted(risk_counts.items()):
            lines.append(f"- {risk}: {count}")
        lines.append("")

        # Constraint violations
        violations: dict[str, int] = {}
        for r in records:
            if r.decision == "blocked":
                for check in r.justification.constraints_checked:
                    if check.result == "violated":
                        violations[check.constraint_uri] = violations.get(check.constraint_uri, 0) + 1
        if violations:
            lines.append("## Most Violated Constraints")
            lines.append("")
            for uri, count in sorted(violations.items(), key=lambda x: -x[1]):
                lines.append(f"- {uri}: {count} violations")
            lines.append("")

        # Decision trace
        lines.append("## Decision Trace")
        lines.append("")
        lines.append("| Timestamp | Session | User | Tool | Action Class | Decision | Constraint | Reason |")
        lines.append("|-----------|---------|------|------|-------------|----------|------------|--------|")
        for r in records:
            constraint = ""
            reason = ""
            if r.decision == "blocked":
                for check in r.justification.constraints_checked:
                    if check.result in ("violated", "requires_confirmation"):
                        constraint = check.constraint_uri
                        reason = check.reason[:40]
                        break
                if not constraint:
                    for pref in r.justification.preferences_applied:
                        constraint = pref.preference_uri
                        reason = pref.effect[:40]
                        break
            lines.append(
                f"| {r.timestamp[:19]} | {r.session_id[:8]} | {r.user_id} | "
                f"{r.action.tool_name} | {r.action.ontology_class} | {r.decision} | "
                f"{constraint} | {reason} |"
            )
        lines.append("")

        return "\n".join(lines)

    def get_statistics(self, records: list[DecisionRecord]) -> dict:
        """Compute aggregate statistics from audit records."""
        if not records:
            return {"total": 0}

        total = len(records)
        allowed = sum(1 for r in records if r.decision == "allowed")
        blocked = total - allowed

        risk_dist: dict[str, int] = {}
        tool_dist: dict[str, int] = {}
        constraint_violations: dict[str, int] = {}

        for r in records:
            risk_dist[r.action.risk_level] = risk_dist.get(r.action.risk_level, 0) + 1
            tool_dist[r.action.tool_name] = tool_dist.get(r.action.tool_name, 0) + 1
            if r.decision == "blocked":
                for check in r.justification.constraints_checked:
                    if check.result in ("violated", "requires_confirmation"):
                        constraint_violations[check.constraint_uri] = (
                            constraint_violations.get(check.constraint_uri, 0) + 1
                        )

        avg_latency = (
            sum(r.justification.elapsed_ms for r in records) / total if total else 0
        )

        return {
            "total": total,
            "allowed": allowed,
            "blocked": blocked,
            "block_rate": round(blocked / total * 100, 1) if total else 0,
            "risk_distribution": risk_dist,
            "tool_distribution": tool_dist,
            "top_violated_constraints": dict(
                sorted(constraint_violations.items(), key=lambda x: -x[1])[:10]
            ),
            "avg_latency_ms": round(avg_latency, 2),
        }

    def _to_markdown(self, records: list[DecisionRecord], session_id: str) -> str:
        lines = [
            f"# SafeClaw Audit Report - Session {session_id}",
            "",
            f"**Total decisions**: {len(records)}",
            f"**Allowed**: {sum(1 for r in records if r.decision == 'allowed')}",
            f"**Blocked**: {sum(1 for r in records if r.decision == 'blocked')}",
            "",
            "## Decisions",
            "",
        ]

        for record in records:
            status = "ALLOWED" if record.decision == "allowed" else "BLOCKED"
            lines.append(f"### [{status}] {record.action.tool_name}")
            lines.append(f"- **Time**: {record.timestamp}")
            lines.append(f"- **Action class**: {record.action.ontology_class}")
            lines.append(f"- **Risk level**: {record.action.risk_level}")
            lines.append(f"- **Latency**: {record.justification.elapsed_ms:.1f}ms")
            if record.decision == "blocked":
                for check in record.justification.constraints_checked:
                    if check.result in ("violated", "requires_confirmation"):
                        lines.append(f"- **Violation**: [{check.constraint_type}] {check.reason}")
                for pref in record.justification.preferences_applied:
                    lines.append(f"- **Preference**: {pref.effect}")
            lines.append("")

        return "\n".join(lines)

    def _to_json(self, records: list[DecisionRecord], session_id: str) -> str:
        return json.dumps(
            {
                "session_id": session_id,
                "total": len(records),
                "allowed": sum(1 for r in records if r.decision == "allowed"),
                "blocked": sum(1 for r in records if r.decision == "blocked"),
                "decisions": [r.model_dump() for r in records],
            },
            indent=2,
            default=str,
        )

    def _to_csv(self, records: list[DecisionRecord]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp", "session_id", "user_id", "tool_name",
            "ontology_class", "risk_level", "decision", "reason", "latency_ms",
        ])
        for r in records:
            reason = ""
            for check in r.justification.constraints_checked:
                if check.result in ("violated", "requires_confirmation"):
                    reason = check.reason
                    break
            if not reason:
                for pref in r.justification.preferences_applied:
                    reason = pref.effect
                    break
            writer.writerow([
                r.timestamp, r.session_id, r.user_id,
                r.action.tool_name, r.action.ontology_class,
                r.action.risk_level, r.decision, reason,
                f"{r.justification.elapsed_ms:.1f}",
            ])
        return output.getvalue()
