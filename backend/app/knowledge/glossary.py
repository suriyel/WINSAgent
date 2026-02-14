"""Expert glossary manager for telecom terminology and synonym mapping.

Loads JSON/CSV glossary files and provides query expansion
and term matching for reranker score boosting.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class GlossaryManager:
    """Manages expert terminology and synonym mappings.

    Glossary files are stored in corpus_glossary_dir and loaded on startup.

    Supported formats:
    - JSON: {"terms": [{"term": "...", "definition": "..."}],
             "synonyms": {"canonical": ["alias1", "alias2"]}}
    - CSV: columns "term,definition" or "canonical,alias"
    """

    def __init__(self) -> None:
        self.terms: dict[str, str] = {}         # term → definition
        self.synonyms: dict[str, list[str]] = {} # canonical → [aliases]
        self._reverse_synonyms: dict[str, str] = {}  # alias → canonical

    def reload(self) -> None:
        """Reload all glossary files from disk."""
        self.terms.clear()
        self.synonyms.clear()
        self._reverse_synonyms.clear()

        glossary_dir = Path(settings.corpus_glossary_dir)
        if not glossary_dir.exists():
            return

        for f in sorted(glossary_dir.iterdir()):
            if not f.is_file():
                continue
            try:
                if f.suffix.lower() == ".json":
                    self._load_json(f)
                elif f.suffix.lower() == ".csv":
                    self._load_csv(f)
            except Exception:
                logger.exception("Failed to load glossary file: %s", f.name)

        # Build reverse synonym map
        for canonical, aliases in self.synonyms.items():
            for alias in aliases:
                self._reverse_synonyms[alias.lower()] = canonical

        logger.info(
            "Loaded glossary: %d terms, %d synonym groups",
            len(self.terms), len(self.synonyms),
        )

    def _load_json(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))

        # Load terms
        for entry in data.get("terms", []):
            term = entry.get("term", "").strip()
            definition = entry.get("definition", "").strip()
            if term:
                self.terms[term] = definition

        # Load synonyms
        for canonical, aliases in data.get("synonyms", {}).items():
            canonical = canonical.strip()
            if canonical:
                existing = self.synonyms.get(canonical, [])
                existing.extend(a.strip() for a in aliases if a.strip())
                self.synonyms[canonical] = existing

    def _load_csv(self, path: Path) -> None:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return

            fields_lower = [fn.lower() for fn in reader.fieldnames]

            if "term" in fields_lower:
                # Term definition CSV
                for row in reader:
                    term = row.get("term", "").strip()
                    definition = row.get("definition", "").strip()
                    if term:
                        self.terms[term] = definition
            elif "canonical" in fields_lower:
                # Synonym mapping CSV
                for row in reader:
                    canonical = row.get("canonical", "").strip()
                    alias = row.get("alias", "").strip()
                    if canonical and alias:
                        self.synonyms.setdefault(canonical, []).append(alias)

    def expand_query(self, query: str) -> str:
        """Expand a query with synonym terms.

        If the query contains a known alias, append the canonical term.
        If it contains a canonical term, append aliases.
        """
        words = query.lower().split()
        expansions: set[str] = set()

        for word in words:
            # Check if word is an alias → add canonical
            if word in self._reverse_synonyms:
                expansions.add(self._reverse_synonyms[word])

            # Check if word is a canonical term → add aliases
            if word in self.synonyms:
                expansions.update(self.synonyms[word])

        if expansions:
            return query + " " + " ".join(expansions)
        return query

    def find_matching_terms(self, query: str) -> list[str]:
        """Find glossary terms that appear in the query.

        Returns a list of matching terms for reranker score boosting.
        """
        query_lower = query.lower()
        matches: list[str] = []

        for term in self.terms:
            if term.lower() in query_lower:
                matches.append(term)

        return matches


# Singleton
glossary_manager = GlossaryManager()
