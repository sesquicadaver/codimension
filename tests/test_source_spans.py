# -*- coding: utf-8 -*-
"""Unit tests for codimension.parsers.source_spans (parser contract T003)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "codimension"))

from parsers.source_spans import SourceIndex, build_source_index, node_source_segment  # noqa: E402


def test_ascii_simple_node_span() -> None:
    source = "x = 1\ny = 2\n"
    tree = ast.parse(source)
    index = build_source_index(source)
    assign = tree.body[1]
    begin, end, bln, eln, bpos, epos = index.node_span(assign)
    assert bln == 2 and eln == 2
    assert source[begin:end] == "y = 2"
    assert bpos == 1
    assert epos == 6  # exclusive end col as 1-based char after last


def test_cyrillic_prefix_does_not_shift_span() -> None:
    # Cyrillic before the assignment on the same line (2 bytes per letter in UTF-8)
    source = "привіт = 1\nz = 2\n"
    tree = ast.parse(source)
    index = SourceIndex.build(source)
    first = tree.body[0]
    begin, end, *_ = index.node_span(first)
    assert source[begin:end] == "привіт = 1"
    second = tree.body[1]
    begin2, end2, *_ = index.node_span(second)
    assert source[begin2:end2] == "z = 2"


def test_emoji_in_string_span() -> None:
    source = 's = "😀"\n'
    tree = ast.parse(source)
    index = build_source_index(source)
    begin, end, *_ = index.node_span(tree.body[0])
    assert source[begin:end] == 's = "😀"'


def test_multi_statement_same_line() -> None:
    source = "a = 1; b = 2\n"
    tree = ast.parse(source)
    index = build_source_index(source)
    a_span = index.node_span(tree.body[0])
    b_span = index.node_span(tree.body[1])
    assert source[a_span[0] : a_span[1]] == "a = 1"
    assert source[b_span[0] : b_span[1]] == "b = 2"
    assert a_span[1] <= b_span[0]


def test_exclusive_end_no_extra_char() -> None:
    source = "pass\n"
    tree = ast.parse(source)
    index = build_source_index(source)
    begin, end, *_ = index.node_span(tree.body[0])
    assert source[begin:end] == "pass"
    assert end == begin + 4


def test_node_source_segment_matches_slice() -> None:
    source = "def f(x=1):\n    return x\n"
    tree = ast.parse(source)
    func = tree.body[0]
    segment = node_source_segment(source, func)
    index = build_source_index(source)
    begin, end, *_ = index.node_span(func)
    assert segment == source[begin:end]


def test_character_vs_byte_column_apis() -> None:
    """tokenize uses character columns; AST uses UTF-8 byte columns (A07)."""
    source = 'значення = "тест"  # коментар\n'
    index = SourceIndex.build(source)
    hash_char = source.index("#")
    # Character column of '#' on line 1 (0-based)
    char_col = hash_char - index.line_start(1)
    assert index.abs_from_character_column(1, char_col) == hash_char
    # Same numeric value treated as UTF-8 bytes would land earlier on Cyrillic line
    wrong = index.abs_from_utf8_byte_column(1, char_col)
    assert wrong != hash_char
    assert source[wrong:hash_char]


def test_line_count_and_empty() -> None:
    assert build_source_index("").line_count == 1
    idx = build_source_index("a\nb")
    assert idx.line_text(1) == "a"
    assert idx.line_text(2) == "b"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
