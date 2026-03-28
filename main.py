"""
Wrapper script for the AI Native game engine.

This script serves as a simple entry point that delegates to the main implementation
in src/main.py.
"""
import sys
import asyncio
from src.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except asyncio.CancelledError:
        pass  # Suppress asyncio cancellation traceback for graceful shutdown