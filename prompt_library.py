"""
Prompt library for the prompt reliability workflow.
Manages versioned prompt templates with metadata, rendering, and change tracking.
"""
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PromptCategory(str, Enum):
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    GENERATION = "generation"
    REASONING = "reasoning"
    QA = "qa"


@dataclass
class PromptVersion:
    version: str
    template: str
    variables: List[str]
    created_at: float
    notes: str = ""
    deprecated: bool = False

    def checksum(self) -> str:
        return hashlib.sha256(self.template.encode()).hexdigest()[:12]


@dataclass
class PromptTemplate:
    prompt_id: str
    name: str
    category: PromptCategory
    description: str
    versions: List[PromptVersion] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    owner: str = ""

    def add_version(self, template: str, notes: str = "") -> PromptVersion:
        variables = self._extract_variables(template)
        version_num = f"v{len(self.versions) + 1}.0"
        pv = PromptVersion(
            version=version_num,
            template=template,
            variables=variables,
            created_at=time.time(),
            notes=notes,
        )
        self.versions.append(pv)
        return pv

    def _extract_variables(self, template: str) -> List[str]:
        return list(set(re.findall(r"\{\{(\w+)\}\}", template)))

    @property
    def latest(self) -> Optional[PromptVersion]:
        active = [v for v in self.versions if not v.deprecated]
        return active[-1] if active else None

    def render(self, variables: Dict[str, Any], version: Optional[str] = None) -> str:
        if version:
            pv = next((v for v in self.versions if v.version == version), None)
        else:
            pv = self.latest
        if pv is None:
            raise ValueError(f"No active version found for prompt {self.prompt_id}")
        result = pv.template
        for k, v in variables.items():
            result = result.replace(f"{{{{{k}}}}}", str(v))
        missing = re.findall(r"\{\{(\w+)\}\}", result)
        if missing:
            raise ValueError(f"Missing variables in prompt {self.prompt_id}: {missing}")
        return result

    def to_dict(self) -> Dict:
        return {
            "prompt_id": self.prompt_id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "tags": self.tags,
            "owner": self.owner,
            "num_versions": len(self.versions),
            "latest_version": self.latest.version if self.latest else None,
        }


class PromptLibrary:
    """
    Registry for managing versioned prompt templates.
    Supports CRUD operations, search, and JSON export.
    """

    def __init__(self):
        self._prompts: Dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        self._prompts[template.prompt_id] = template

    def get(self, prompt_id: str) -> Optional[PromptTemplate]:
        return self._prompts.get(prompt_id)

    def list_prompts(self, category: Optional[PromptCategory] = None,
                     tag: Optional[str] = None) -> List[PromptTemplate]:
        prompts = list(self._prompts.values())
        if category:
            prompts = [p for p in prompts if p.category == category]
        if tag:
            prompts = [p for p in prompts if tag in p.tags]
        return prompts

    def search(self, query: str) -> List[PromptTemplate]:
        q = query.lower()
        return [
            p for p in self._prompts.values()
            if q in p.name.lower() or q in p.description.lower()
            or any(q in t for t in p.tags)
        ]

    def add_version(self, prompt_id: str, template_str: str,
                     notes: str = "") -> Optional[PromptVersion]:
        pt = self.get(prompt_id)
        if not pt:
            return None
        return pt.add_version(template_str, notes=notes)

    def deprecate_version(self, prompt_id: str, version: str) -> bool:
        pt = self.get(prompt_id)
        if not pt:
            return False
        for v in pt.versions:
            if v.version == version:
                v.deprecated = True
                return True
        return False

    def render(self, prompt_id: str, variables: Dict[str, Any],
               version: Optional[str] = None) -> str:
        pt = self.get(prompt_id)
        if not pt:
            raise KeyError(f"Prompt '{prompt_id}' not found.")
        return pt.render(variables, version=version)

    def export_json(self) -> str:
        return json.dumps(
            [p.to_dict() for p in self._prompts.values()],
            indent=2, default=str
        )

    def stats(self) -> Dict:
        by_category: Dict[str, int] = {}
        for p in self._prompts.values():
            cat = p.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total_prompts": len(self._prompts),
            "by_category": by_category,
        }


def build_default_library() -> PromptLibrary:
    """Bootstrap a library with common prompt templates."""
    lib = PromptLibrary()

    entity_extraction = PromptTemplate(
        prompt_id="entity_extraction_v1",
        name="Entity Extraction",
        category=PromptCategory.EXTRACTION,
        description="Extracts named entities from unstructured text.",
        tags=["ner", "extraction", "entities"],
        owner="nlp_team",
    )
    entity_extraction.add_version(
        template="""Extract all named entities from the following text.
Return a JSON object with keys: persons, organizations, locations, dates, products.

Text: {{text}}

JSON:""",
        notes="Initial version using zero-shot extraction.",
    )
    lib.register(entity_extraction)

    sentiment = PromptTemplate(
        prompt_id="sentiment_classification_v1",
        name="Sentiment Classification",
        category=PromptCategory.CLASSIFICATION,
        description="Classifies customer feedback sentiment.",
        tags=["sentiment", "classification", "customer"],
        owner="analytics_team",
    )
    sentiment.add_version(
        template="""Classify the sentiment of the following customer review.
Respond with exactly one of: positive, negative, neutral.

Product: {{product_name}}
Review: {{review_text}}

Sentiment:""",
        notes="Single-label sentiment with product context.",
    )
    lib.register(sentiment)

    summarizer = PromptTemplate(
        prompt_id="document_summarizer_v1",
        name="Document Summarizer",
        category=PromptCategory.SUMMARIZATION,
        description="Summarizes long documents in bullet points.",
        tags=["summary", "document", "bullets"],
    )
    summarizer.add_version(
        template="""Summarize the following document in {{num_bullets}} bullet points.
Each bullet should capture a key insight or finding.

Document:
{{document_text}}

Summary:""",
        notes="Configurable bullet count summarizer.",
    )
    lib.register(summarizer)

    return lib


if __name__ == "__main__":
    lib = build_default_library()
    print(f"Library initialized with {lib.stats()['total_prompts']} prompts")
    print("By category:", lib.stats()["by_category"])

    rendered = lib.render("entity_extraction_v1", {
        "text": "Apple Inc. CEO Tim Cook announced new products in San Francisco on Monday."
    })
    print("\nRendered entity extraction prompt:")
    print(rendered)

    sentiment_rendered = lib.render("sentiment_classification_v1", {
        "product_name": "Wireless Headphones",
        "review_text": "Sound quality is excellent but the battery drains too fast.",
    })
    print("\nRendered sentiment prompt:")
    print(sentiment_rendered)

    lib.add_version(
        "sentiment_classification_v1",
        template="""You are a sentiment analysis expert. Classify sentiment as positive, negative, or neutral.
Consider intensity: strongly_positive, positive, neutral, negative, strongly_negative.

Product: {{product_name}}
Review: {{review_text}}

Sentiment:""",
        notes="Added intensity scale in v2.",
    )
    pt = lib.get("sentiment_classification_v1")
    print(f"\nSentiment prompt now has {len(pt.versions)} versions.")
    print("Export JSON snippet:", lib.export_json()[:300])
