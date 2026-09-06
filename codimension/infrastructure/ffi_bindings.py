# -*- coding: utf-8 -*-
#
# codimension - FFI binding extractors (R206 / R217)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Evidence-backed PyO3 / pybind11 / CPython / ``.pyi`` extractors (R206 / R217).

Uses pattern matching on source text (not a compiler). Edges always carry
:class:`~core.bindings.BindingEvidence`; name equality alone never yields
:attr:`~core.bindings.BindingPrecision.EXACT`.

R217: ``EXACT`` only when a full registration chain is present; otherwise
``BRIDGE`` (or ``INLINE`` for pybind11 lambdas).
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

_RE_PYBIND11_MODULE = re.compile(
    r"PYBIND11_MODULE\s*\(\s*(?P<mod>\w+)\s*,\s*(?P<var>\w+)\s*\)",
    re.MULTILINE,
)

_RE_PYMETHODDEF_TABLE = re.compile(
    r"(?:static\s+)?PyMethodDef\s+(?P<table>\w+)\s*\[",
    re.MULTILINE,
)
_RE_PYMETHODDEF = re.compile(
    r"""\{\s*(['"])(?P<py>[^'"]+)\1\s*,\s*(?P<fn>\w+)\s*,\s*METH_""",
    re.MULTILINE,
)
_RE_PYINIT = re.compile(r"\bPyInit_(\w+)\s*\(", re.MULTILINE)
_RE_PYMODULEDEF = re.compile(r"(?:static\s+)?PyModuleDef\s+(?P<def>\w+)\s*=", re.MULTILINE)
_RE_MMETHODS = re.compile(r"\.m_methods\s*=\s*(?P<table>\w+)", re.MULTILINE)
_RE_MODULE_CREATE = re.compile(r"PyModule_Create\s*\(\s*&(?P<def>\w+)\s*\)", re.MULTILINE)


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


def _pybind11_def_patterns(module_var: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build ``var.def`` regexes for a PYBIND11_MODULE binder variable."""
    var = re.escape(module_var)
    symbol = re.compile(
        rf"""\b{var}\.def\s*\(\s*(['"])(?P<py>[^'"]+)\1\s*,\s*&(?P<cpp>[\w:]+)\s*[,)]""",
        re.MULTILINE,
    )
    inline = re.compile(
        rf"""\b{var}\.def\s*\(\s*(['"])(?P<py>[^'"]+)\1\s*,\s*\[""",
        re.MULTILINE,
    )
    return symbol, inline


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
        """Parse Rust source for evidence-backed PyO3 exports.

        ``EXACT`` only when ``#[pyfunction]`` + ``wrap_pyfunction!`` +
        ``#[pymodule]`` are all present for that function (R217).
        """
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
            registered = rust_name in wrapped and mod_m is not None
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
            precision = BindingPrecision.EXACT if registered else BindingPrecision.BRIDGE
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=_rust_symbol(rust_name),
                    framework=BindingFramework.PYO3,
                    precision=precision,
                    evidence=tuple(evidence),
                    python_module=module,
                    python_name=py_name,
                    native_language_id="rust",
                    provider_id=self.provider_id,
                )
            )
        return tuple(edges)


class Pybind11BindingProvider:
    """Extract ``PYBIND11_MODULE`` + ``<var>.def`` edges (exact or inline)."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.pybind11"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.PYBIND11

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse C++ source for pybind11 exports.

        Supports arbitrary binder variable names from
        ``PYBIND11_MODULE(name, var)`` (R217); ``EXACT`` requires both
        ``var.def`` and the module macro.
        """
        modules = list(_RE_PYBIND11_MODULE.finditer(text))
        # Fall back to scanning ``m.def`` if no macro (declaration-only → BRIDGE).
        binders: list[tuple[str, str, re.Match[str] | None]] = []
        if modules:
            for mod_m in modules:
                binders.append((mod_m.group("mod"), mod_m.group("var"), mod_m))
        else:
            binders.append(("_native", "m", None))

        edges: list[BindingEdge] = []
        seen_starts: set[int] = set()
        for module, var, mod_match in binders:
            symbol_re, inline_re = _pybind11_def_patterns(var)
            for match in symbol_re.finditer(text):
                if match.start() in seen_starts:
                    continue
                seen_starts.add(match.start())
                py_name = match.group("py")
                cpp_name = match.group("cpp")
                evidence = [
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYBIND11_DEF,
                        uri=uri,
                        span=_span_for_match(text, match),
                        detail=f'{var}.def("{py_name}", &{cpp_name})',
                    )
                ]
                if mod_match is not None:
                    evidence.append(
                        BindingEvidence(
                            kind=BindingEvidenceKind.PYBIND11_MODULE,
                            uri=uri,
                            span=_span_for_match(text, mod_match, "mod"),
                            detail=f"PYBIND11_MODULE({module})",
                        )
                    )
                precision = BindingPrecision.EXACT if mod_match is not None else BindingPrecision.BRIDGE
                edges.append(
                    BindingEdge(
                        python_symbol=_python_symbol(module, py_name),
                        native_symbol=_cpp_symbol(cpp_name),
                        framework=BindingFramework.PYBIND11,
                        precision=precision,
                        evidence=tuple(evidence),
                        python_module=module,
                        python_name=py_name,
                        native_language_id="cpp",
                        provider_id=self.provider_id,
                    )
                )
            for match in inline_re.finditer(text):
                if match.start() in seen_starts:
                    continue
                seen_starts.add(match.start())
                py_name = match.group("py")
                line = text.count("\n", 0, match.start()) + 1
                col = match.start() - (text.rfind("\n", 0, match.start()) + 1)
                native = f"cpp:{uri.rsplit('/', 1)[-1]}::<lambda@{line}:{col}>"
                evidence = [
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYBIND11_INLINE,
                        uri=uri,
                        span=_span_for_match(text, match),
                        detail=f'{var}.def("{py_name}", []…)',
                    )
                ]
                if mod_match is not None:
                    evidence.append(
                        BindingEvidence(
                            kind=BindingEvidenceKind.PYBIND11_MODULE,
                            uri=uri,
                            span=_span_for_match(text, mod_match, "mod"),
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


def _cpython_registered_tables(text: str) -> dict[str, tuple[str, re.Match[str], re.Match[str]]]:
    """Map method-table name → (module_name, pymoduledef_match, pyinit_match).

    A table is registered when some ``PyModuleDef`` sets ``.m_methods = table``
    and some ``PyInit_*`` calls ``PyModule_Create(&that_def)``.
    """
    def_to_table: dict[str, tuple[str, re.Match[str]]] = {}
    for def_m in _RE_PYMODULEDEF.finditer(text):
        def_name = def_m.group("def")
        # Search for m_methods near this def (same file heuristic: next 800 chars).
        window = text[def_m.start() : def_m.start() + 800]
        mm = _RE_MMETHODS.search(window)
        if mm is not None:
            def_to_table[def_name] = (mm.group("table"), def_m)

    registered: dict[str, tuple[str, re.Match[str], re.Match[str]]] = {}
    for init_m in _RE_PYINIT.finditer(text):
        module = init_m.group(1)
        # Look inside the PyInit function body for PyModule_Create.
        body = text[init_m.start() : init_m.start() + 1200]
        create = _RE_MODULE_CREATE.search(body)
        if create is None:
            continue
        def_name = create.group("def")
        if def_name not in def_to_table:
            continue
        table, def_m = def_to_table[def_name]
        registered[table] = (module, def_m, init_m)
    return registered


def _method_table_for_offset(text: str, offset: int) -> str | None:
    """Return the nearest preceding ``PyMethodDef table[]`` name for ``offset``."""
    best: tuple[int, str] | None = None
    for table_m in _RE_PYMETHODDEF_TABLE.finditer(text):
        if table_m.start() <= offset and (best is None or table_m.start() > best[0]):
            best = (table_m.start(), table_m.group("table"))
    return best[1] if best is not None else None


class CPythonBindingProvider:
    """Extract ``PyMethodDef`` + ``PyModuleDef`` / ``PyInit_*`` edges."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "ffi.cpython"

    @property
    def framework(self) -> BindingFramework:
        """Framework tag."""
        return BindingFramework.CPYTHON

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse C/C++ extension source for CPython method table exports.

        ``EXACT`` only when the method table is referenced from a
        ``PyModuleDef.m_methods`` used by ``PyInit_*`` via ``PyModule_Create``
        (R217). Otherwise ``BRIDGE``.
        """
        registered = _cpython_registered_tables(text)
        fallback_init = _RE_PYINIT.search(text)
        fallback_module = fallback_init.group(1) if fallback_init is not None else "_native"

        edges: list[BindingEdge] = []
        for match in _RE_PYMETHODDEF.finditer(text):
            py_name = match.group("py")
            fn_name = match.group("fn")
            table = _method_table_for_offset(text, match.start())
            evidence = [
                BindingEvidence(
                    kind=BindingEvidenceKind.PYMETHODDEF,
                    uri=uri,
                    span=_span_for_match(text, match),
                    detail=f'{{"{py_name}", {fn_name}, METH_…}}',
                )
            ]
            precision = BindingPrecision.BRIDGE
            module = fallback_module
            if table is not None and table in registered:
                module, def_m, init_m = registered[table]
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYMODULEDEF,
                        uri=uri,
                        span=_span_for_match(text, def_m, "def"),
                        detail=f"PyModuleDef {def_m.group('def')}.m_methods={table}",
                    )
                )
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYINIT,
                        uri=uri,
                        span=_span_for_match(text, init_m, 1),
                        detail=f"PyInit_{module}",
                    )
                )
                precision = BindingPrecision.EXACT
            elif fallback_init is not None:
                # Co-located PyInit without proven table link → BRIDGE only.
                evidence.append(
                    BindingEvidence(
                        kind=BindingEvidenceKind.PYINIT,
                        uri=uri,
                        span=_span_for_match(text, fallback_init, 1),
                        detail=f"PyInit_{fallback_module} (unlinked)",
                    )
                )
            edges.append(
                BindingEdge(
                    python_symbol=_python_symbol(module, py_name),
                    native_symbol=_cpp_symbol(fn_name),
                    framework=BindingFramework.CPYTHON,
                    precision=precision,
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
            base = uri.rsplit("/", 1)[-1]
            if base.endswith(".pyi"):
                mod = base[: -len(".pyi")]
            else:
                mod = base or "_stub"
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ()
        lines = text.splitlines(keepends=True)
        stubs: list[PyiStubSymbol] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = max(1, int(getattr(node, "lineno", 1)))
                offset = sum(len(lines[i]) for i in range(max(0, start_line - 1)))
                line = lines[start_line - 1] if start_line - 1 < len(lines) else ""
                col = int(getattr(node, "col_offset", 0) or 0)
                idx = line.find(node.name, col)
                if idx < 0:
                    idx = line.find(node.name)
                if idx < 0:
                    idx = col
                abs_start = offset + idx
                name_span = SourceSpan(abs_start, abs_start + len(node.name))
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
