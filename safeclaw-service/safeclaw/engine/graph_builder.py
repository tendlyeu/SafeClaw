"""Graph builder - generates D3-compatible JSON from the knowledge graph."""

import itertools
import weakref

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP, SU

# Monotonically increasing generation counter to avoid cache collisions
# when a KnowledgeGraph is freed and a new one gets the same id().
_generation_counter = itertools.count()

# Class-level cache keyed by (generation, triple count) so that
# the cache survives across per-request GraphBuilder instances while still
# invalidating when the underlying graph changes (e.g. after /reload).
_graph_cache: dict[tuple[int, int], dict] = {}

# Maps KnowledgeGraph id() to its assigned generation number.
# When a KG is garbage-collected and a new one gets the same address,
# the new KG gets a different generation, preventing stale cache hits.
_kg_generations: dict[int, int] = {}


def _get_generation(kg: KnowledgeGraph) -> int:
    """Get or assign a generation number for a KnowledgeGraph instance.

    Each unique KnowledgeGraph object gets a unique generation number.
    A weak-reference finalizer automatically removes the entry when the
    KG is garbage-collected, so a new KG that reuses the same ``id()``
    will always receive a fresh generation number.
    """
    kg_id = id(kg)
    if kg_id not in _kg_generations:
        _kg_generations[kg_id] = next(_generation_counter)
        weakref.finalize(kg, _kg_generations.pop, kg_id, None)
    return _kg_generations[kg_id]


class GraphBuilder:
    """Walks the knowledge graph and produces a D3-compatible node/edge structure."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self._generation = _get_generation(knowledge_graph)

    def invalidate_cache(self) -> None:
        """Invalidate the cached graph so it will be rebuilt on next access."""
        cache_key = (self._generation, len(self.kg))
        _graph_cache.pop(cache_key, None)
        # Also remove the generation mapping so a new GraphBuilder for the
        # same KG (after reload) gets a fresh generation.
        _kg_generations.pop(id(self.kg), None)

    @staticmethod
    def invalidate_all_caches() -> None:
        """Invalidate all cached graphs."""
        _graph_cache.clear()
        _kg_generations.clear()

    def build_graph(self) -> dict:
        """Build a D3-compatible graph from the knowledge graph."""
        cache_key = (self._generation, len(self.kg))
        cached = _graph_cache.get(cache_key)
        if cached is not None:
            return cached

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_nodes: set[str] = set()

        # Classes (circles)
        class_results = self.kg.query("""
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?class ?label ?parent WHERE {
                ?class a owl:Class .
                OPTIONAL { ?class rdfs:label ?label }
                OPTIONAL { ?class rdfs:subClassOf ?parent }
            }
        """)

        for row in class_results:
            uri = str(row["class"])
            name = uri.split("#")[-1].split("/")[-1]
            if name.startswith("_:") or not name:
                continue
            label = str(row.get("label", name) or name)

            if uri not in seen_nodes:
                node_type = "class"
                if uri.startswith(str(SP)):
                    node_type = "policy"
                elif uri.startswith(str(SU)):
                    node_type = "preference"
                nodes.append({
                    "id": uri,
                    "name": name,
                    "label": label,
                    "type": node_type,
                })
                seen_nodes.add(uri)

            parent = row.get("parent")
            if parent:
                parent_uri = str(parent)
                if not parent_uri.startswith("_:"):
                    edges.append({
                        "source": uri,
                        "target": parent_uri,
                        "type": "subClassOf",
                    })

        # Individuals (instances)
        instance_results = self.kg.query("""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?instance ?type ?label WHERE {
                ?instance rdf:type ?type .
                OPTIONAL { ?instance rdfs:label ?label }
                FILTER(!isBlank(?instance))
            }
        """)

        for row in instance_results:
            uri = str(row["instance"])
            name = uri.split("#")[-1].split("/")[-1]
            if not name or uri.startswith("http://www.w3.org"):
                continue
            label = str(row.get("label", name) or name)
            type_uri = str(row["type"])

            if uri not in seen_nodes:
                node_type = "instance"
                if "Prohibition" in type_uri or "Constraint" in type_uri:
                    node_type = "policy"
                elif "Preference" in type_uri or "User" in type_uri:
                    node_type = "preference"
                nodes.append({
                    "id": uri,
                    "name": name,
                    "label": label,
                    "type": node_type,
                })
                seen_nodes.add(uri)

            edges.append({
                "source": uri,
                "target": type_uri,
                "type": "instanceOf",
            })

        result = {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_triples": len(self.kg),
            },
        }
        _graph_cache[cache_key] = result
        return result

    def search_nodes(self, query: str) -> list[dict]:
        """Fuzzy search for nodes by name or label."""
        query_lower = query.lower()
        graph = self.build_graph()
        return [
            n for n in graph["nodes"]
            if query_lower in n["name"].lower() or query_lower in n["label"].lower()
        ]
