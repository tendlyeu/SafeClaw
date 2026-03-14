"""Full engine - the complete SafeClaw engine with pySHACL + RDFLib."""

import asyncio
import json
import logging
import time
from collections import OrderedDict

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
from safeclaw.engine.agent_registry import AgentRegistry
from safeclaw.engine.event_bus import EventBus, SafeClawEvent
from safeclaw.engine.delegation_detector import DelegationDetector
from safeclaw.engine.class_hierarchy import ClassHierarchy
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.ontology_validator import OntologyValidator
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker
from safeclaw.engine.roles import RoleManager
from safeclaw.engine.session_tracker import SessionTracker
from safeclaw.engine.shacl_validator import SHACLValidator
from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor
from safeclaw.engine.temp_permissions import TempPermissionManager

logger = logging.getLogger("safeclaw.engine")

_PATH_PARAM_KEYS = (
    "file_path", "path", "filepath", "filename", "dest", "destination",
    "target", "source", "src", "dir", "directory", "folder",
)


class FullEngine(SafeClawEngine):
    """Complete engine with pySHACL + RDFLib + ClassHierarchy."""

    @staticmethod
    def _extract_resource_paths(params: dict) -> list[str]:
        """Extract all resource paths from params, checking common key variants."""
        paths = []
        for key in _PATH_PARAM_KEYS:
            val = params.get(key, "")
            if val and isinstance(val, str):
                paths.append(val)
        return paths

    def __init__(self, config: SafeClawConfig, api_key_manager=None):
        self.config = config
        self.api_key_manager = api_key_manager
        self.event_bus = EventBus()
        # BUG-001/075/076: Lock to prevent concurrent reloads
        self._reload_lock = asyncio.Lock()
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

        # Class hierarchy (pure-Python replacement for Java OWL reasoner)
        self.hierarchy = ClassHierarchy(self.kg)

        # Ontology consistency validation (advisory)
        validator = OntologyValidator(self.kg, self.hierarchy)
        for warning in validator.validate():
            logger.warning("Ontology: %s", warning)

        # Constraint checkers
        self.classifier = ActionClassifier(hierarchy=self.hierarchy)
        self.policy_checker = PolicyChecker(self.kg, hierarchy=self.hierarchy)
        self.preference_checker = PreferenceChecker(self.kg)
        self.dependency_checker = DependencyChecker(self.kg, hierarchy=self.hierarchy)

        # Phase 2: Advanced constraint checkers
        self.derived_checker = DerivedConstraintChecker(self.kg, hierarchy=self.hierarchy)
        self.temporal_checker = TemporalChecker()
        self.rate_limiter = RateLimiter()

        # Phase 3: Message gate & session tracker
        self.message_gate = MessageGate(self.kg)
        self.session_tracker = SessionTracker()

        # Context builder
        self.context_builder = ContextBuilder(self.kg)

        # Multi-agent governance (Phase: multi-agent)
        self.agent_registry = AgentRegistry()
        try:
            raw = config.raw
        except (json.JSONDecodeError, AttributeError, OSError, UnicodeDecodeError):
            logger.warning("Malformed or missing config.raw, falling back to defaults")
            raw = {}
        self.role_manager = RoleManager(raw, hierarchy=self.hierarchy, knowledge_graph=self.kg)
        self.delegation_detector = DelegationDetector(
            mode=raw.get("agents", {}).get("delegationPolicy", "configurable")
            if raw
            else "configurable"
        )
        self.temp_permissions = TempPermissionManager(hierarchy=self.hierarchy)
        self.heartbeat_monitor = HeartbeatMonitor(self.event_bus)
        self._require_token_auth = (
            raw.get("agents", {}).get("requireTokenAuth", False) if raw else False
        )

        # Per-session locks for TOCTOU prevention (bounded)
        self._session_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._max_session_locks = 10000

        # Audit
        self.audit = AuditLogger(audit_dir)

        # LLM layer (passive observer — gated on API key)
        self.llm_client = None
        self.security_reviewer = None
        self.classification_observer = None
        self.explainer = None

        if config.mistral_api_key:
            from safeclaw.llm.client import create_client
            from safeclaw.llm.security_reviewer import SecurityReviewer
            from safeclaw.llm.classification_observer import ClassificationObserver
            from safeclaw.llm.explainer import DecisionExplainer

            self.llm_client = create_client(config)
            if self.llm_client:
                suggestions_path = config.data_dir / "llm" / "classification_suggestions.jsonl"
                self.security_reviewer = SecurityReviewer(self.llm_client, self)
                self.classification_observer = ClassificationObserver(
                    self.llm_client, suggestions_path
                )
                self.explainer = DecisionExplainer(self.llm_client)
                logger.info("LLM layer initialized (security review, observer, explainer)")

        # Per-user LLM client cache (bounded LRU, keyed by Mistral API key)
        self._user_llm_clients: OrderedDict = OrderedDict()
        self._max_user_llm_clients = 500

    def get_llm_client_for_user(self, user_id: str):
        """Get LLM client for a specific user, falling back to global client.

        Looks up the user's Mistral key from the shared DB, caches clients by key.
        """
        if self.api_key_manager is None or not hasattr(
            self.api_key_manager, "get_user_mistral_key"
        ):
            return self.llm_client  # Fall back to global

        user_key = self.api_key_manager.get_user_mistral_key(user_id)
        if not user_key:
            return self.llm_client  # Fall back to global

        # Check cache (move to end for LRU)
        if user_key in self._user_llm_clients:
            self._user_llm_clients.move_to_end(user_key)
            return self._user_llm_clients[user_key]

        # Create new client for this key
        from safeclaw.llm.client import SafeClawLLMClient

        try:
            from mistralai import Mistral

            mistral = Mistral(api_key=user_key)
            client = SafeClawLLMClient(
                mistral_client=mistral,
                model=self.config.mistral_model,
                model_large=self.config.mistral_model_large,
                timeout_ms=self.config.mistral_timeout_ms,
            )
            self._user_llm_clients[user_key] = client
            # Evict oldest if over limit
            while len(self._user_llm_clients) > self._max_user_llm_clients:
                self._user_llm_clients.popitem(last=False)
            return client
        except Exception:
            logger.warning("Failed to create per-user Mistral client for user %s", user_id)
            return self.llm_client

    def _reload_kg_components(self) -> None:
        """Reinitialize only KG-dependent components, preserving runtime state.

        BUG-001/075/076: reload() previously called _init_components() which
        reset session locks, session tracker, rate limiter, and other runtime
        state. This method only reinitializes components that depend on the
        knowledge graph, preserving per-session state across hot-reloads.

        All new components are built first, then swapped in atomically to avoid
        concurrent evaluations seeing a mix of old and new checkers.
        """
        ontology_dir = self.config.get_ontology_dir()

        # Build all new components into local variables first
        new_kg = KnowledgeGraph()
        new_kg.load_directory(ontology_dir)
        logger.info(f"Loaded {len(new_kg)} triples from ontologies")

        new_shacl = SHACLValidator()
        shapes_dir = ontology_dir / "shapes"
        if shapes_dir.exists():
            new_shacl.load_shapes(shapes_dir)

        new_hierarchy = ClassHierarchy(new_kg)

        # Ontology consistency validation (advisory)
        validator = OntologyValidator(new_kg, new_hierarchy)
        for warning in validator.validate():
            logger.warning("Ontology: %s", warning)

        new_classifier = ActionClassifier(hierarchy=new_hierarchy)
        new_policy_checker = PolicyChecker(new_kg, hierarchy=new_hierarchy)
        new_preference_checker = PreferenceChecker(new_kg)

        # Preserve dependency checker session history across reloads (#92)
        old_dep_history = getattr(self.dependency_checker, '_session_history', {})
        new_dependency_checker = DependencyChecker(new_kg, hierarchy=new_hierarchy)
        new_dependency_checker._session_history = old_dep_history

        new_derived_checker = DerivedConstraintChecker(new_kg, hierarchy=new_hierarchy)
        new_message_gate = MessageGate(new_kg)
        new_context_builder = ContextBuilder(new_kg)

        # Preserve context builder violation history across reloads
        new_context_builder._violation_history = self.context_builder._violation_history

        try:
            raw = self.config.raw
        except (json.JSONDecodeError, AttributeError, OSError, UnicodeDecodeError):
            raw = {}
        new_role_manager = RoleManager(raw, hierarchy=new_hierarchy, knowledge_graph=new_kg)

        # Swap all components atomically — concurrent evaluations will see
        # either all-old or all-new, never a mix
        self.kg = new_kg
        self.shacl = new_shacl
        self.hierarchy = new_hierarchy
        self.classifier = new_classifier
        self.policy_checker = new_policy_checker
        self.preference_checker = new_preference_checker
        self.dependency_checker = new_dependency_checker
        self.derived_checker = new_derived_checker
        self.message_gate = new_message_gate
        self.context_builder = new_context_builder
        self.role_manager = new_role_manager

        # Update temp_permissions hierarchy reference (preserve active grants)
        self.temp_permissions._hierarchy = new_hierarchy

    async def reload(self) -> None:
        """Hot-reload: re-read ontologies and reinitialize KG-dependent components.

        BUG-001/075/076: Uses an asyncio.Lock to prevent concurrent reloads,
        and only reinitializes KG-dependent components to avoid losing runtime
        state (session locks, session tracker, rate limiter, etc.).
        """
        async with self._reload_lock:
            logger.info("Hot-reloading ontologies...")
            self._reload_kg_components()
            logger.info("Hot-reload complete")

    def _maybe_record_delegation_block(
        self, event: ToolCallEvent, params_sig: str | None = None
    ) -> None:
        """Record a block for delegation detection if this is an agent action."""
        if event.agent_id is not None:
            sig = (
                params_sig
                if params_sig is not None
                else DelegationDetector.make_signature(event.params)
            )
            self.delegation_detector.record_block(
                event.session_id, event.agent_id, event.tool_name, sig
            )

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
            self._evict_unlocked_session_locks()
        else:
            self._session_locks.move_to_end(session_id)
        return self._session_locks[session_id]

    def _evict_unlocked_session_locks(self) -> None:
        """Evict oldest unlocked session locks when over capacity."""
        while len(self._session_locks) > self._max_session_locks:
            # Walk from oldest, skip actively-held locks
            evicted = False
            for sid in list(self._session_locks):
                if not self._session_locks[sid].locked():
                    del self._session_locks[sid]
                    evicted = True
                    break
            if not evicted:
                break

    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision:
        """Run the full constraint checking pipeline."""
        lock = self._get_session_lock(event.session_id)
        async with lock:
            return await self._evaluate_tool_call_locked(event)

    async def _evaluate_tool_call_locked(self, event: ToolCallEvent) -> Decision:
        """Internal: runs the constraint pipeline under the session lock."""
        start = time.monotonic()
        checks: list[ConstraintCheck] = []
        prefs_applied: list[PreferenceApplied] = []

        # Compute params signature once for reuse
        params_sig = DelegationDetector.make_signature(event.params) if event.agent_id is not None else None

        # 0. Agent governance checks (before main pipeline)
        if event.agent_id is not None:
            # 0a. Verify agent token
            if self._require_token_auth:
                if not event.agent_token or not self.agent_registry.verify_token(
                    event.agent_id, event.agent_token
                ):
                    return Decision(block=True, reason="[SafeClaw] Invalid agent token")

            # 0b. Check kill switch
            if self.agent_registry.is_killed(event.agent_id):
                return Decision(
                    block=True, reason=f"[SafeClaw] Agent {event.agent_id} has been killed"
                )

            # 0c. Check delegation bypass
            delegation = self.delegation_detector.check_delegation(
                event.session_id, event.agent_id, event.tool_name, params_sig
            )
            if delegation.is_delegation and self.delegation_detector.mode == "strict":
                return Decision(
                    block=True, reason=f"[SafeClaw] Delegation bypass detected: {delegation.reason}"
                )

        # 1. Classify action
        action = self.classifier.classify(event.tool_name, event.params)

        # 1b. Role-based action check
        if event.agent_id is not None:
            agent_record = self.agent_registry.get_agent(event.agent_id)
            if agent_record:
                role = self.role_manager.get_role(agent_record.role)
                if role:
                    # Check temp permissions first - they bypass role restrictions
                    has_temp_grant = self.temp_permissions.check(
                        event.agent_id, action.ontology_class
                    )
                    if not has_temp_grant and not self.role_manager.is_action_allowed(
                        role, action.ontology_class
                    ):
                        reason = f"[SafeClaw] Role '{role.name}' does not allow action '{action.ontology_class}'"
                        if role.enforcement_mode == "warn-only":
                            logger.warning(
                                "Role '%s' would block '%s' but enforcement_mode is warn-only",
                                role.name,
                                action.ontology_class,
                            )
                        else:
                            decision = Decision(block=True, reason=reason)
                            self.delegation_detector.record_block(
                                event.session_id, event.agent_id, event.tool_name, params_sig
                            )
                            self._record_violation_and_log(
                                event, action, decision, checks, prefs_applied, start,
                                constraint_step="role_check",
                            )
                            return decision

                    # Check resource access for all path parameters
                    resource_paths = self._extract_resource_paths(event.params)
                    for resource_path in resource_paths:
                        if not self.role_manager.is_resource_allowed(
                            role, resource_path
                        ):
                            reason = f"[SafeClaw] Role '{role.name}' denied access to '{resource_path}'"
                            if role.enforcement_mode == "warn-only":
                                logger.warning(
                                    "Role '%s' would deny access to '%s' but enforcement_mode is warn-only",
                                    role.name,
                                    resource_path,
                                )
                            else:
                                decision = Decision(block=True, reason=reason)
                                self.delegation_detector.record_block(
                                    event.session_id, event.agent_id, event.tool_name, params_sig
                                )
                                self._record_violation_and_log(
                                    event, action, decision, checks, prefs_applied, start,
                                    constraint_step="role_check",
                                )
                                return decision

        # 2. SHACL validation
        shacl_result = self.shacl.validate(action.as_rdf_graph())
        if not shacl_result.conforms:
            reason = f"[SafeClaw] {shacl_result.first_violation_message}"
            checks.append(
                ConstraintCheck(
                    constraint_uri="shacl:validation",
                    constraint_type="SHACL",
                    result="violated",
                    reason=shacl_result.first_violation_message,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="shacl_validation",
            )
            return decision

        checks.append(
            ConstraintCheck(
                constraint_uri="shacl:validation",
                constraint_type="SHACL",
                result="satisfied",
                reason="All SHACL shapes conform",
            )
        )

        # 3. Policy check
        policy_result = self.policy_checker.check(action)
        if policy_result.violated:
            reason = f"[SafeClaw] {policy_result.reason}"
            checks.append(
                ConstraintCheck(
                    constraint_uri=policy_result.policy_uri,
                    constraint_type=policy_result.policy_type,
                    result="violated",
                    reason=policy_result.reason,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="policy_check",
            )
            return decision

        checks.append(
            ConstraintCheck(
                constraint_uri="policy:check",
                constraint_type="Policy",
                result="satisfied",
                reason="No policy violations",
            )
        )

        # 4. Preference check
        user_prefs = self.preference_checker.get_preferences(event.user_id)
        pref_result = self.preference_checker.check(action, user_prefs)
        if pref_result.violated:
            reason = f"[SafeClaw] {pref_result.reason}"
            prefs_applied.append(
                PreferenceApplied(
                    preference_uri=pref_result.preference_uri,
                    value="true",
                    effect=pref_result.reason,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="preference_check",
            )
            return decision

        # 5. Dependency check
        dep_result = self.dependency_checker.check(action, event.session_id)
        if dep_result.unmet:
            reason = f"[SafeClaw] {dep_result.reason}"
            checks.append(
                ConstraintCheck(
                    constraint_uri="dependency:check",
                    constraint_type="Dependency",
                    result="violated",
                    reason=dep_result.reason,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="dependency_check",
            )
            return decision

        # 6. Temporal constraint check
        temporal_result = self.temporal_checker.check(action, self.kg)
        if temporal_result.violated:
            reason = f"[SafeClaw] {temporal_result.reason}"
            checks.append(
                ConstraintCheck(
                    constraint_uri="temporal:check",
                    constraint_type="Temporal",
                    result="violated",
                    reason=temporal_result.reason,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="temporal_check",
            )
            return decision

        # 7. Rate limit check
        rate_result = self.rate_limiter.check(action, event.session_id)
        if rate_result.exceeded:
            reason = f"[SafeClaw] {rate_result.reason}"
            checks.append(
                ConstraintCheck(
                    constraint_uri="ratelimit:check",
                    constraint_type="RateLimit",
                    result="violated",
                    reason=rate_result.reason,
                )
            )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="rate_limit_check",
            )
            return decision

        # 8. Derived constraint rules (confirmation check)
        # BUG-004/035: Use server-side session data instead of client-supplied
        # session_history for security decisions (cumulative risk check).
        server_session_history = self.session_tracker.get_risk_history(event.session_id)
        # Include the current action's risk level so cumulative risk check
        # is not off-by-one (the current action hasn't been recorded yet).
        if action.risk_level:
            server_session_history = server_session_history + [
                f"{action.risk_level}:{action.ontology_class}"
            ]
        derived_result = self.derived_checker.check(action, user_prefs, server_session_history)
        if derived_result.requires_confirmation:
            reason = f"[SafeClaw] {derived_result.reason}"
            for rule in derived_result.derived_rules:
                checks.append(
                    ConstraintCheck(
                        constraint_uri=f"derived:{rule}",
                        constraint_type="DerivedRule",
                        result="requires_confirmation",
                        reason=derived_result.reason,
                    )
                )
            decision = Decision(block=True, reason=reason)
            self._maybe_record_delegation_block(event, params_sig)
            self._record_violation_and_log(
                event, action, decision, checks, prefs_applied, start,
                constraint_step="derived_rules",
            )
            return decision

        # 9. Hierarchy rate limit check (multi-agent)
        if event.agent_id is not None:
            hierarchy_ids = self.agent_registry.get_hierarchy_ids(event.agent_id)
            hierarchy_result = self.rate_limiter.check_hierarchy(action, hierarchy_ids)
            if hierarchy_result.exceeded:
                reason = f"[SafeClaw] {hierarchy_result.reason}"
                checks.append(
                    ConstraintCheck(
                        constraint_uri="ratelimit:hierarchy",
                        constraint_type="HierarchyRateLimit",
                        result="violated",
                        reason=hierarchy_result.reason,
                    )
                )
                decision = Decision(block=True, reason=reason)
                self._maybe_record_delegation_block(event, params_sig)
                self._record_violation_and_log(
                    event, action, decision, checks, prefs_applied, start,
                    constraint_step="hierarchy_rate_limit",
                )
                return decision

        # 10. All checks passed - record for rate limiting (only allowed actions)
        self.rate_limiter.record(action, event.session_id, agent_id=event.agent_id)
        decision = Decision(block=False)
        self._log_decision(event, action, decision, checks, prefs_applied, start)

        # Fire-and-forget LLM tasks (non-blocking, passive observer)
        self._fire_llm_tasks(event, action, decision, checks)

        return decision

    async def evaluate_message(self, event: MessageEvent) -> Decision:
        # BUG-019: Acquire session lock for message evaluation, same as tool calls
        lock = self._get_session_lock(event.session_id)
        async with lock:
            return await self._evaluate_message_locked(event)

    async def _evaluate_message_locked(self, event: MessageEvent) -> Decision:
        """Internal: runs the message evaluation pipeline under the session lock."""
        start = time.monotonic()

        # Agent governance checks
        if event.agent_id is not None:
            # Verify agent token
            if self._require_token_auth:
                if not event.agent_token or not self.agent_registry.verify_token(
                    event.agent_id, event.agent_token
                ):
                    return Decision(block=True, reason="[SafeClaw] Invalid agent token")

            # Check kill switch
            if self.agent_registry.is_killed(event.agent_id):
                return Decision(
                    block=True, reason=f"[SafeClaw] Agent {event.agent_id} has been killed"
                )

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
            self._log_message_decision(event, decision, start, risk_level=gate_result.risk_level)
            return decision

        # User preference: confirm before send (check before recording)
        user_prefs = self.preference_checker.get_preferences(event.user_id)
        if user_prefs.confirm_before_send:
            decision = Decision(
                block=True,
                reason="[SafeClaw] User preference requires confirmation before sending messages",
            )
            self._log_message_decision(event, decision, start, risk_level=gate_result.risk_level)
            return decision

        # Record message only after all checks pass (not blocked messages)
        self.message_gate.record_message(event.session_id)

        decision = Decision(block=False)
        self._log_message_decision(event, decision, start, risk_level=gate_result.risk_level)
        return decision

    def _log_message_decision(
        self, event: MessageEvent, decision: Decision, start_time: float,
        risk_level: str = "LowRisk",
    ) -> None:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        record = DecisionRecord(
            session_id=event.session_id,
            user_id=event.user_id,
            agent_id=event.agent_id,
            action=ActionDetail(
                tool_name="message",
                params={"to": event.to, "content_length": len(event.content)},
                ontology_class="SendMessage",
                risk_level=risk_level,
                is_reversible=False,
                affects_scope="ExternalWorld",
            ),
            decision="blocked" if decision.block else "allowed",
            justification=Justification(elapsed_ms=elapsed_ms),
        )
        decision.audit_id = record.id
        self.audit.log(record)
        if self.api_key_manager and hasattr(self.api_key_manager, 'log_audit_decision'):
            import json
            self.api_key_manager.log_audit_decision(
                user_id=event.user_id,
                timestamp=record.timestamp,
                session_id=event.session_id,
                tool_name="message",
                params_summary=json.dumps({"to": event.to}, default=str)[:500],
                decision="blocked" if decision.block else "allowed",
                risk_level=risk_level,
                reason=decision.reason or "passed all checks",
                elapsed_ms=elapsed_ms,
            )

    async def build_context(self, event: AgentStartEvent) -> ContextResult:
        # Get session summary from tracker
        session_summary = self.session_tracker.get_session_summary(event.session_id)
        context = self.context_builder.build_context(
            event.user_id,
            session_id=event.session_id,
            session_history=session_summary or None,
        )

        # Append agent role info if applicable
        if event.agent_id is not None:
            agent_record = self.agent_registry.get_agent(event.agent_id)
            if agent_record:
                role = self.role_manager.get_role(agent_record.role)
                if role:
                    context += f"\nAgent role: {role.name} (autonomy: {role.autonomy_level})"
                    if role.denied_action_classes:
                        context += (
                            f"\nDenied actions: {', '.join(sorted(role.denied_action_classes))}"
                        )

        return ContextResult(prepend_context=context)

    async def record_action_result(self, event: ToolResultEvent) -> None:
        async with self._get_session_lock(event.session_id):
            # Agent governance checks (same as evaluate_tool_call/evaluate_message)
            if event.agent_id is not None:
                if self._require_token_auth:
                    if not event.agent_token or not self.agent_registry.verify_token(
                        event.agent_id, event.agent_token
                    ):
                        logger.warning(
                            "record_action_result rejected: invalid token for agent %s",
                            event.agent_id,
                        )
                        return
                if self.agent_registry.is_killed(event.agent_id):
                    logger.warning(
                        "record_action_result rejected: agent %s is killed",
                        event.agent_id,
                    )
                    return

            action = self.classifier.classify(event.tool_name, event.params)

            # Record in session tracker (Phase 3: KG feedback loop)
            # BUG-004/035: Include risk_level for server-side cumulative risk tracking
            self.session_tracker.record_outcome(
                session_id=event.session_id,
                action_class=action.ontology_class,
                tool_name=event.tool_name,
                success=event.success,
                params=event.params,
                risk_level=action.risk_level,
            )

            # Record successful actions in dependency tracker
            if event.success:
                self.dependency_checker.record_action(event.session_id, action.ontology_class)

    async def clear_session(self, session_id: str) -> None:
        """Clean up all per-session state when a session ends.

        BUG-028: Acquires the session lock before clearing to prevent races
        with in-flight evaluations, then removes the lock from the dict.
        """
        lock = self._get_session_lock(session_id)
        async with lock:
            self.session_tracker.clear_session(session_id)
            self.rate_limiter.clear_session(session_id)
            self.context_builder.clear_session(session_id)
            self.dependency_checker.clear_session(session_id)
            self.message_gate.clear_session(session_id)
            self.delegation_detector.clear_session(session_id)
        # Remove lock after releasing it (outside the async with block)
        self._session_locks.pop(session_id, None)
        logger.info(f"Session {session_id} cleared")

    async def log_llm_io(self, event: LlmIOEvent) -> None:
        logger.debug(
            f"LLM {event.direction}: {event.content[:100]}{'...' if len(event.content) > 100 else ''}"
        )

    def _fire_llm_tasks(
        self,
        event: ToolCallEvent,
        action,
        decision,
        checks,
    ) -> None:
        """Launch background LLM review tasks. Non-blocking, fire-and-forget."""
        if self.security_reviewer and self.config.llm_security_review_enabled:
            from safeclaw.llm.security_reviewer import ReviewEvent

            review_event = ReviewEvent(
                tool_name=event.tool_name,
                params=event.params,
                classified_action=action,
                symbolic_decision="allowed" if not decision.block else "blocked",
                session_history=getattr(event, "session_history", []),
                constraints_checked=[
                    {"type": c.constraint_type, "result": c.result, "reason": c.reason}
                    for c in checks
                ],
            )
            asyncio.create_task(self._run_security_review(review_event))

        if (
            self.classification_observer
            and self.config.llm_classification_observe
            and action.ontology_class == "Action"
        ):
            asyncio.create_task(
                self._run_classification_observer(event.tool_name, event.params, action)
            )

    async def _run_security_review(self, review_event) -> None:
        """Background task: run security review and handle findings."""
        try:
            finding = await self.security_reviewer.review(review_event)
            if finding:
                logger.warning(
                    "Security finding [%s/%s]: %s",
                    finding.severity,
                    finding.category,
                    finding.description,
                )
                self.event_bus.publish(SafeClawEvent(
                    event_type="security_finding",
                    severity="critical" if finding.severity == "critical" else "warning",
                    title=f"Security: {finding.category}",
                    detail=finding.description,
                    metadata={
                        "category": finding.category,
                        "finding_severity": finding.severity,
                        "tool_name": review_event.classified_action.tool_name,
                    },
                ))
                if finding.severity == "critical" and review_event.classified_action.tool_name:
                    logger.critical("CRITICAL security finding — manual review required")
        except Exception:
            logger.debug("Security review background task failed", exc_info=True)

    async def _run_classification_observer(self, tool_name, params, action) -> None:
        """Background task: observe classification and suggest improvements."""
        try:
            await self.classification_observer.observe(tool_name, params, action)
        except Exception:
            logger.debug("Classification observer background task failed", exc_info=True)

    def _record_violation_and_log(
        self,
        event: ToolCallEvent,
        action,
        decision: Decision,
        checks: list[ConstraintCheck],
        prefs_applied: list[PreferenceApplied],
        start_time: float,
        constraint_step: str = "",
    ) -> None:
        """Log decision and record the violation for context injection."""
        self.context_builder.record_violation(event.session_id, decision.reason)
        self.session_tracker.record_violation(event.session_id, decision.reason)
        self._log_decision(
            event, action, decision, checks, prefs_applied, start_time, constraint_step
        )

        # Publish blocked event to event bus
        self.event_bus.publish(SafeClawEvent(
            event_type="blocked",
            severity="warning",
            title=f"Blocked: {event.tool_name}",
            detail=decision.reason,
            metadata={
                "tool_name": event.tool_name,
                "session_id": event.session_id,
                "ontology_class": action.ontology_class,
                "risk_level": action.risk_level,
            },
        ))

    def _log_decision(
        self,
        event: ToolCallEvent,
        action,
        decision: Decision,
        checks: list[ConstraintCheck],
        prefs_applied: list[PreferenceApplied],
        start_time: float,
        constraint_step: str = "",
    ) -> None:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        # BUG-004/035: Use server-side session history for audit records instead
        # of client-supplied event.session_history
        server_history = self.session_tracker.get_risk_history(event.session_id)
        record = DecisionRecord(
            session_id=event.session_id,
            user_id=event.user_id,
            agent_id=event.agent_id,
            action=ActionDetail(
                tool_name=event.tool_name,
                params=event.params,
                ontology_class=action.ontology_class,
                risk_level=action.risk_level,
                is_reversible=action.is_reversible,
                affects_scope=action.affects_scope,
            ),
            decision="blocked" if decision.block else "allowed",
            constraint_step=constraint_step,
            justification=Justification(
                constraints_checked=checks,
                preferences_applied=prefs_applied,
                elapsed_ms=elapsed_ms,
            ),
            session_action_history=server_history,
        )
        decision.audit_id = record.id
        self.audit.log(record)
        # Write to shared DB for user dashboard (if enabled)
        if self.api_key_manager and hasattr(self.api_key_manager, 'log_audit_decision'):
            import json
            params_summary = json.dumps(event.params, default=str)[:500]
            self.api_key_manager.log_audit_decision(
                user_id=event.user_id,
                timestamp=record.timestamp,
                session_id=event.session_id,
                tool_name=event.tool_name,
                params_summary=params_summary,
                decision="blocked" if decision.block else "allowed",
                risk_level=action.risk_level,
                reason=decision.reason or "passed all checks",
                elapsed_ms=elapsed_ms,
            )
