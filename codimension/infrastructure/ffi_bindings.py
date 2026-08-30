# -*- coding: utf-8 -*-
#
# codimension - FFI binding extractors (R206)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Evidence-backed PyO3 / pybind11 / CPython / ``.pyi`` extractors (R206).

Uses pattern matching on source text (not a compiler). Edges always carry
:class:`~core.bindings.BindingEvidence`; name equality alone never yields
:attr:`~core.bindings.BindingPrecision.EXACT`.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable

from core.bindings import (
    BindingEdge,
    BindingEvidence,
    BindingEvidenceKind,
    BindingFramework,
    BindingPrecision,
    BindingProvider,
    PyiStubSymbol,
)
from core.symbol_index import SourceSpan

_RE_PYO3_NAME = re.compile(
    r"#\s*\[\s*pyo3\s*\(\s*name\s*=\s*\"([^\"]+)\"\s*\)\s*\]",
    re.MULTILINE,
)
_RE_PYFUNCTION = re.compile(r"#\s*\[\s*pyfunction(?:\s*\([^)]*\))?\s*\]", re.MULTILINE)
_RE_PYMODULE = re.compile(
    r"#\s*\[\s*pymodule(?:\s*\([^)]*\))?\s*\]\s*(?:pub\s+)?(?:unsafe\s+)?fn\s+(\w+)",
    re.MULTILINE,
)
_RE_FN_AFTER_ATTR = re.compile(
    r"#\s*\[\s*pyfunction(?:\s*\([^)]*\))?\s*\](?P<attrs>(?:\s*#\s*\[[^\]]+\])*)\s*"
    r"(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(?P<rust>\w+)",
    re.MULTILINE,
)
_RE_WRAP_PYFUNCTION = re.compile(r"wrap_pyfunction!\s*\(\s*(\w+)\s*,", re.MULTILINE)

_RE_PYBIND11_MODULE = re.compile(r"PYBIND11_MODULE\s*\(\s*(\w+)\s*,\s*\w+\s*\)", re.MULTILINE)
_RE_M_DEF_SYMBOL = re.compile(
    r"""\bm\.def\s*\(\s*(['"])(?P<py>[^'"]+)\1\s*,\s*&(?P<cpp>[\w:]+)\s*[,)]""",
    re.MULTILINE,
)
_RE_M_DEF_INLINE = re.compile(
    r"""\bm\.def\s*\(\s*(['"])(?P<py>[^'"]+)\1\s*,\s*\[""",
    re.MULTILINE,
)

_RE_PYMETHODDEF = re.compile(
    r"""\{\s*(['"])(?P<py>[^'"]+)\1\s*,\s*(?P<fn>\w+)\s*,\s*METH_""",
    re.MULTILINE,
)
_RE_PYINIT = re.compile(r"\bPyInit_(\w+)\s*\(", re.MULTILINE)


def _span_for_match(text: str, match: re.Match[str], group: int | str = 0) -> SourceSpan:
    """Unicode span for a regex match group."""
    return SourceSpan(match.start(group), match.end(group))


def _python_symbol(module: str, name: str) -> str:
    """Build ``python:<module>.<name>`` key."""
    mod = module.strip() or "_unknown"
    return f"python:{mod}.{name}"


def _rust_symbol(name: str) -> str:
    """Build ``rust:<name>`` key (crate path refinement is R207+)."""
    return f"rust:{name}"


def _cpp_symbol(name: str) -> str:
    """Build ``cpp:<name>`` key."""
    return f"cpp:{name}"


class PyO3BindingProvider:
    """Extract PyO3 ``#[pyfunction]`` / ``#[pyo3(name)]`` / ``wrap_pyfunction!`` edges."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.pyo3"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.PYO3

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse Rust source for evidence-backed PyO3 exports."""
        module = "_native"
        mod_m = _RE_PYMODULE.search(text)
        if mod_m is not None:
            module = mod_m.group(1)

        edges: list[BindingEdge] = []
        wrapped = {m.group(1) for m in _RE_WRAP_PYFUNCTION.finditer(text)}

        for match in _RE_FN_AFTER_ATTR.finditer(text):
            rust_name = match.group("rust")
            block = match.group(0)
            evidence: list[BindingEvidence] = [
                BindingEvidence(
                    kind=BindingEvidenceKind.PYFUNCTION_ATTR,
                    uri=uri,
                    span=_span_for_match(text, match),
                    detail="#[pyfunction]",
                )
            ]
            name_m = _RE_PYO3_NAME.search(block)
            py_name = rust_name
            if name_m is not None:
                py_name = name_m.group(1)
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYO3_NAME_ATTR,
                        uri=uri,
                        span=SourceSpan(match.start() + name_m.start(1), match.start() + name_m.end(1)),
                        detail=f'pyo3(name="{py_name}")',
                    )
                )
            if rust_name in wrapped:
                wrap_m = next(m for m in _RE_WRAP_PYFUNCTION.finditer(text) if m.group(1) == rust_name)
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.WRAP_PYFUNCTION,
                        uri=uri,
                        span=_span_for_match(text, wrap_m, 1),
                        detail=f"wrap_pyfunction!({rust_name})",
                    )
                )
            if mod_m is not None:
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYMODULE_ATTR,
                        uri=uri,
                        span=_span_for_match(text, mod_m, 1),
                        detail=f"#[pymodule] fn {module}",
                    )
                )
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=_rust_symbol(rust_name),
                    framework=BindingFramework.PYO3,
                    precision=BindingPrecision.EXACT,
                    evidence=tuple(evidence),
                    python_module=module,
                    python_name=py_name,
                    native_language_id="rust",
                    provider_id=self.provider_id,
                )
            )
        return tuple(edges)


class Pybind11BindingProvider:
    """Extract ``PYBIND11_MODULE`` + ``m.def`` edges (exact or inline)."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.pybind11"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.PYBIND11

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse C++ source for pybind11 exports."""
        module = "_native"
        mod_m = _RE_PYBIND11_MODULE.search(text)
        if mod_m is not None:
            module = mod_m.group(1)

        edges: list[BindingEdge] = []
        for match in _RE_M_DEF_SYMBOL.finditer(text):
            py_name = match.group("py")
            cpp_name = match.group("cpp")
            evidence = [
                BindingEvidence(
                    kind=BindingEvidenceKind.PYBIND11_DEF,
                    uri=uri,
                    span=_span_for_match(text, match),
                    detail=f'm.def("{py_name}", &{cpp_name})',
                )
            ]
            if mod_m is not None:
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYBIND11_MODULE,
                        uri=uri,
                        span=_span_for_match(text, mod_m, 1),
                        detail=f"PYBIND11_MODULE({module})",
                    )
                )
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=_cpp_symbol(cpp_name),
                    framework=BindingFramework.PYBIND11,
                    precision=BindingPrecision.EXACT,
                    evidence=tuple(evidence),
                    python_module=module,
                    python_name=py_name,
                    native_language_id="cpp",
                    provider_id=self.provider_id,
                )
            )
        for match in _RE_M_DEF_INLINE.finditer(text):
            py_name = match.group("py")
            # Skip if already captured as symbol form at same offset.
            if any(e.python_name == py_name and e.precision is BindingPrecision.EXACT for e in edges):
                # Same name may still be inline elsewhere; allow if span differs.
                if any(e.evidence[0].span.start == match.start() for e in edges):
                    continue
            line = text.count("\n", 0, match.start()) + 1
            col = match.start() - (text.rfind("\n", 0, match.start()) + 1)
            native = f"cpp:{uri.rsplit('/', 1)[-1]}::<lambda@{line}:{col}>"
            evidence = [
                BindingEvidence(
                    kind=BindingEvidenceKind.PYBIND11_INLINE,
                    uri=uri,
                    span=_span_for_match(text, match),
                    detail=f'm.def("{py_name}", []…)',
                )
            ]
            if mod_m is not None:
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYBIND11_MODULE,
                        uri=uri,
                        span=_span_for_match(text, mod_m, 1),
                        detail=f"PYBIND11_MODULE({module})",
                    )
                )
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=native,
                    framework=BindingFramework.PYBIND11,
                    precision=BindingPrecision.INLINE,
                    evidence=tuple(evidence),
                    python_module=module,
                    python_name=py_name,
                    native_language_id="cpp",
                    provider_id=self.provider_id,
                )
            )
        return tuple(edges)


class CPythonBindingProvider:
    """Extract ``PyMethodDef`` + ``PyInit_*`` edges."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.cpython"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.CPYTHON

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse C/C++ extension source for CPython method table exports."""
        module = "_native"
        init_m = _RE_PYINIT.search(text)
        if init_m is not None:
            module = init_m.group(1)

        edges: list[BindingEdge] = []
        for match in _RE_PYMETHODDEF.finditer(text):
            py_name = match.group("py")
            fn_name = match.group("fn")
            evidence = [
                BindingEvidence(
                    kind=BindingEvidenceKind.PYMETHODDEF,
                    uri=uri,
                    span=_span_for_match(text, match),
                    detail=f'{{"{py_name}", {fn_name}, METH_…}}',
                )
            ]
            if init_m is not None:
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYINIT,
                        uri=uri,
                        span=_span_for_match(text, init_m, 1),
                        detail=f"PyInit_{module}",
                    )
                )
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=_cpp_symbol(fn_name),
                    framework=BindingFramework.CPYTHON,
                    precision=BindingPrecision.EXACT,
                    evidence=tuple(evidence),
                    python_module=module,
                    python_name=py_name,
                    native_language_id="cpp",
                    provider_id=self.provider_id,
                )
            )
        return tuple(edges)


class PyiBridgeProvider:
    """Extract stub declarations from ``.pyi`` (bridge side; not an FFI edge alone)."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.pyi"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.PYI

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """``.pyi`` does not emit FFI edges by itself — use :meth:`extract_stubs`."""
        return ()

    def extract_stubs(self, uri: str, text: str, *, module: str = "") -> tuple[PyiStubSymbol, ...]:
        """Parse top-level function / class names from a stub file."""
        mod = module.strip()
        if not mod:
            # Derive from filename: path/_native.pyi → _native
            base = uri.rsplit("/", 1)[-1]
            if base.endswith(".pyi"):
                mod = base[: -len(".pyi")]
            else:
                mod = base or "_stub"
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ()
        stubs: list[PyiStubSymbol] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = getattr(node, "lineno", 1)
                # Approximate Unicode span via line scan.
                lines = text.splitlines(keepends=True)
                offset = sum(len(lines[i]) for i in range(max(0, start - 1)))
                name_span = SourceSpan(offset, offset + len(node.name))
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                stubs.append(
                    PyiStubSymbol(
                        module=mod,
                        name=node.name,
                        uri=uri,
                        span=name_span,
                        kind=kind,
                    )
                )
        return tuple(stubs)


def default_binding_providers() -> tuple[BindingProvider, ...]:
    """Return the built-in PyO3 / pybind11 / CPython providers."""
    return (
        PyO3BindingProvider(),
        Pybind11BindingProvider(),
        CPythonBindingProvider(),
    )


def extract_all_bindings(
    uri: str, text: str, providers: Iterable[BindingProvider] | None = None
) -> tuple[BindingEdge, ...]:
    """Run all (or given) providers and concatenate edges."""
    out: list[BindingEdge] = []
    for provider in providers if providers is not None else default_binding_providers():
        out.extend(provider.extract(uri, text))
    return tuple(out)


__all__ = [
    "CPythonBindingProvider",
    "PyO3BindingProvider",
    "Pybind11BindingProvider",
    "PyiBridgeProvider",
    "default_binding_providers",
    "extract_all_bindings",
]
