"""Toml helpers that preserve comments/format via tomlkit (write path).

Reads still use tomllib (stdlib). For adapters that must rewrite TOML while
keeping comments, use these helpers."""
from __future__ import annotations

from pathlib import Path


def load_toml_editable(path: Path):
    """Return a tomlkit document (editable) or None if file missing/dep absent."""
    try:
        import tomlkit
    except ImportError:
        return None
    if not path.exists():
        return None
    return tomlkit.parse(path.read_text("utf-8"))


def dump_toml(doc) -> str:
    import tomlkit
    return tomlkit.dumps(doc)


def set_top_level(path: Path, key: str, value: str) -> str | None:
    """Set a top-level string key in a TOML file, preserving everything else.
    Returns the new text, or None if file missing/dep absent."""
    doc = load_toml_editable(path)
    if doc is None:
        return None
    doc[key] = value
    text = dump_toml(doc)
    from . import config
    config.write_text_atomic(path, text)
    return text


def set_table_field(path: Path, table: str, field: str, value: str,
                    create_table: bool = False) -> str | None:
    """Set `table.field = value` in a TOML file (table must already exist)."""
    doc = load_toml_editable(path)
    if doc is None:
        return None
    if table not in doc:
        if not create_table:
            return None
        import tomlkit
        doc[table] = tomlkit.table()
    doc[table][field] = value
    text = dump_toml(doc)
    from . import config
    config.write_text_atomic(path, text)
    return text