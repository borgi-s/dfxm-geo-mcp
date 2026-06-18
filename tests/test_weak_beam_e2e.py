"""Weak vs strong beam produce different forward images.

The regression that would have caught the original bug: a phi offset must change
the rendered physics, not be silently ignored. Uses the ops layer directly.
"""

from __future__ import annotations

import pytest

from dfxm_geo_mcp.ops import forward as _forward
from dfxm_geo_mcp.ops.scaffold import scaffold_config

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.slow
def test_weak_and_strong_produce_different_images():
    weak = _forward.run_forward(scaffold_config(beam="weak"))
    strong = _forward.run_forward(scaffold_config(beam="strong"))
    assert weak.png_bytes[:8] == _PNG_MAGIC
    assert strong.png_bytes[:8] == _PNG_MAGIC
    # The phi offset changed the physics: the two renders are not identical.
    assert weak.png_bytes != strong.png_bytes
