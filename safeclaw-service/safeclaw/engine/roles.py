"""Role management for multi-agent governance."""

from dataclasses import dataclass, field
from fnmatch import fnmatch


@dataclass
class Role:
    """A role defining permissions and constraints for agents."""

    name: str
    enforcement_mode: str  # "enforce" or "warn-only"
    autonomy_level: str  # "supervised", "moderate", "full"
    allowed_action_classes: set[str] = field(default_factory=set)
    denied_action_classes: set[str] = field(default_factory=set)
    resource_patterns: dict = field(
        default_factory=lambda: {"allow": ["**"], "deny": []}
    )


BUILTIN_ROLES = {
    "researcher": Role(
        name="researcher",
        enforcement_mode="enforce",
        autonomy_level="supervised",
        allowed_action_classes={
            "ReadFile",
            "ListFiles",
            "SearchFiles",
        },
        denied_action_classes={
            "WriteFile",
            "EditFile",
            "DeleteFile",
            "GitPush",
            "GitForcePush",
            "ShellAction",
        },
        resource_patterns={"allow": ["**"], "deny": []},
    ),
    "developer": Role(
        name="developer",
        enforcement_mode="enforce",
        autonomy_level="moderate",
        allowed_action_classes=set(),
        denied_action_classes={
            "GitForcePush",
            "DeleteRootFiles",
            "SystemConfigChange",
        },
        resource_patterns={"allow": ["**"], "deny": ["/secrets/**", "/etc/**"]},
    ),
    "admin": Role(
        name="admin",
        enforcement_mode="warn-only",
        autonomy_level="full",
        allowed_action_classes=set(),
        denied_action_classes=set(),
        resource_patterns={"allow": ["**"], "deny": []},
    ),
}


class RoleManager:
    """Manages roles and checks action/resource permissions."""

    def __init__(self, config: dict | None = None):
        self._roles: dict[str, Role] = {}
        if config and "roles" in config and "definitions" in config["roles"]:
            for name, rdef in config["roles"]["definitions"].items():
                self._roles[name] = Role(
                    name=name,
                    enforcement_mode=rdef.get("enforcement_mode", "enforce"),
                    autonomy_level=rdef.get("autonomy_level", "supervised"),
                    allowed_action_classes=set(
                        rdef.get("allowed_action_classes", [])
                    ),
                    denied_action_classes=set(
                        rdef.get("denied_action_classes", [])
                    ),
                    resource_patterns=rdef.get(
                        "resource_patterns", {"allow": ["**"], "deny": []}
                    ),
                )
        else:
            self._roles = dict(BUILTIN_ROLES)

    def get_role(self, name: str) -> Role | None:
        return self._roles.get(name)

    def get_default_role(self) -> Role:
        return self._roles.get("researcher", BUILTIN_ROLES["researcher"])

    def is_action_allowed(self, role: Role, action_class: str) -> bool:
        if action_class in role.denied_action_classes:
            return False
        if role.allowed_action_classes:
            return action_class in role.allowed_action_classes
        return True

    def is_resource_allowed(self, role: Role, resource_path: str) -> bool:
        patterns = role.resource_patterns
        for deny_pat in patterns.get("deny", []):
            if fnmatch(resource_path, deny_pat):
                return False
        allow_pats = patterns.get("allow", [])
        if not allow_pats:
            return False
        return any(fnmatch(resource_path, pat) for pat in allow_pats)

    def get_effective_constraints(
        self,
        role: Role,
        org_policy: dict,
        parent_constraints: dict,
    ) -> dict:
        """Merge constraints from 3 tiers (most restrictive wins).

        Tiers: org_policy -> parent_constraints -> role.
        Result is the union of all denied actions and the intersection
        of all allowed resources.
        """
        denied = set(role.denied_action_classes)
        denied |= set(org_policy.get("denied_actions", []))
        denied |= set(parent_constraints.get("denied_actions", []))

        allowed = set(role.allowed_action_classes)
        org_allowed = set(org_policy.get("allowed_actions", []))
        parent_allowed = set(parent_constraints.get("allowed_actions", []))

        if org_allowed and allowed:
            allowed &= org_allowed
        elif org_allowed:
            allowed = org_allowed

        if parent_allowed and allowed:
            allowed &= parent_allowed
        elif parent_allowed:
            allowed = parent_allowed

        resource_deny = list(role.resource_patterns.get("deny", []))
        resource_deny += list(org_policy.get("resource_deny", []))
        resource_deny += list(parent_constraints.get("resource_deny", []))

        resource_allow = list(role.resource_patterns.get("allow", []))
        org_res_allow = org_policy.get("resource_allow", [])
        parent_res_allow = parent_constraints.get("resource_allow", [])
        if org_res_allow:
            resource_allow = [
                p for p in resource_allow if p in org_res_allow
            ] or org_res_allow
        if parent_res_allow:
            resource_allow = [
                p for p in resource_allow if p in parent_res_allow
            ] or parent_res_allow

        return {
            "denied_actions": sorted(denied),
            "allowed_actions": sorted(allowed),
            "resource_deny": sorted(set(resource_deny)),
            "resource_allow": sorted(set(resource_allow)),
            "enforcement_mode": role.enforcement_mode,
            "autonomy_level": role.autonomy_level,
        }
