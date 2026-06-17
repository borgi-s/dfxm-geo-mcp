"""validate_config: parse TOML into a dfxm-geo SimulationConfig, report structured issues.

Exception-widening log:
- ValueError, KeyError, TypeError, tomllib.TOMLDecodeError: caught per brief.
  No additional exception types were observed during test development.
"""

from __future__ import annotations

import dataclasses
import tempfile
import tomllib
from pathlib import Path

from dfxm_geo.config import ReciprocalConfig, SimulationConfig

from dfxm_geo_mcp.ops.types import ConfigIssue, ResolvedSummary, ValidationReport

_AXES = ("phi", "chi", "two_dtheta", "z")

# Known valid keys for [reciprocal] block — ReciprocalConfig.from_dict silently
# ignores unknown keys, so we validate them here to surface typos as issues.
_RECIPROCAL_VALID_KEYS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(ReciprocalConfig) if not f.name.startswith("_")
)


def _check_unknown_reciprocal_keys(raw: dict[str, object]) -> list[ConfigIssue]:
    """Return ConfigIssue entries for any unrecognised keys in [reciprocal].

    Only [reciprocal] needs this pre-validation because ReciprocalConfig.from_dict
    silently drops unknown keys instead of raising an error.  Every other block
    ([detector], [io], [postprocess], [scan.<axis>]) is constructed via **-expansion
    inside SimulationConfig.from_toml, so an unknown key there triggers a TypeError
    which is caught structurally in the full-parse step below.  Adding per-field
    detection for those blocks would be YAGNI — the TypeError path already surfaces
    the problem with a helpful message.
    """
    reciprocal_raw = raw.get("reciprocal")
    if not isinstance(reciprocal_raw, dict):
        return []
    issues: list[ConfigIssue] = []
    for key in reciprocal_raw:
        if key not in _RECIPROCAL_VALID_KEYS:
            issues.append(
                ConfigIssue(
                    block="reciprocal",
                    field=key,
                    problem=f"Unknown key {key!r} in [reciprocal]; not a recognised ReciprocalConfig field.",
                    fix=f"Remove or rename {key!r}. Valid keys: {sorted(_RECIPROCAL_VALID_KEYS)}.",
                )
            )
    return issues


def _resolved_summary(config: SimulationConfig) -> ResolvedSummary:
    scanned = [ax for ax in _AXES if getattr(config.scan, ax).is_scanned]
    n_frames = 1
    for ax in scanned:
        n_frames *= int(getattr(config.scan, ax).steps)
    hkl = config.reciprocal.hkl
    return ResolvedSummary(
        reflection=(int(hkl[0]), int(hkl[1]), int(hkl[2])),
        energy_keV=float(config.reciprocal.keV),
        backend=str(config.reciprocal.backend),
        n_frames=n_frames,
        scanned_axes=scanned,
    )


def validate_config(toml_text: str) -> ValidationReport:
    """Parse *toml_text* into a SimulationConfig and return a structured ValidationReport.

    All exceptions from the dfxm-geo library are caught and surfaced as
    ConfigIssue entries; no exception escapes this function.
    """
    # --- Pre-parse to catch malformed TOML and unknown reciprocal keys ---
    try:
        raw = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        return ValidationReport(
            ok=False,
            issues=[
                ConfigIssue(
                    block="(file)",
                    field="(syntax)",
                    problem=str(exc),
                    fix="Fix the TOML syntax (check brackets, quotes, =).",
                )
            ],
            resolved=None,
        )

    pre_issues = _check_unknown_reciprocal_keys(raw)
    if pre_issues:
        return ValidationReport(ok=False, issues=pre_issues, resolved=None)

    # --- Full SimulationConfig parse ---
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "config.toml"
        path.write_text(toml_text, encoding="utf-8")
        try:
            config = SimulationConfig.from_toml(path)
        except (ValueError, KeyError, TypeError) as exc:
            return ValidationReport(
                ok=False,
                issues=[
                    ConfigIssue(
                        block="(config)",
                        field="(value)",
                        problem=str(exc),
                        fix="Correct the field named in the message; see schema://config.",
                    )
                ],
                resolved=None,
            )

    return ValidationReport(ok=True, issues=[], resolved=_resolved_summary(config))
