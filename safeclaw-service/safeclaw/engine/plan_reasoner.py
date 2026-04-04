"""Plan-level reasoner - analyzes multi-step plans before execution."""

from dataclasses import dataclass, field

from safeclaw.constraints.action_classifier import ActionClassifier, ClassifiedAction
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.constraints.preference_checker import UserPreferences
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker


@dataclass
class PlanStep:
    """A single step in a multi-step plan."""

    tool_name: str
    params: dict
    description: str = ""


@dataclass
class PlanIssue:
    """An issue found during plan-level reasoning."""

    step_index: int
    severity: str  # "error" | "warning" | "info"
    issue_type: str  # "policy_violation" | "dependency_order" | "cumulative_risk" | "irreversible"
    message: str


@dataclass
class PlanAssessment:
    """The result of analyzing a multi-step plan."""

    issues: list[PlanIssue] = field(default_factory=list)
    total_risk_score: int = 0
    recommended_order: list[int] | None = None

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)


class PlanReasoner:
    """Analyzes multi-step plans to detect issues before execution begins.

    Checks for:
    - Policy violations in any step
    - Dependency ordering issues
    - Cumulative risk across the plan
    - Irreversible actions that should be confirmed
    """

    RISK_SCORES = {
        "LowRisk": 1,
        "MediumRisk": 3,
        "HighRisk": 7,
        "CriticalRisk": 15,
    }

    def __init__(
        self,
        classifier: ActionClassifier,
        policy_checker: PolicyChecker,
        derived_checker: DerivedConstraintChecker,
    ):
        self.classifier = classifier
        self.policy_checker = policy_checker
        self.derived_checker = derived_checker

    def assess_plan(self, steps: list[PlanStep], user_prefs: UserPreferences) -> PlanAssessment:
        """Analyze a full plan and return all issues found."""
        issues: list[PlanIssue] = []
        actions: list[ClassifiedAction] = []
        simulated_history: list[str] = []
        total_risk = 0

        for i, step in enumerate(steps):
            action = self.classifier.classify(step.tool_name, step.params)
            actions.append(action)
            total_risk += self.RISK_SCORES.get(action.risk_level, 3)

            # Check policy violations
            policy_result = self.policy_checker.check(action)
            if policy_result.violated:
                issues.append(
                    PlanIssue(
                        step_index=i,
                        severity="error",
                        issue_type="policy_violation",
                        message=f"Step {i + 1} ({action.ontology_class}): {policy_result.reason}",
                    )
                )

            # Check derived constraints
            derived_result = self.derived_checker.check(action, user_prefs, simulated_history)
            if derived_result.requires_confirmation:
                issues.append(
                    PlanIssue(
                        step_index=i,
                        severity="warning",
                        issue_type="irreversible",
                        message=f"Step {i + 1}: {derived_result.reason}",
                    )
                )

            simulated_history.append(f"{action.risk_level}:{action.ontology_class}")

        # Check cumulative risk
        if total_risk > 30:
            issues.append(
                PlanIssue(
                    step_index=-1,
                    severity="warning",
                    issue_type="cumulative_risk",
                    message=f"Plan cumulative risk score is {total_risk} (high). Consider breaking into smaller steps.",
                )
            )

        # Check dependency ordering
        dep_issues = self._check_dependency_order(actions)
        issues.extend(dep_issues)

        return PlanAssessment(
            issues=issues,
            total_risk_score=total_risk,
        )

    def _check_dependency_order(self, actions: list[ClassifiedAction]) -> list[PlanIssue]:
        """Check if actions are in the correct dependency order."""
        issues = []
        seen_classes: set[str] = set()

        from safeclaw.constraints.dependency_checker import DEFAULT_DEPENDENCIES

        for i, action in enumerate(actions):
            required = DEFAULT_DEPENDENCIES.get(action.ontology_class, [])
            for req in required:
                if req not in seen_classes:
                    # Check if the requirement appears later in the plan
                    later_has_req = any(a.ontology_class == req for a in actions[i + 1 :])
                    if later_has_req:
                        issues.append(
                            PlanIssue(
                                step_index=i,
                                severity="error",
                                issue_type="dependency_order",
                                message=(
                                    f"Step {i + 1} ({action.ontology_class}) requires "
                                    f"'{req}' which appears later in the plan. Reorder required."
                                ),
                            )
                        )
                    else:
                        issues.append(
                            PlanIssue(
                                step_index=i,
                                severity="warning",
                                issue_type="dependency_order",
                                message=(
                                    f"Step {i + 1} ({action.ontology_class}) requires "
                                    f"'{req}' which is not in the plan."
                                ),
                            )
                        )
            seen_classes.add(action.ontology_class)

        return issues
