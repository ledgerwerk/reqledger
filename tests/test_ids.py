"""Tests for reqledger.ids."""

from __future__ import annotations

from reqledger.config import load_config
from reqledger.ids import (
    filename_for_id,
    is_valid_criterion_id,
    is_valid_requirement_id,
    next_criterion_id,
    next_requirement_id,
    requirement_filename,
)


def test_next_requirement_id_is_deterministic(workspace) -> None:
    config = load_config(start=workspace)
    assert next_requirement_id([], config) == "REQ-0001"
    assert next_requirement_id(["REQ-0001", "REQ-0002"], config) == "REQ-0003"
    # Non-matching ids are ignored.
    assert next_requirement_id(["REQ-0001", "garbage"], config) == "REQ-0002"


def test_next_criterion_id_starts_at_one(workspace) -> None:
    config = load_config(start=workspace)
    assert next_criterion_id([], config) == "AC-0001"
    assert next_criterion_id(["AC-0001", "AC-0005"], config) == "AC-0006"


def test_id_validity_checks(workspace) -> None:
    config = load_config(start=workspace)
    assert is_valid_requirement_id("REQ-0001", config)
    assert not is_valid_requirement_id("REQ-1", config)
    assert not is_valid_requirement_id("AC-0001", config)
    assert is_valid_criterion_id("AC-0001", config)
    assert not is_valid_criterion_id("REQ-0001", config)


def test_filename_from_id(workspace) -> None:
    config = load_config(start=workspace)
    assert requirement_filename("REQ-0001", config) == "req-0001.req.md"
    assert filename_for_id("REQ-0042") == "req-0042.req.md"
