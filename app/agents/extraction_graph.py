"""LangGraph document-processing agent.

Flow: **ocr** -> **extract** (LLM or regex) -> **validate** (deterministic) ->
route to **erp** (valid) or **exception** (invalid).

The graph makes the hybrid split explicit: the LLM lives only in the ``extract``
node; the ``validate`` node is pure deterministic code and is what decides
routing. The model never decides whether its own extraction is correct.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.extraction.extractor import Extractor
from app.schemas import InvoiceData, ValidationIssue
from app.validation.validator import validate_invoice


class DocState(TypedDict, total=False):
    raw_text: str
    tolerance: float
    invoice: InvoiceData
    extracted_by: str
    issues: list[ValidationIssue]
    route: str  # "erp" | "exception"


def _extract_node(state: DocState, extractor: Extractor) -> DocState:
    invoice = extractor.extract(state["raw_text"])
    return {**state, "invoice": invoice, "extracted_by": extractor.name}


def _validate_node(state: DocState) -> DocState:
    issues = validate_invoice(state["invoice"], tolerance=state.get("tolerance", 0.02))
    return {**state, "issues": issues, "route": "exception" if issues else "erp"}


def _route(state: DocState) -> str:
    return state["route"]


def build_extraction_graph(extractor: Extractor):
    graph = StateGraph(DocState)
    graph.add_node("extract", lambda s: _extract_node(s, extractor))
    graph.add_node("validate", _validate_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", "validate")
    # Terminal routing decided by deterministic validation, not the LLM.
    graph.add_conditional_edges("validate", _route, {"erp": END, "exception": END})
    return graph.compile()
