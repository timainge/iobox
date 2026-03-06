"""
iobox provider package.

Exports the EmailProvider ABC, EmailQuery, EmailData, and the
get_provider() factory. Provider implementations are loaded lazily
so that optional dependencies (e.g. O365) are never imported unless
the corresponding provider is actually requested.
"""

import importlib

from iobox.providers.base import AttachmentInfo, EmailData, EmailProvider, EmailQuery

__all__ = [
    "AttachmentInfo",
    "EmailData",
    "EmailProvider",
    "EmailQuery",
    "get_provider",
]

_PROVIDERS: dict[str, str] = {
    "gmail": "iobox.providers.gmail.GmailProvider",
    "outlook": "iobox.providers.outlook.OutlookProvider",
}

_INSTALL_HINTS: dict[str, str] = {
    "outlook": "pip install 'iobox[outlook]'  # or: pip install O365>=2.1.8",
}


def get_provider(name: str = "gmail", **kwargs) -> EmailProvider:
    """Instantiate an email provider by name.

    Uses lazy importlib import so Outlook dependencies are never
    required for Gmail-only users.

    Args:
        name: Provider name — 'gmail' or 'outlook'.
        **kwargs: Passed through to the provider constructor.

    Raises:
        ValueError: If the provider name is not recognised.
        ImportError: If the provider's optional dependency is not installed.
    """
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS)}"
        )

    module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        hint = _INSTALL_HINTS.get(name)
        if hint:
            raise ImportError(
                f"Provider '{name}' requires additional dependencies. "
                f"Install them with: {hint}"
            ) from exc
        raise

    cls = getattr(module, class_name)
    return cls(**kwargs)
