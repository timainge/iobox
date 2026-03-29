"""
iobox — multi-provider personal workspace context tool.

Single interface for searching, retrieving, and exporting email, calendar events,
and files across Google and Microsoft 365 accounts.
"""

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("iobox")
except PackageNotFoundError:
    __version__ = "0.1.0"  # fallback for uninstalled dev

__all__ = ["__version__"]
