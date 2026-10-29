"""Local image evidence and explicit, bounded geographic lookups.

An image identifier is a capability issued by AttachmentStore, never a pathname
chosen by the model. Importing or examining an image performs no network calls.
"""
from .images import AttachmentStore, GeointError, MAX_IMAGE_BYTES
from .mapping import MappingClient, reverse_search_providers

__all__ = ["AttachmentStore", "GeointError", "MAX_IMAGE_BYTES", "MappingClient", "reverse_search_providers"]
