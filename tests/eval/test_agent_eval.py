"""Eval-suite placeholder. Real projects wire DeepEval/RAGAS metrics here
(faithfulness, answer-relevancy, classification accuracy against a golden set)
and run them in CI as a quality gate. Kept as a skipped scaffold so the eval
tier exists from day one without requiring an LLM key in unit CI."""
import pytest

pytest.skip(
    "Eval suite requires a live LLM key; run in the eval CI stage.",
    allow_module_level=True,
)
