"""Read and write cassettes as normalized, human-diffable YAML.

ruamel.yaml is used for stable, block-style output so a cassette reviews cleanly
in a pull request and a tampered line shows up as a minimal diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from ..errors import CassetteError
from ..schemas.cassette import Cassette

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def _to_plain(obj: Any) -> Any:
    """Convert ruamel's CommentedMap/Seq (and scalar wrappers) to plain types."""
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


def save_cassette(cassette: Cassette, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = cassette.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as handle:
        _yaml.dump(data, handle)
    return path


def load_cassette(path: str | Path) -> Cassette:
    path = Path(path)
    if not path.exists():
        raise CassetteError(f"cassette not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = _yaml.load(handle)
    except Exception as exc:  # surface any parse error uniformly
        raise CassetteError(f"could not parse cassette {path}: {exc}") from exc
    return Cassette.model_validate(_to_plain(raw))
