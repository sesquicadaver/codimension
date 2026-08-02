# -*- coding: utf-8 -*-
"""Stable JSON serialization of flow_ast control-flow trees (T005)."""

from __future__ import annotations

import importlib.util
import os.path
from typing import Any

_FLOW_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "codimension",
    "parsers",
    "flow_ast.py",
)
_spec = importlib.util.spec_from_file_location("flow_ast_conformance", _FLOW_PATH)
_flow_ast = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_flow_ast)

getControlFlowFromMemory = _flow_ast.getControlFlowFromMemory
_KIND_NAMES = getattr(_flow_ast, "_KIND_NAMES", {})


def _kind_name(kind: int) -> str:
    return _KIND_NAMES.get(kind, f"kind:{kind}")


def _serialize_fragment(frag: Any) -> dict[str, Any]:
    """Serialize one fragment node to a JSON-stable dict."""
    begin, end = frag.getAbsPosRange()
    bln, eln = frag.getLineRange()
    body = frag.body
    node: dict[str, Any] = {
        "kind": _kind_name(frag.kind),
        "kind_id": int(frag.kind),
        "begin": begin,
        "end": end,
        "beginLine": bln,
        "endLine": eln,
        "beginPos": body.beginPos,
        "endPos": body.endPos,
        "display": frag.getDisplayValue(),
    }
    name = getattr(frag, "name", None)
    if name is not None and hasattr(name, "getContent"):
        node["name"] = name.getContent()

    children: list[dict[str, Any]] = []
    for child in getattr(frag, "nsuite", []) or []:
        children.append(_serialize_fragment(child))
    for part in getattr(frag, "parts", []) or []:
        children.append({"role": "part", **_serialize_fragment(part)})
    else_part = getattr(frag, "elsePart", None)
    if else_part is not None:
        children.append({"role": "else", **_serialize_fragment(else_part)})
    for ep in getattr(frag, "exceptParts", []) or []:
        children.append({"role": "except", **_serialize_fragment(ep)})
    finally_part = getattr(frag, "finallyPart", None)
    if finally_part is not None:
        children.append({"role": "finally", **_serialize_fragment(finally_part)})
    for dec in getattr(frag, "decorators", []) or []:
        children.append({"role": "decorator", **_serialize_fragment(dec)})

    if children:
        node["children"] = children
    return node


def serialize_control_flow(source: str) -> dict[str, Any]:
    """Parse ``source`` and return a stable snapshot dict."""
    cf = getControlFlowFromMemory(source)
    doc = None
    if cf.docstring is not None:
        doc = cf.docstring.getDisplayValue()
    return {
        "version": 1,
        "errors": [[e[0], e[1], e[2]] for e in cf.errors],
        "docstring": doc,
        "nsuite": [_serialize_fragment(f) for f in cf.nsuite],
    }
