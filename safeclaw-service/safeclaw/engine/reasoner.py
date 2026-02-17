"""OWL reasoner wrapper - runs owlready2 + HermiT for pre-computation."""

import logging
from pathlib import Path

logger = logging.getLogger("safeclaw.reasoner")


class OWLReasoner:
    """Wraps owlready2 for OWL reasoning with HermiT.

    Runs HermiT once at startup to pre-compute inferences.
    All real-time queries go against the pre-computed model.
    """

    def __init__(self, ontology_dir: Path):
        self.ontology_dir = ontology_dir
        self._world = None
        self._ontology = None

    def initialize(self, run_reasoner: bool = True) -> None:
        """Load ontologies and optionally run HermiT reasoner."""
        try:
            import owlready2

            self._world = owlready2.World()
            # Load all .owl and .ttl files
            for owl_file in self.ontology_dir.glob("*.ttl"):
                logger.info(f"Loading ontology: {owl_file.name}")
                self._ontology = self._world.get_ontology(str(owl_file)).load()

            if run_reasoner and self._ontology:
                logger.info("Running HermiT reasoner (one-time pre-computation)...")
                with self._ontology:
                    owlready2.sync_reasoner_hermit(self._world)
                logger.info("Reasoning complete")
        except ImportError:
            logger.warning("owlready2 not installed, reasoner disabled")
        except Exception as e:
            logger.warning(f"Reasoner initialization failed: {e}")

    @property
    def world(self):
        return self._world

    @property
    def ontology(self):
        return self._ontology
