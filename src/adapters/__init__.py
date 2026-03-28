"""
Adapters package for the AI Native game engine.

This package contains adapters for interfacing with different systems,
such as frontend interfaces, databases, and external services.
"""

from .base import FrontendAdapter
from .web_frontend_adapter import WebFrontendAdapter

__all__ = ['FrontendAdapter', 'WebFrontendAdapter']
