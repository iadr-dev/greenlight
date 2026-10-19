"""Project configuration: ``.bdd/config.toml`` (human-edited, read with tomllib)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ALL_PROFILES = ("base", "api", "ui", "cli", "lib")
DEFAULT_SIMILARITY = 0.85
BDD_DIR = ".bdd"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    root: Path | None = None                 # directory that contains .bdd/ (None outside a project)
    profiles: tuple[str, ...] = ALL_PROFILES
    near_duplicate_similarity: float = DEFAULT_SIMILARITY
    feature_dirs: tuple[Path, ...] = ()
    test_dirs: tuple[Path, ...] = ()         # features + steps + drivers: not "production source"
    autonomy: str = "standard"
    language: str = "auto"

    @property
    def vocabulary_file(self) -> Path | None:
        return self.root / BDD_DIR / "vocabulary.toml" if self.root else None


def find_root(start: Path | str | None = None) -> Path | None:
    """Nearest directory at or above ``start`` that contains a ``.bdd`` directory."""
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / BDD_DIR).is_dir():
            return candidate
    return None


def load(root: Path | str | None) -> Config:
    """Read ``<root>/.bdd/config.toml``. Without a root or file, every profile is enabled."""
    if root is None:
        return Config()
    root = Path(root)
    path = root / BDD_DIR / "config.toml"
    if not path.exists():
        return Config(root=root)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    profiles = tuple(data.get("profiles", ALL_PROFILES))
    unknown = [p for p in profiles if p not in ALL_PROFILES]
    if unknown:
        raise ConfigError(f"{path}: unknown profile(s) {', '.join(unknown)}; choose from {', '.join(ALL_PROFILES)}")
    gates = data.get("gates", {})
    return Config(
        root=root,
        profiles=profiles,
        near_duplicate_similarity=float(gates.get("near_duplicate_step_similarity", DEFAULT_SIMILARITY)),
        feature_dirs=tuple(root / a["features"] for a in data.get("adapters", []) if "features" in a),
        test_dirs=tuple(root / a[key] for a in data.get("adapters", []) for key in ("features", "steps", "drivers")
                        if key in a),
        autonomy=data.get("autonomy", "standard"),
        language=data.get("language", "auto"),
    )
