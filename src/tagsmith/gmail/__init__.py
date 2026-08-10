"""Gmail auth, API client, and MIME normalization."""

from tagsmith.gmail.parser import NormalizedEmail, normalize_message

__all__ = ["NormalizedEmail", "normalize_message"]
