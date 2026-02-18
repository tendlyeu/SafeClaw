"""Graph builder - generates D3-compatible JSON from the knowledge graph."""

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SC, SP, SU


class GraphBuilder:
    """Walks the knowledge graph and produces a D3-compatible node/edge structure."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self._cached_graph: dict | None = None
        self._cache_valid: bool = False

    def invalidate_cache(self) -> None:
        """Invalidate the cached graph when KG changes."""
        self._cache_valid = False
        self._cached_graph = None

    def build_graph(self, max_depth: int = 10) -> dict:
        """Build a D3-compatible graph from the knowledge graph."""
        if self._cache_valid and self._cached_graph is not None:
            return self._cached_graph
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
        self._cached_graph = result
        self._cache_valid = True
        return result

    def search_nodes(self, query: str) -> list[dict]:
        """Fuzzy search for nodes by name or label."""
        query_lower = query.lower()
        graph = self.build_graph()  # uses cache if valid
        return [
            n for n in graph["nodes"]
            if query_lower in n["name"].lower() or query_lower in n["label"].lower()
        ]
