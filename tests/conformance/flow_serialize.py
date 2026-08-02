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
    doc = getattr(frag, "docstring", None)
    if doc is not None and hasattr(doc, "getDisplayValue"):
        node["docstring"] = doc.getDisplayValue()
    if getattr(frag, "isAsync", False):
        node["isAsync"] = True
    if getattr(frag, "isComprehension", False):
        node["isComprehension"] = True
    with_items = getattr(frag, "withItems", None)
    if with_items:
        node["withItems"] = list(with_items)
    leading = getattr(frag, "leadingComment", None)
    if leading is not None and hasattr(leading, "getDisplayValue"):
        node["leadingComment"] = leading.getDisplayValue()
    side = getattr(frag, "sideComment", None)
    if side is not None and hasattr(side, "getDisplayValue"):
        node["sideComment"] = side.getDisplayValue()
    def _cml_list(items: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "recordType": getattr(c, "recordType", ""),
                "version": getattr(c, "version", 0),
                "display": c.getDisplayValue() if hasattr(c, "getDisplayValue") else "",
            }
            for c in items
        ]

    leading_cml = getattr(frag, "leadingCMLComments", None) or []
    if leading_cml:
        node["leadingCML"] = _cml_list(leading_cml)
    side_cml = getattr(frag, "sideCMLComments", None) or []
    if side_cml:
        node["sideCML"] = _cml_list(side_cml)

    children: list[dict[str, Any]] = []
    for child in getattr(frag, "nsuite", []) or []:
        children.append(_serialize_fragment(child))
    # Only control-flow branch parts (If/Match), not comment .parts lists
    kind_name = _kind_name(getattr(frag, "kind", -1))
    if kind_name in ("If", "Match"):
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
    bang = None
    if cf.bangLine is not None:
        bang = {"begin": cf.bangLine.begin, "end": cf.bangLine.end, "beginLine": cf.bangLine.beginLine}
    enc = None
    if cf.encodingLine is not None:
        enc = {
            "begin": cf.encodingLine.begin,
            "end": cf.encodingLine.end,
            "beginLine": cf.encodingLine.beginLine,
        }
    leading = None
    if cf.leadingComment is not None and hasattr(cf.leadingComment, "getDisplayValue"):
        leading = cf.leadingComment.getDisplayValue()
    return {
        "version": 1,
        "errors": [[e[0], e[1], e[2]] for e in cf.errors],
        "docstring": doc,
        "bangLine": bang,
        "encodingLine": enc,
        "leadingComment": leading,
        "nsuite": [_serialize_fragment(f) for f in cf.nsuite],
    }
