# src/ondotori_client/__init__.py

from importlib.metadata import (
    version as _pkg_version,
    PackageNotFoundError as _PkgNotFound,
)

try:
    __version__ = _pkg_version(__name__.replace("_", "-"))
except _PkgNotFound:
    # fallback when package metadata is unavailable (e.g., during source run)
    __version__ = "0.0.0.dev0"

from .client import OndotoriClient, parse_current, parse_data

__all__ = [
    "OndotoriClient",
    "parse_current",
    "parse_data",
    "__version__",
]
