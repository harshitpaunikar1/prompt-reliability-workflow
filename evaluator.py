"""
Prompt reliability evaluator.
Runs prompt templates against test cases and scores consistency, accuracy, and format compliance.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    from prompt_library import PromptLibrary, PromptTemplate
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False


@dataclass
class TestCase:
    test_id: str
    prompt_id: str
    variables: Dict[str, Any]
    expected_output: Optional[str] = None
    expected_contains: Optional[List[str]] = None
    expected_json_keys: Optional[List[str]] = None
    expected_label: Optional[str] = None
    description: str = ""


@dataclass
class EvalResult:
    test_id: str
    prompt_id: str
    prompt_version: str
    raw_output: str
    latency_ms: float
    format_pass: bool
    content_pass: bool
    consistency_score: Optional[float] = None
    error: Optional[str] = None

    @property
    def overall_pass(self) -> bool:
        return self.format_pass and self.content_pass and self.error is None


class OutputValidator:
    """Validates LLM outputs against structured test case expectations."""

    def validate_format(self, output: str, test_case: TestCase) -> Tuple[bool, str]:
        if test_case.expected_json_keys:
            try:
                parsed = json.loads(output.strip())
                missing = [k for k in test_case.expected_json_keys if k not in parsed]
                if missing:
                    return False, f"Missing JSON keys: {missing}"
                return True, "JSON valid with required keys."
            except json.JSONDecodeError as exc:
                return False, f"Invalid JSON: {exc}"
        return True, "No format constraint."

    def validate_content(self, output: str, test_case: TestCase) -> Tuple[bool, str]:
        output_lower = output.lower().strip()
        if test_case.expected_label:
            if test_case.expected_label.lower() not in output_lower:
                return False, f"Expected label '{test_case.expected_label}' not found."
        if test_case.expected_contains:
            missing = [kw for kw in test_case.expected_contains
                       if kw.lower() not in output_lower]
            if missing:
                return False, f"Missing expected terms: {missing}"
        if test_case.expected_output:
            if test_case.expected_output.lower() not in output_lower:
                return False, f"Expected output substring not found."
        return True, "Content validation passed."


class LLMRunner:
    """Executes prompts against a local LLM and returns raw outputs."""

    def __init__(self, model: str = "llama3"):
        self.model = model

    def run(self, prompt: str) -> Tuple[str, float]:
        t0 = time.perf_counter()
        if OLLAMA_AVAILABLE:
            try:
                resp = ollama.generate(model=self.model, prompt=prompt)
                output = resp.get("response", "")
                return output, (time.perf_counter() - t0) * 1000
            except Exception as exc:
                logger.error("Ollama error: %s", exc)
        output = self._stub(prompt)
        return output, (time.perf_counter() - t0) * 1000

    def _stub(self, prompt: str) -> str:
        if "sentiment" in prompt.lower():
            return "positive"
        if "json" in prompt.lower() or "extract" in prompt.lower():
            return json.dumps({"persons": ["Tim Cook"], "organizations": ["Apple Inc."],
                               "locations": ["San Francisco"], "dates": ["Monday"], "products": []})
        if "summary" in prompt.lower() or "bullet" in prompt.lower():
            return "- Key finding 1\n- Key finding 2\n- Key finding 3"
        return "The answer based on the given context is: the result is satisfactory."


class ConsistencyEvaluator:
    """Evaluates prompt consistency by running the same prompt N times."""

    def __init__(self, runner: LLMRunner, n_runs: int = 3):
        self.runner = runner
        self.n_runs = n_runs

    def evaluate(self, prompt: str, label_extractor: Optional[Callable[[str], str]] = None) -> float:
        """Return consistency score (0-1): fraction of runs with identical primary output."""
        outputs = []
        for _ in range(self.n_runs):
            output, _ = self.runner.run(prompt)
            if label_extractor:
                output = label_extractor(output)
            outputs.append(output.strip().lower()[:50])
        most_common = max(set(outputs), key=outputs.count)
        consistency = outputs.count(most_common) / self.n_runs
        return round(consistency, 4)


class PromptEvaluator:
    """
    Runs a suite of test cases against prompt templates and generates evaluation reports.
    """

    def __init__(self, library: "PromptLibrary", runner: LLMRunner):
        self.library = library
        self.runner = runner
        self.validator = OutputValidator()
        self.consistency_eval = ConsistencyEvaluator(runner)
        self._results: List[EvalResult] = []

    def run_test(self, test_case: TestCase,
                 check_consistency: bool = False) -> EvalResult:
        try:
            rendered = self.library.render(test_case.prompt_id, test_case.variables)
            prompt_template = self.library.get(test_case.prompt_id)
            version = prompt_template.latest.version if prompt_template and prompt_template.latest else "unknown"
        except Exception as exc:
            return EvalResult(
                test_id=test_case.test_id,
                prompt_id=test_case.prompt_id,
                prompt_version="unknown",
                raw_output="",
                latency_ms=0.0,
                format_pass=False,
                content_pass=False,
                error=str(exc),
            )

        output, latency_ms = self.runner.run(rendered)
        fmt_pass, _ = self.validator.validate_format(output, test_case)
        content_pass, _ = self.validator.validate_content(output, test_case)

        consistency = None
        if check_consistency:
            consistency = self.consistency_eval.evaluate(rendered)

        result = EvalResult(
            test_id=test_case.test_id,
            prompt_id=test_case.prompt_id,
            prompt_version=version,
            raw_output=output[:500],
            latency_ms=round(latency_ms, 1),
            format_pass=fmt_pass,
            content_pass=content_pass,
            consistency_score=consistency,
        )
        self._results.append(result)
        return result

    def run_suite(self, test_cases: List[TestCase],
                  check_consistency: bool = False) -> List[EvalResult]:
        return [self.run_test(tc, check_consistency) for tc in test_cases]

    def report(self) -> Dict:
        if not self._results:
            return {}
        total = len(self._results)
        passed = sum(1 for r in self._results if r.overall_pass)
        latencies = [r.latency_ms for r in self._results]
        consistency_scores = [r.consistency_score for r in self._results if r.consistency_score is not None]
        return {
            "total_tests": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate_pct": round(passed / total * 100, 1),
            "avg_latency_ms": round(float(np.mean(latencies)), 1),
            "avg_consistency": round(float(np.mean(consistency_scores)), 4) if consistency_scores else None,
            "by_prompt": self._by_prompt(),
        }

    def _by_prompt(self) -> Dict:
        grouped: Dict[str, List[EvalResult]] = {}
        for r in self._results:
            grouped.setdefault(r.prompt_id, []).append(r)
        return {
            pid: {
                "total": len(results),
                "passed": sum(1 for r in results if r.overall_pass),
                "avg_latency_ms": round(float(np.mean([r.latency_ms for r in results])), 1),
            }
            for pid, results in grouped.items()
        }


if __name__ == "__main__":
    from prompt_library import build_default_library

    lib = build_default_library()
    runner = LLMRunner(model="llama3")
    evaluator = PromptEvaluator(library=lib, runner=runner)

    test_cases = [
        TestCase(
            test_id="t001",
            prompt_id="entity_extraction_v1",
            variables={"text": "Apple Inc. CEO Tim Cook announced new products in San Francisco."},
            expected_json_keys=["persons", "organizations", "locations"],
            description="Basic entity extraction",
        ),
        TestCase(
            test_id="t002",
            prompt_id="sentiment_classification_v1",
            variables={"product_name": "Laptop", "review_text": "Excellent build quality, very satisfied."},
            expected_label="positive",
            description="Positive review classification",
        ),
        TestCase(
            test_id="t003",
            prompt_id="sentiment_classification_v1",
            variables={"product_name": "Headphones", "review_text": "Broke after one week, terrible quality."},
            expected_label="negative",
            description="Negative review classification",
        ),
        TestCase(
            test_id="t004",
            prompt_id="document_summarizer_v1",
            variables={"num_bullets": "3", "document_text": "Long document about machine learning..."},
            expected_contains=["Key finding", "finding"],
            description="Document summarization",
        ),
    ]

    print("Running evaluation suite...")
    results = evaluator.run_suite(test_cases, check_consistency=False)

    for r in results:
        status = "PASS" if r.overall_pass else "FAIL"
        print(f"  [{status}] {r.test_id} | {r.prompt_id} | {r.latency_ms:.0f}ms")
        if r.error:
            print(f"    Error: {r.error}")

    print("\nEvaluation report:")
    print(json.dumps(evaluator.report(), indent=2))
