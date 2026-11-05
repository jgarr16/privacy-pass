"""Sidecar runtime bootstrap (``python_runtime: external``).

The plugin manager cannot resolve this plugin's dependencies alongside
hermes-agent (presidio-analyzer caps ``numpy<2.5`` while hermes-agent pins
``numpy==2.5.4``), and the spaCy model is a direct-URL requirement. The
plugin therefore owns a sidecar venv under the user's Hermes data area,
created on first use, and imports its heavy dependencies from there. Hermes
installs nothing and no shared environment is modified.

All identifiers used at runtime stay on device; nothing here transmits data.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Keep caps generous but bounded; the sidecar is ours so conflicts with
# hermes-agent pins are impossible by construction.
SIDECAR_REQUIREMENTS = (
    "presidio-analyzer>=2.2.364,<3",
    "spacy>=3.8.16,<4",
    "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/"
    "download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
)


def sidecar_dir() -> Path:
    override = os.environ.get("PRIVACY_PASS_SIDECAR_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / "plugins_data" / "privacy-pass"


def sidecar_venv() -> Path:
    return sidecar_dir() / "venv"


def sidecar_site_packages() -> Path | None:
    lib = sidecar_venv() / "lib"
    if not lib.is_dir():
        return None
    for child in sorted(lib.glob("python*/site-packages")):
        if child.is_dir():
            return child
    return None


def ensure_sidecar() -> Path:
    """Create the sidecar venv and install core deps if missing.

    Returns the site-packages path to put on sys.path. One-time cost on
    first registration (a few minutes of downloads); every later start is
    a no-op.
    """
    existing = sidecar_site_packages()
    if existing is not None:
        return existing

    venv = sidecar_venv()
    venv.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / "bin" / "python"
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", *SIDECAR_REQUIREMENTS], check=True)

    created = sidecar_site_packages()
    if created is None:
        raise RuntimeError("sidecar site-packages not found after bootstrap")
    return created


def wire_sys_path() -> Path:
    """Put the sidecar site-packages on sys.path (bootstrapping if needed)."""
    site_packages = sidecar_site_packages() or ensure_sidecar()
    text = str(site_packages)
    if text not in sys.path:
        sys.path.insert(0, text)
    return site_packages


if __name__ == "__main__":  # manual bootstrap: python3 bootstrap.py
    print(f"Privacy Pass sidecar: {wire_sys_path()}")
