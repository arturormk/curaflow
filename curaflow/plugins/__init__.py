"""Plugin modules for curaflow.

Import all source and target plugins to register them via decorators.
"""

# Import all built-in plugins to auto-register them
from .sources import http_html, http_xml
from .targets import concat_json

__all__ = ["http_html", "http_xml", "concat_json"]
