"""CrowdVision — the repo root IS the ``crowdvision`` package.

See ``pyproject.toml`` for why: ``package-dir = {"crowdvision": "."}`` keeps the
v9 §i top-level layout literal while making ``sim/`` importable as
``crowdvision.sim`` (so ``python -m crowdvision.sim --all`` works after
``pip install -e .``).

Shared, schema-level helpers live in :mod:`crowdvision._lib`. Everything else at
the repo root (``zone-brain/``, ``venue-tier/`` …) is run as scripts.
"""

__version__ = "0.9.0"
