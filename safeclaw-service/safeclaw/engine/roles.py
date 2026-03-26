"""Role management for multi-agent governance."""

from __future__ import annotations

import copy
import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy
    from safeclaw.engine.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def _glob_match(path: str, pattern: str) -> bool:
    """Match a path against a glob pattern, supporting ``**`` across separators.

    ``fnmatch.fnmatch`` treats ``*`` and ``**`` identically (single-segment
    only).  This function converts ``**`` to a regex that crosses directory
    boundaries while ensuring a single ``*`` does **not** cross them.

    Edge cases handled:

    * Empty *path* never matches (a resource path must be non-empty).
    * Empty segments produced by ``pattern.split("**")`` (e.g. leading or
      trailing ``**``) are handled by normalising boundary ``/`` characters
      and using a joiner regex that optionally matches any number of path
      segments including zero.
    """
    # Empty paths never match — a real resource path is always non-empty
    if not path:
        return False

    # Split pattern on ** to handle recursive matching separately
    segments = pattern.split("**")

    # Convert each non-** segment via fnmatch.translate, strip anchoring
    regex_parts: list[str] = []
    for seg in segments:
        translated = fnmatch.translate(seg)
        # fnmatch.translate output varies by Python version:
        #   Python 3.12+: '(?s:...)\\z'
        #   Python 3.11:  '(?s:...)\\Z'
        #   Older:        '...\\Z'
        # Strip the wrapper and anchoring to get the inner pattern.
        if translated.startswith("(?s:"):
            if translated.endswith(r"\z"):
                inner = translated[4:-3]
            elif translated.endswith(r"\Z"):
                inner = translated[4:-3]
            else:
                inner = translated[4:-1]
        else:
            if translated.endswith(r"\Z"):
                inner = translated[:-2]
            elif translated.endswith(r"\z"):
                inner = translated[:-2]
            else:
                inner = translated

        # fnmatch translates * to .* which, under the (?s:) DOTALL flag,
        # crosses path separators.  Replace .* with [^/]* so that a single
        # * only matches within one path segment.  This substitution is safe
        # because we add our own cross-directory .* for ** below.
        inner = inner.replace(".*", "[^/]*")

        regex_parts.append(inner)

    if len(regex_parts) == 1:
        # No ** in the pattern — straightforward match
        full_regex = regex_parts[0]
    else:
        # Normalise boundary slashes around ** joins.
        # When ** matches zero segments (e.g. /a/**/d.py matching /a/d.py)
        # the surrounding slashes would otherwise double up.  Strip the
        # trailing / from segments before a join and the leading / from
        # segments after a join, then reconnect via the joiner regex.
        cleaned: list[str] = []
        for i, part in enumerate(regex_parts):
            p = part
            if i < len(regex_parts) - 1 and p.endswith("/"):
                p = p[:-1]
            if i > 0 and p.startswith("/"):
                p = p[1:]
            cleaned.append(p)

        # The joiner must match what ** expands to between the cleaned
        # segments.  Possible matches:
        #   ""          — ** matches zero segments  (/a/**/d.py -> /a/d.py)
        #   "/"         — the absorbed separator    (/a/** -> /a/x)
        #   "/x/y/z/"  — multiple segments          (/a/**/f -> /a/x/y/z/f)
        #   "x/y/"     — no leading / (pattern starts with **)
        #   "/x/y"     — no trailing / (pattern ends with **)
        #   "x"        — single non-slash char (pattern is exactly **)
        # Limit pattern complexity to prevent ReDoS with many ** segments.
        # Patterns with more than 4 ** separators are rejected as too complex.
        if len(cleaned) > 5:
            return False

        # Use a non-backtracking character class instead of .* to prevent
        # catastrophic backtracking when multiple ** joiners interact.
        # [\\s\\S]*? (non-greedy) avoids the nested quantifier problem.
        joiner = "(?:[\\s\\S]*?)"
        full_regex = joiner.join(cleaned)

    return re.fullmatch(full_regex, path) is not None


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
            "ForcePush",
            "ShellAction",
            "SendMessage",
        },
        resource_patterns={"allow": ["**"], "deny": []},
    ),
    "developer": Role(
        name="developer",
        enforcement_mode="enforce",
        autonomy_level="moderate",
        allowed_action_classes=set(),
        denied_action_classes={
            "ForcePush",
            "DeleteFile",
            "GitResetHard",
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

    def __init__(
        self,
        config: dict | None = None,
        hierarchy: ClassHierarchy | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ):
        self._roles: dict[str, Role] = {}
        self._hierarchy = hierarchy
        self._default_role_name = "developer"
        if config and "roles" in config:
            self._default_role_name = config["roles"].get("defaultRole", "developer")
            if "definitions" in config["roles"]:
                for name, rdef in config["roles"]["definitions"].items():
                    rp = rdef.get("resource_patterns", {"allow": ["**"], "deny": []})
                    if not isinstance(rp.get("allow"), list) or not isinstance(rp.get("deny"), list):
                        logger.warning(f"Invalid resource_patterns for role {name}, using defaults")
                        rp = {"allow": ["**"], "deny": []}
                    raw_allowed = rdef.get("allowed_action_classes", [])
                    if not isinstance(raw_allowed, list):
                        logger.warning(
                            f"allowed_action_classes for role {name} is not a list, using empty list"
                        )
                        raw_allowed = []
                    raw_denied = rdef.get("denied_action_classes", [])
                    if not isinstance(raw_denied, list):
                        logger.warning(
                            f"denied_action_classes for role {name} is not a list, using empty list"
                        )
                        raw_denied = []
                    self._roles[name] = Role(
                        name=name,
                        enforcement_mode=rdef.get("enforcement_mode", "enforce"),
                        autonomy_level=rdef.get("autonomy_level", "supervised"),
                        allowed_action_classes=set(raw_allowed),
                        denied_action_classes=set(raw_denied),
                        resource_patterns=rp,
                    )
        else:
            self._roles = {k: copy.deepcopy(v) for k, v in BUILTIN_ROLES.items()}

        # Load roles from knowledge graph TTL files (merge, don't override builtins)
        if knowledge_graph is not None:
            self._load_roles_from_kg(knowledge_graph)

    def _load_roles_from_kg(self, kg: KnowledgeGraph) -> None:
        """Load role definitions from the knowledge graph and merge into _roles.

        KG (TTL) roles override Python builtins so that editing the ontology
        has runtime effect (#46).  Roles loaded from explicit config (JSON)
        still take priority — those are skipped here.
        """
        from safeclaw.engine.knowledge_graph import SP, SC

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            PREFIX sc: <{SC}>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?role ?label ?enforcement ?autonomy WHERE {{
                ?role a sp:Role .
                ?role rdfs:label ?label .
                OPTIONAL {{ ?role sp:enforcementMode ?enforcement }}
                OPTIONAL {{ ?role sp:autonomyLevel ?autonomy }}
            }}
        """)

        for row in results:
            label = str(row["label"])
            role_name = label.lower()

            # Skip roles loaded from explicit JSON config (they take priority)
            # but allow KG roles to override Python builtins
            if role_name in self._roles and role_name not in BUILTIN_ROLES:
                continue

            role_uri = row["role"]
            enforcement = str(row.get("enforcement") or "enforce")
            autonomy = str(row.get("autonomy") or "supervised")

            # Query allowed actions
            allowed_results = kg.query(f"""
                PREFIX sp: <{SP}>
                SELECT ?action WHERE {{
                    <{role_uri}> sp:allowsAction ?action .
                }}
            """)
            allowed = set()
            for ar in allowed_results:
                action_str = str(ar["action"])
                local_name = action_str.rsplit("#", 1)[-1] if "#" in action_str else action_str
                if local_name == "AllActions":
                    allowed = set()  # empty means all allowed
                    break
                allowed.add(local_name)

            # Query denied actions
            denied_results = kg.query(f"""
                PREFIX sp: <{SP}>
                SELECT ?action WHERE {{
                    <{role_uri}> sp:deniesAction ?action .
                }}
            """)
            denied = set()
            for dr in denied_results:
                action_str = str(dr["action"])
                local_name = action_str.rsplit("#", 1)[-1] if "#" in action_str else action_str
                denied.add(local_name)

            # Query denied write paths for resource patterns
            deny_paths = []
            path_results = kg.query(f"""
                PREFIX sp: <{SP}>
                SELECT ?path WHERE {{
                    <{role_uri}> sp:deniesWritePath ?path .
                }}
            """)
            for pr in path_results:
                deny_paths.append(str(pr["path"]))

            resource_patterns = {"allow": ["**"], "deny": deny_paths}

            self._roles[role_name] = Role(
                name=role_name,
                enforcement_mode=enforcement,
                autonomy_level=autonomy,
                allowed_action_classes=allowed,
                denied_action_classes=denied,
                resource_patterns=resource_patterns,
            )
            logger.info("Loaded role '%s' from knowledge graph", role_name)

    def get_role(self, name: str) -> Role | None:
        return self._roles.get(name)

    def get_default_role(self) -> Role:
        return self._roles.get(self._default_role_name, BUILTIN_ROLES["developer"])

    def is_action_allowed(self, role: Role, action_class: str) -> bool:
        # Unknown/generic actions ("Action") are denied for restricted roles.
        # Only unrestricted roles (no denied classes and no allowed-list) pass.
        if action_class == "Action":
            is_unrestricted = (
                not role.denied_action_classes and not role.allowed_action_classes
            )
            if not is_unrestricted:
                return False

        if self._hierarchy:
            superclasses = self._hierarchy.get_superclasses(action_class)
            # Denied if action_class or any ancestor is denied
            if superclasses & role.denied_action_classes:
                return False
            # If allowed list is set, allowed if action_class or any ancestor matches
            if role.allowed_action_classes:
                return bool(superclasses & role.allowed_action_classes)
            return True
        # Fallback: exact match (no hierarchy)
        if action_class in role.denied_action_classes:
            return False
        if role.allowed_action_classes:
            return action_class in role.allowed_action_classes
        return True

    def is_resource_allowed(self, role: Role, resource_path: str) -> bool:
        resource_path = os.path.normpath(resource_path)
        if ".." in resource_path.split(os.sep):
            return False
        # Strip leading / for consistent matching
        norm = resource_path.lstrip("/")
        patterns = role.resource_patterns
        for deny_pat in patterns.get("deny", []):
            if _glob_match(norm, deny_pat.lstrip("/")):
                return False
        allow_pats = patterns.get("allow", [])
        if not allow_pats:
            return False
        return any(_glob_match(norm, pat.lstrip("/")) for pat in allow_pats)

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

        # Use None as sentinel for "all allowed" (empty set means all)
        allowed = set(role.allowed_action_classes) if role.allowed_action_classes else None
        org_allowed_raw = org_policy.get("allowed_actions", [])
        org_allowed = set(org_allowed_raw) if org_allowed_raw else None
        parent_allowed_raw = parent_constraints.get("allowed_actions", [])
        parent_allowed = set(parent_allowed_raw) if parent_allowed_raw else None

        # Only intersect when both sides are non-None sets
        if allowed is not None and org_allowed is not None:
            allowed = allowed & org_allowed
        elif org_allowed is not None:
            allowed = org_allowed

        if allowed is not None and parent_allowed is not None:
            allowed = allowed & parent_allowed
        elif parent_allowed is not None:
            allowed = parent_allowed

        resource_deny = list(role.resource_patterns.get("deny", []))
        resource_deny += list(org_policy.get("resource_deny", []))
        resource_deny += list(parent_constraints.get("resource_deny", []))

        resource_allow = list(role.resource_patterns.get("allow", []))
        org_res_allow = org_policy.get("resource_allow", [])
        parent_res_allow = parent_constraints.get("resource_allow", [])
        if org_res_allow:
            # Keep role patterns that are a subset of any org pattern (org pattern matches role pattern)
            narrower = [
                p for p in resource_allow
                if any(fnmatch.fnmatch(p.lstrip("/"), o.lstrip("/")) for o in org_res_allow)
            ]
            resource_allow = narrower or org_res_allow
        if parent_res_allow:
            narrower = [
                p for p in resource_allow
                if any(fnmatch.fnmatch(p.lstrip("/"), o.lstrip("/")) for o in parent_res_allow)
            ]
            resource_allow = narrower or parent_res_allow

        return {
            "denied_actions": sorted(denied),
            "allowed_actions": sorted(allowed) if allowed is not None else [],
            "resource_deny": sorted(set(resource_deny)),
            "resource_allow": sorted(set(resource_allow)),
            "enforcement_mode": role.enforcement_mode,
            "autonomy_level": role.autonomy_level,
        }
