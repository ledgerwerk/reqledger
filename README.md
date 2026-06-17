# ReqLedger

ReqLedger is the Ledgerwerk record owner for requirements and acceptance
criteria.

It stores durable requirement records as readable Markdown files with TOML
metadata. It does not run tests, generate Gherkin, parse Gherkin, discover
pytest tests, or own task/architecture records.

Downstream tools such as SpecMason can consume ReqLedger exports to create and
validate behavior specs, pytest mappings, coverage reports, and evidence
reports.

## Scope boundary

| Tool        | Owns                                                        |
| ----------- | ---------------------------------------------------------- |
| reqledger   | requirements and acceptance criteria                       |
| specmason   | behavior specs, mappings, coverage, and evidence           |
| taskledger  | tasks and task workflow                                    |
| archledger  | architecture records and ADRs                              |
| planledger  | implementation plans                                       |
| wikimason   | wiki content                                              |

ReqLedger is normative: accepted requirement records define intended product
behavior. Source code and tests describe observed behavior but never silently
rewrite requirements.

## Requirements live as readable files

```text
requirements/
  README.md
  manifest.json
  records/
    req-0001.req.md
  reports/
    reqledger/
      review.md
      review.json
reqledger.toml
```

Each requirement is a Markdown file with TOML front matter delimited by `+++`:

```toml
+++
schema_version = 1
id = "REQ-0001"
title = "Reject invalid login passwords"
kind = "functional"
status = "accepted"
priority = "must"
tags = ["auth", "login"]
source = "manual"
created = "2026-06-16"
updated = "2026-06-16"

[[criteria]]
id = "AC-0001"
statement = "Login is rejected when an invalid password is submitted."
verification = "behavior"
status = "accepted"
tags = ["auth"]
+++

# REQ-0001: Reject invalid login passwords

## Intent

The product must reject invalid passwords for registered users.
```

## Quickstart

```bash
pip install reqledger
reqledger init
reqledger new "Reject invalid login passwords" \
  --kind functional \
  --priority must \
  --criterion "Login is rejected when an invalid password is submitted."
reqledger validate
reqledger index
reqledger review
reqledger export --format json
```

## Commands

```bash
reqledger init [--force] [--json]
reqledger new "Title" [--kind] [--priority] [--tag TAG]... [--criterion STMT]... [--status] [--source] [--json]
reqledger list [--status STATUS] [--tag TAG] [--json]
reqledger show REQ-0001 [--json]
reqledger validate [--json]
reqledger index [--json]
reqledger link REQ-0001 --task ID --arch ID --spec PATH --evidence PATH [--json]
reqledger review [--json]
reqledger export --format json [--output PATH] [--json]
```

Global options: `reqledger --version`, `reqledger --config PATH <command>`.

Validation is fail-closed and returns exit code `1` on validation errors,
`2` on usage/config errors, and `0` when all records are valid.

## Configuration

ReqLedger looks for config in this order (first wins):

1. explicit `--config PATH`,
2. `reqledger.toml` discovered upward from the current directory,
3. `.reqledger.toml` discovered upward,
4. built-in defaults.

When both `reqledger.toml` and `.reqledger.toml` exist in the same directory,
`reqledger.toml` wins. Paths declared in config resolve relative to the config
file's directory; with no config they resolve relative to the current working
directory.

Default config:

```toml
schema_version = 1

[paths]
root = "requirements"
records_dir = "requirements/records"
manifest = "requirements/manifest.json"
reports_dir = "requirements/reports"
reports_state_dir = "requirements/reports/reqledger"

[ids]
requirement_prefix = "REQ"
criterion_prefix = "AC"
width = 4

[review]
draft_stale_days = 90
```

## Manifest and export

`reqledger index` writes a deterministic `requirements/manifest.json`:

```json
{
  "schema_version": 1,
  "tool": "reqledger",
  "requirements": [
    {
      "id": "REQ-0001",
      "title": "Reject invalid login passwords",
      "path": "requirements/records/req-0001.req.md",
      "kind": "functional",
      "status": "accepted",
      "priority": "must",
      "tags": ["auth", "login"],
      "source": "manual",
      "source_refs": [],
      "criteria": [
        {
          "id": "AC-0001",
          "statement": "Login is rejected when an invalid password is submitted.",
          "verification": "behavior",
          "status": "accepted",
          "tags": ["auth"]
        }
      ],
      "refs": {
        "tasks": [],
        "architecture": [],
        "specs": [],
        "evidence": []
      }
    }
  ]
}
```

The manifest is derived state; Markdown records remain the source of truth.
`reqledger export --format json` emits the same shape for downstream tools.

## Design constraints

- Prefer readable files over hidden state.
- Keep deterministic output.
- Keep dependencies minimal (`typer`, `ledgercore`, `tomli` for Python < 3.11).
- Preserve user-authored Markdown bodies.
- Do not use title matching for identity; IDs are the identity.
- Validation is fail-closed.
- External links are references, not ownership transfers.
- ReqLedger does not parse or generate Gherkin, discover or run tests, or
  import SpecMason at runtime.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

ReqLedger reuses shared Ledgerwerk primitives from
[`ledgercore`](https://github.com/ledgerwerk/ledgercore) (ID allocation, config
discovery, deterministic JSON, atomic writes) and implements the TOML `+++`
front matter and requirements domain itself.

## License

Apache-2.0.
