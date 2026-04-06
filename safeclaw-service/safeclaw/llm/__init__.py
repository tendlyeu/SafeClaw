"""SafeClaw LLM layer — passive observer and advisor."""

from safeclaw.llm.client import SafeClawLLMClient, create_client
from safeclaw.llm.classification_observer import ClassificationObserver, ClassificationSuggestion
from safeclaw.llm.explainer import DecisionExplainer
from safeclaw.llm.policy_compiler import CompileResult, PolicyCompiler
from safeclaw.llm.providers import PROVIDERS, ProviderInfo
from safeclaw.llm.security_reviewer import ReviewEvent, SecurityFinding, SecurityReviewer

__all__ = [
    "SafeClawLLMClient",
    "create_client",
    "PROVIDERS",
    "ProviderInfo",
    "SecurityReviewer",
    "SecurityFinding",
    "ReviewEvent",
    "ClassificationObserver",
    "ClassificationSuggestion",
    "DecisionExplainer",
    "PolicyCompiler",
    "CompileResult",
]
