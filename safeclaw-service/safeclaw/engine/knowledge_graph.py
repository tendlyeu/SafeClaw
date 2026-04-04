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
        self.failed_files: list[str] = []

    def load_ontology(self, path: Path) -> None:
        self.graph.parse(str(path), format="turtle")

    def load_directory(self, directory: Path) -> None:
        for ttl_file in directory.rglob("*.ttl"):
            try:
                self.load_ontology(ttl_file)
            except Exception as e:
                import logging

                logging.getLogger("safeclaw.kg").error(f"Failed to parse {ttl_file}: {e}")
                self.failed_files.append(str(ttl_file))
                continue

    def query(self, sparql: str) -> list[dict]:
        results = self.graph.query(sparql)
        var_names = [str(v) for v in results.vars] if results.vars else []
        return [dict(zip(var_names, row)) for row in results]

    def add_triple(self, subject, predicate, obj) -> None:
        self.graph.add((subject, predicate, obj))

    def get_failed_files(self) -> list[str]:
        """Return list of file paths that failed to load."""
        return list(self.failed_files)

    def is_healthy(self) -> bool:
        """Return False if any ontology files failed to load."""
        return len(self.failed_files) == 0

    def __len__(self) -> int:
        return len(self.graph)
