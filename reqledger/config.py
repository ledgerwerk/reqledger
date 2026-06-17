"""ReqLedger configuration discovery and path resolution.

Config lookup order (first wins):

1. explicit ``--config`` path,
2. ``reqledger.toml`` discovered upward from the current directory,
3. ``.reqledger.toml`` discovered upward,
4. built-in defaults (paths relative to the current directory).

When both ``reqledger.toml`` and ``.reqledger.toml`` exist in the same
directory, the visible ``reqledger.toml`` wins. Paths declared in config
resolve relative to the config file's directory; with no config they resolve
relative to the current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:  # pragma: no cover - exercised only on 3.10
    import tomli as _toml

from ledgercore.paths import ConfigLocator, find_config_upwards, locate_config

from reqledger.errors import ConfigError
from reqledger.model import ReqLedgerConfig

CONFIG_FILENAMES: tuple[str, ...] = ("reqledger.toml", ".reqledger.toml")
LEGACY_CONFIG_FILENAME = ".reqledger.toml"


def _load_toml_document(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return _toml.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - callers guard this
        raise ConfigError(f"Config file not found: {path}") from exc
    except _toml.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in config {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config {path}: {exc}") from exc


def _coerce_int(value: object, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"[{field_name}] must be an integer")
    return value


def _resolve_path(config_dir: Path, value: str) -> Path:
    """Resolve a config-declared path relative to the config directory.

    Absolute paths are accepted as-is (they are still inside a workspace the
    user explicitly configured). Relative paths resolve under ``config_dir``.
    """
    rendered = value.strip()
    if not rendered:
        raise ConfigError("Config path value must not be empty")
    candidate = Path(rendered)
    if candidate.is_absolute():
        return candidate
    return (config_dir / candidate).resolve()


def _resolve_config(config_path: Path, document: dict[str, Any]) -> ReqLedgerConfig:
    config_dir = config_path.parent.resolve()
    defaults = ReqLedgerConfig.default_fields()
    paths_section = document.get("paths", {})
    ids_section = document.get("ids", {})
    review_section = document.get("review", {})
    if not isinstance(paths_section, dict):
        raise ConfigError("[paths] must be a table")
    if not isinstance(ids_section, dict):
        raise ConfigError("[ids] must be a table")
    if not isinstance(review_section, dict):
        raise ConfigError("[review] must be a table")

    root = _resolve_path(
        config_dir, str(paths_section.get("root", defaults["paths"]["root"]))
    )
    records_dir = _resolve_path(
        config_dir,
        str(paths_section.get("records_dir", defaults["paths"]["records_dir"])),
    )
    manifest = _resolve_path(
        config_dir, str(paths_section.get("manifest", defaults["paths"]["manifest"]))
    )
    reports_dir = _resolve_path(
        config_dir,
        str(paths_section.get("reports_dir", defaults["paths"]["reports_dir"])),
    )
    reports_state_dir = _resolve_path(
        config_dir,
        str(
            paths_section.get(
                "reports_state_dir", defaults["paths"]["reports_state_dir"]
            )
        ),
    )

    requirement_prefix = str(
        ids_section.get("requirement_prefix", defaults["ids"]["requirement_prefix"])
    )
    criterion_prefix = str(
        ids_section.get("criterion_prefix", defaults["ids"]["criterion_prefix"])
    )
    width = _coerce_int(
        ids_section.get("width", defaults["ids"]["width"]),
        field_name="ids.width",
        default=4,
    )
    draft_stale_days = _coerce_int(
        review_section.get("draft_stale_days", defaults["review"]["draft_stale_days"]),
        field_name="review.draft_stale_days",
        default=90,
    )
    schema_version = _coerce_int(
        document.get("schema_version", defaults["schema_version"]),
        field_name="schema_version",
        default=1,
    )

    return ReqLedgerConfig(
        schema_version=schema_version,
        root=root,
        records_dir=records_dir,
        manifest=manifest,
        reports_dir=reports_dir,
        reports_state_dir=reports_state_dir,
        requirement_prefix=requirement_prefix,
        criterion_prefix=criterion_prefix,
        width=width,
        draft_stale_days=draft_stale_days,
        workspace_root=config_dir,
        config_path=config_path,
    )


def _build_defaults(start: Path) -> ReqLedgerConfig:
    """Build a config from built-in defaults anchored at ``start``."""
    base = start.resolve()
    defaults = ReqLedgerConfig.default_fields()
    return ReqLedgerConfig(
        schema_version=int(defaults["schema_version"]),
        root=(base / defaults["paths"]["root"]).resolve(),
        records_dir=(base / defaults["paths"]["records_dir"]).resolve(),
        manifest=(base / defaults["paths"]["manifest"]).resolve(),
        reports_dir=(base / defaults["paths"]["reports_dir"]).resolve(),
        reports_state_dir=(base / defaults["paths"]["reports_state_dir"]).resolve(),
        requirement_prefix=str(defaults["ids"]["requirement_prefix"]),
        criterion_prefix=str(defaults["ids"]["criterion_prefix"]),
        width=int(defaults["ids"]["width"]),
        draft_stale_days=int(defaults["review"]["draft_stale_days"]),
        workspace_root=base,
        config_path=Path(),
    )


def load_config(
    *,
    config: str | Path | None = None,
    start: Path | None = None,
) -> ReqLedgerConfig:
    """Load a resolved ReqLedger configuration.

    Args:
        config: Optional explicit config file path. When provided, paths in the
            config resolve relative to that file's directory.
        start: Directory to search from when no explicit config is given.
            Defaults to the current working directory.
    """
    search_start = (start or Path.cwd()).resolve()

    if config is not None:
        config_path = Path(config).expanduser()
        if not config_path.is_absolute():
            config_path = (search_start / config_path).resolve()
        if not config_path.is_file():
            raise ConfigError(f"Config file not found: {config_path}")
        document = _load_toml_document(config_path)
        return _resolve_config(config_path, document)

    # Visible config wins over the hidden/legacy one within the same directory.
    locator = locate_config(search_start, CONFIG_FILENAMES)
    if locator is not None and locator.config_path.is_file():
        document = _load_toml_document(locator.config_path)
        return _resolve_config(locator.config_path, document)

    return _build_defaults(search_start)


def discover_config_path(start: Path | None = None) -> Path | None:
    """Return the config path that would be selected, or None for defaults."""
    search_start = (start or Path.cwd()).resolve()
    found = find_config_upwards(search_start, CONFIG_FILENAMES)
    return found


def locator(start: Path | None = None) -> ConfigLocator | None:
    """Expose the underlying ledgercore locator for callers that need it."""
    search_start = (start or Path.cwd()).resolve()
    return locate_config(search_start, CONFIG_FILENAMES)


__all__ = [
    "CONFIG_FILENAMES",
    "LEGACY_CONFIG_FILENAME",
    "discover_config_path",
    "load_config",
    "locator",
]
