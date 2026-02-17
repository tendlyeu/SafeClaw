"""Full engine - the complete SafeClaw engine with owlready2 + pySHACL."""

import logging
import time

from safeclaw.audit.logger import AuditLogger
from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
    PreferenceApplied,
)
from safeclaw.config import SafeClawConfig
from safeclaw.constraints.action_classifier import ActionClassifier
from safeclaw.constraints.dependency_checker import DependencyChecker
from safeclaw.constraints.message_gate import MessageGate
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.constraints.preference_checker import PreferenceChecker
from safeclaw.constraints.rate_limiter import RateLimiter
from safeclaw.constraints.temporal_checker import TemporalChecker
from safeclaw.engine.context_builder import ContextBuilder
from safeclaw.engine.core import (
    AgentStartEvent,
    ContextResult,
    Decision,
    LlmIOEvent,
    MessageEvent,
    SafeClawEngine,
    ToolCallEvent,
    ToolResultEvent,
)
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.reasoner import OWLReasoner
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker
from safeclaw.engine.session_tracker import SessionTracker
from safeclaw.engine.shacl_validator import SHACLValidator

logger = logging.getLogger("safeclaw.engine")


class FullEngine(SafeClawEngine):
    """Complete engine with owlready2 + pySHACL + RDFLib."""

    def __init__(self, config: SafeClawConfig):
        self.config = config
        self._init_components(config)

    def _init_components(self, config: SafeClawConfig) -> None:
        """Initialize or reinitialize all engine components."""
        ontology_dir = config.get_ontology_dir()
        audit_dir = config.get_audit_dir()

        # Knowledge graph
        self.kg = KnowledgeGraph()
        self.kg.load_directory(ontology_dir)
        logger.info(f"Loaded {len(self.kg)} triples from ontologies")

        # SHACL validator
        self.shacl = SHACLValidator()
        shapes_dir = ontology_dir / "shapes"
        if shapes_dir.exists():
            self.shacl.load_shapes(shapes_dir)

        # OWL reasoner (optional, may fail without Java)
        self.reasoner = OWLReasoner(ontology_dir)
        if config.run_reasoner_on_startup:
            self.reasoner.initialize(run_reasoner=True)

        # Constraint checkers
        self.classifier = ActionClassifier()
        self.policy_checker = PolicyChecker(self.kg)
        self.preference_checker = PreferenceChecker(self.kg)
        self.dependency_checker = DependencyChecker(self.kg)

        # Phase 2: Advanced constraint checkers
        self.derived_checker = DerivedConstraintChecker(self.kg)
        self.temporal_checker = TemporalChecker()
        self.rate_limiter = RateLimiter()

        # Phase 3: Message gate & session tracker
        self.message_gate = MessageGate(self.kg)
        self.session_tracker = SessionTracker()

        # Context builder
        self.context_builder = ContextBuilder(self.kg)

        # Audit
        self.audit = AuditLogger(audit_dir)

    def reload(self) -> None:
        """Hot-reload: re-read ontologies and reinitialize constraint checkers."""
        logger.info("Hot-reloading ontologies...")
        self._init_components(self.config)
        logger.info("Hot-reload complete")

    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
        """Run the full constraint checking pipeline."""
        start = time.monotonic()
        checks: list[ConstraintCheck] = []
        prefs_applied: list[PreferenceApplied] = []

        # 1. Classify action
        action = self.classifier.classify(event.tool_name, event.params)

        # 2. SHACL validation
        shacl_result = self.shacl.validate(action.as_rdf_graph())
        if not shacl_result.conforms:
            reason = f"[SafeClaw] {shacl_result.first_violation_message}"
            checks.append(ConstraintCheck(
                constraint_uri="shacl:validation",
                constraint_type="SHACL",
                result="violated",
                reason=shacl_result.first_violation_message,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        checks.append(ConstraintCheck(
            constraint_uri="shacl:validation",
            constraint_type="SHACL",
            result="satisfied",
            reason="All SHACL shapes conform",
        ))

        # 3. Policy check
        policy_result = self.policy_checker.check(action)
        if policy_result.violated:
            reason = f"[SafeClaw] {policy_result.reason}"
            checks.append(ConstraintCheck(
                constraint_uri=policy_result.policy_uri,
                constraint_type=policy_result.policy_type,
                result="violated",
                reason=policy_result.reason,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        checks.append(ConstraintCheck(
            constraint_uri="policy:check",
            constraint_type="Policy",
            result="satisfied",
            reason="No policy violations",
        ))

        # 4. Preference check
        user_prefs = self.preference_checker.get_preferences(event.user_id)
        pref_result = self.preference_checker.check(action, user_prefs)
        if pref_result.violated:
            reason = f"[SafeClaw] {pref_result.reason}"
            prefs_applied.append(PreferenceApplied(
                preference_uri=pref_result.preference_uri,
                value="true",
                effect=pref_result.reason,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        # 5. Dependency check
        dep_result = self.dependency_checker.check(action, event.session_id)
        if dep_result.unmet:
            reason = f"[SafeClaw] {dep_result.reason}"
            checks.append(ConstraintCheck(
                constraint_uri="dependency:check",
                constraint_type="Dependency",
                result="violated",
                reason=dep_result.reason,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        # 6. Temporal constraint check
        temporal_result = self.temporal_checker.check(action, self.kg)
        if temporal_result.violated:
            reason = f"[SafeClaw] {temporal_result.reason}"
            checks.append(ConstraintCheck(
                constraint_uri="temporal:check",
                constraint_type="Temporal",
                result="violated",
                reason=temporal_result.reason,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        # 7. Rate limit check
        rate_result = self.rate_limiter.check(action, event.session_id)
        if rate_result.exceeded:
            reason = f"[SafeClaw] {rate_result.reason}"
            checks.append(ConstraintCheck(
                constraint_uri="ratelimit:check",
                constraint_type="RateLimit",
                result="violated",
                reason=rate_result.reason,
            ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        # 8. Derived constraint rules (confirmation check)
        derived_result = self.derived_checker.check(
            action, user_prefs, event.session_history
        )
        if derived_result.requires_confirmation:
            reason = f"[SafeClaw] {derived_result.reason}"
            for rule in derived_result.derived_rules:
                checks.append(ConstraintCheck(
                    constraint_uri=f"derived:{rule}",
                    constraint_type="DerivedRule",
                    result="requires_confirmation",
                    reason=derived_result.reason,
                ))
            decision = Decision(block=True, reason=reason)
            self._record_violation_and_log(event, action, decision, checks, prefs_applied, start)
            return decision

        # 9. All checks passed
        decision = Decision(block=False)
        self._log_decision(event, action, decision, checks, prefs_applied, start)

        # Record action in session history for dependency tracking
        self.dependency_checker.record_action(event.session_id, action.ontology_class)
        # Record action for rate limiting
        self.rate_limiter.record(action, event.session_id)

        return decision

    async def evaluate_message(self, event: MessageEvent) -> Decision:
        start = time.monotonic()

        # Phase 3: Message gate checks (content policies, never-contact, rate limiting)
        gate_result = self.message_gate.check(
            to=event.to,
            content=event.content,
            session_id=event.session_id,
        )
        if gate_result.block:
            decision = Decision(
                block=True,
                reason=f"[SafeClaw] {gate_result.reason}",
            )
            self._log_message_decision(event, decision, start)
            return decision

        # User preference: confirm before send
        user_prefs = self.preference_checker.get_preferences(event.user_id)
        if user_prefs.confirm_before_send:
            decision = Decision(
                block=True,
                reason="[SafeClaw] User preference requires confirmation before sending messages",
            )
            self._log_message_decision(event, decision, start)
            return decision

        # Record for rate limiting
        self.message_gate.record_message(event.session_id)

        decision = Decision(block=False)
        self._log_message_decision(event, decision, start)
        return decision

    def _log_message_decision(
        self, event: MessageEvent, decision: Decision, start_time: float
    ) -> None:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        record = DecisionRecord(
            session_id=event.session_id,
            user_id=event.user_id,
            action=ActionDetail(
                tool_name="message",
                params={"to": event.to, "content_length": len(event.content)},
                ontology_class="SendMessage",
                risk_level="HighRisk",
                is_reversible=False,
                affects_scope="ExternalWorld",
            ),
            decision="blocked" if decision.block else "allowed",
            justification=Justification(elapsed_ms=elapsed_ms),
        )
        decision.audit_id = record.id
        self.audit.log(record)

    async def build_context(self, event: AgentStartEvent) -> ContextResult:
        # Get session summary from tracker
        session_summary = self.session_tracker.get_session_summary(event.session_id)
        context = self.context_builder.build_context(
            event.user_id,
            session_id=event.session_id,
            session_history=session_summary or None,
        )
        return ContextResult(prepend_context=context)

    async def record_action_result(self, event: ToolResultEvent) -> None:
        action = self.classifier.classify(event.tool_name, event.params)

        # Record in session tracker (Phase 3: KG feedback loop)
        self.session_tracker.record_outcome(
            session_id=event.session_id,
            action_class=action.ontology_class,
            tool_name=event.tool_name,
            success=event.success,
            params=event.params,
        )

        # Record successful actions in dependency tracker
        if event.success:
            self.dependency_checker.record_action(event.session_id, action.ontology_class)

    async def log_llm_io(self, event: LlmIOEvent) -> None:
        logger.debug(f"LLM {event.direction}: {event.content[:100]}...")

    def _record_violation_and_log(
        self,
        event: ToolCallEvent,
        action,
        decision: Decision,
        checks: list[ConstraintCheck],
        prefs_applied: list[PreferenceApplied],
        start_time: float,
    ) -> None:
        """Log decision and record the violation for context injection."""
        self.context_builder.record_violation(event.session_id, decision.reason)
        self.session_tracker.record_violation(event.session_id, decision.reason)
        self._log_decision(event, action, decision, checks, prefs_applied, start_time)

    def _log_decision(
        self,
        event: ToolCallEvent,
        action,
        decision: Decision,
        checks: list[ConstraintCheck],
        prefs_applied: list[PreferenceApplied],
        start_time: float,
    ) -> None:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        record = DecisionRecord(
            session_id=event.session_id,
            user_id=event.user_id,
            action=ActionDetail(
                tool_name=event.tool_name,
                params=event.params,
                ontology_class=action.ontology_class,
                risk_level=action.risk_level,
                is_reversible=action.is_reversible,
                affects_scope=action.affects_scope,
            ),
            decision="blocked" if decision.block else "allowed",
            justification=Justification(
                constraints_checked=checks,
                preferences_applied=prefs_applied,
                elapsed_ms=elapsed_ms,
            ),
            session_action_history=event.session_history,
        )
        decision.audit_id = record.id
        self.audit.log(record)
