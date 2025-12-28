"""Plugin modules for curaflow.

Import all source and target plugins to register them via decorators.
"""

# Import all built-in plugins to auto-register them
from .sources import http_bytes, http_html, http_json, http_xml
from .targets import concat_json, debug_print

__all__ = [
    "http_json",
    "http_html",
    "http_bytes",
    "http_xml",
    "concat_json",
    "debug_print",
]
