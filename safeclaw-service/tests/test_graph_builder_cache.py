"""Tests for graph_builder cache keyed by id() — issue #143.

Verifies that weakref.finalize auto-cleans stale _kg_generations entries
so a new KnowledgeGraph that reuses the same id() gets a fresh generation.
"""

import gc

from safeclaw.engine.graph_builder import (
    GraphBuilder,
    _get_generation,
    _kg_generations,
)
from safeclaw.engine.knowledge_graph import KnowledgeGraph


def test_new_kg_gets_fresh_generation_even_if_same_id():
    """A new KG must get a fresh generation even if it reuses the same id().

    Before the fix, the stale entry in _kg_generations would persist after
    the old KG was GC'd, causing the new KG to silently reuse the old
    generation number and potentially hit stale cache entries.
    """
    kg1 = KnowledgeGraph()
    gen1 = _get_generation(kg1)
    kg1_id = id(kg1)

    # Drop all references and force garbage collection
    del kg1
    gc.collect()

    # The finalizer should have cleaned up the stale entry
    assert kg1_id not in _kg_generations, "_kg_generations should not contain the old id after GC"

    # Create a new KG — CPython often reuses the same address
    kg2 = KnowledgeGraph()
    gen2 = _get_generation(kg2)

    # Even if id(kg2) == kg1_id, the generation must be different
    assert gen2 != gen1, f"New KG got stale generation {gen1}; expected a fresh one"


def test_generation_stable_while_kg_alive():
    """Multiple calls to _get_generation on the same KG return the same value."""
    kg = KnowledgeGraph()
    gen_a = _get_generation(kg)
    gen_b = _get_generation(kg)
    assert gen_a == gen_b


def test_invalidate_cache_removes_generation():
    """GraphBuilder.invalidate_cache removes the generation mapping."""
    kg = KnowledgeGraph()
    builder = GraphBuilder(kg)
    kg_id = id(kg)

    assert kg_id in _kg_generations
    builder.invalidate_cache()
    assert kg_id not in _kg_generations


def test_invalidate_all_caches_clears_generations():
    """GraphBuilder.invalidate_all_caches clears all generation mappings."""
    kg1 = KnowledgeGraph()
    kg2 = KnowledgeGraph()
    _get_generation(kg1)
    _get_generation(kg2)

    assert len(_kg_generations) >= 2
    GraphBuilder.invalidate_all_caches()
    assert len(_kg_generations) == 0


def test_two_live_kgs_get_different_generations():
    """Two concurrently live KnowledgeGraphs always get distinct generations."""
    kg1 = KnowledgeGraph()
    kg2 = KnowledgeGraph()
    gen1 = _get_generation(kg1)
    gen2 = _get_generation(kg2)
    assert gen1 != gen2
