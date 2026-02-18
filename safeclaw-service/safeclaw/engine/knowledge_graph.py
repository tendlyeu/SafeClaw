"""Knowledge graph manager - loads and queries OWL ontologies via RDFLib."""

from pathlib import Path

from rdflib import Graph, Namespace

SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")
SP = Namespace("http://safeclaw.uku.ai/ontology/policy#")
SU = Namespace("http://safeclaw.uku.ai/ontology/user#")


class KnowledgeGraph:
    """Manages the RDF knowledge graph for SafeClaw."""

    def __init__(self):
        self.graph = Graph()
        self.graph.bind("sc", SC)
        self.graph.bind("sp", SP)
        self.graph.bind("su", SU)

    def load_ontology(self, path: Path) -> None:
        self.graph.parse(str(path), format="turtle")

    def load_directory(self, directory: Path) -> None:
        for ttl_file in directory.rglob("*.ttl"):
            try:
                self.load_ontology(ttl_file)
            except Exception as e:
                import logging
                logging.getLogger("safeclaw.kg").error(f"Failed to parse {ttl_file}: {e}")
                continue

    def query(self, sparql: str) -> list[dict]:
        results = self.graph.query(sparql)
        var_names = [str(v) for v in results.vars] if results.vars else []
        return [dict(zip(var_names, row)) for row in results]

    def add_triple(self, subject, predicate, obj) -> None:
        self.graph.add((subject, predicate, obj))

    def __len__(self) -> int:
        return len(self.graph)
