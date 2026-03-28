"""
Core components for the AI Native game engine.
"""

from .interfaces import (
    ILLMProvider,
    IFrontendAdapter,
    IStateManager,
    IStoryProvider,
    IEntityProvider
)

__all__ = [
    'ILLMProvider',
    'IFrontendAdapter',
    'IStateManager',
    'IStoryProvider',
    'IEntityProvider'
]