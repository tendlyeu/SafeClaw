"""NL → Policy Compiler — turns natural language into validated Turtle policies."""

import logging
import re
from dataclasses import dataclass, field

from rdflib import Graph, Namespace

from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.llm.prompts import POLICY_COMPILER_SYSTEM

logger = logging.getLogger("safeclaw.llm.compiler")

# Prefixes needed to parse generated Turtle
TURTLE_PREFIXES = """\
@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .
@prefix sc: <http://safeclaw.uku.ai/ontology/agent#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
"""


@dataclass
class CompileResult:
    success: bool
    turtle: str = ""
    policy_name: str = ""
    policy_type: str = ""
    validation_errors: list[str] = field(default_factory=list)
    explanation: str = ""


class PolicyCompiler:
    """Compiles natural language policy descriptions into validated Turtle."""

    def __init__(self, client, kg: KnowledgeGraph):
        self.client = client
        self.kg = kg

    async def compile(self, natural_language: str) -> CompileResult:
        """Convert a natural language policy to Turtle. Returns CompileResult."""
        raw_turtle = await self.client.chat(
            messages=[
                {"role": "system", "content": POLICY_COMPILER_SYSTEM},
                {"role": "user", "content": natural_language},
            ],
            model=self.client.model_large,
            temperature=0.0,
        )

        if raw_turtle is None:
            return CompileResult(
                success=False,
                validation_errors=["LLM request failed or timed out"],
            )

        # Strip markdown fences if present
        turtle = self._strip_fences(raw_turtle)

        # Validate
        errors = self._validate(turtle)
        if errors:
            return CompileResult(
                success=False,
                turtle=turtle,
                validation_errors=errors,
            )

        # Extract policy name and type
        name = self._extract_policy_name(turtle)
        ptype = self._extract_policy_type(turtle)

        return CompileResult(
            success=True,
            turtle=turtle,
            policy_name=name,
            policy_type=ptype,
            explanation=f"Generated {ptype} policy '{name}' from: {natural_language}",
        )

    def _strip_fences(self, text: str) -> str:
        """Remove markdown code fences if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()

    def _validate(self, turtle: str) -> list[str]:
        """Validate the generated Turtle. Returns list of error strings."""
        errors = []

        # 1. Syntax check: parse with RDFLib
        full_turtle = TURTLE_PREFIXES + "\n" + turtle
        g = Graph()
        try:
            g.parse(data=full_turtle, format="turtle")
        except Exception as e:
            errors.append(f"Turtle syntax error: {e}")
            return errors

        # 2. Check that sp:reason is present
        sp = Namespace("http://safeclaw.uku.ai/ontology/policy#")
        reasons = list(g.triples((None, sp.reason, None)))
        if not reasons:
            errors.append("Policy must include sp:reason property")

        # 3. Check namespace usage
        valid_ns = {
            "http://safeclaw.uku.ai/ontology/policy#",
            "http://safeclaw.uku.ai/ontology/agent#",
        }
        for s, _, _ in g:
            s_str = str(s)
            if s_str.startswith("http://") and not any(s_str.startswith(ns) for ns in valid_ns):
                errors.append(f"Unknown namespace in subject: {s_str}")

        return errors

    def _extract_policy_name(self, turtle: str) -> str:
        """Extract the policy name (sp:Name) from the Turtle block."""
        match = re.search(r"sp:(\w+)\s+a\s+", turtle)
        return match.group(1) if match else "UnknownPolicy"

    def _extract_policy_type(self, turtle: str) -> str:
        """Extract the policy type (Prohibition/Obligation/Permission).

        Uses regex to match 'a sp:Type' patterns in RDF type declarations,
        avoiding false matches from string literals containing type names.
        """
        # Match RDF type declarations like "a sp:Prohibition" or "rdf:type sp:Prohibition"
        if re.search(r"\ba\s+sp:Prohibition\b", turtle) or re.search(
            r"rdf:type\s+sp:Prohibition\b", turtle
        ):
            return "prohibition"
        elif re.search(r"\ba\s+sp:Obligation\b", turtle) or re.search(
            r"rdf:type\s+sp:Obligation\b", turtle
        ):
            return "obligation"
        elif re.search(r"\ba\s+sp:Permission\b", turtle) or re.search(
            r"rdf:type\s+sp:Permission\b", turtle
        ):
            return "permission"
        return "unknown"
