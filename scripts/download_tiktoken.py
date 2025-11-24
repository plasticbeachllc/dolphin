#!/usr/bin/env python3
"""Download tiktoken encoding data for offline testing.

This script downloads the tiktoken encoding data that would normally be
fetched on first use. Running this before tests allows integration tests
to use real tiktoken without network access.

Usage:
    python scripts/download_tiktoken.py
    # or
    uv run scripts/download_tiktoken.py
"""

import sys
from pathlib import Path


def download_tiktoken_encodings():
    """Download tiktoken encoding data to local cache."""
    try:
        import tiktoken
    except ImportError:
        print("ERROR: tiktoken not installed. Run: uv sync --group test", file=sys.stderr)
        return False

    print("Downloading tiktoken encoding data...")
    print("=" * 70)

    encodings = [
        "cl100k_base",  # Used by text-embedding-3-small and text-embedding-3-large
    ]

    failed = []
    for encoding_name in encodings:
        try:
            print(f"Downloading {encoding_name}...", end=" ", flush=True)
            enc = tiktoken.get_encoding(encoding_name)
            print(f"✓ (vocab size: {enc.n_vocab})")
        except Exception as e:
            print("✗ Failed")
            failed.append((encoding_name, str(e)))

    print("=" * 70)

    if failed:
        print()
        print("⚠ WARNING: Could not download tiktoken encoding data")
        print()
        print("Reason:")
        for name, error in failed:
            if "403" in error or "Forbidden" in error:
                print("  Network access to OpenAI's blob storage is blocked (403 Forbidden)")
                break
            print(f"  {name}: {error}")

        print()
        print("This is expected in some environments (e.g., sandboxed, firewalled).")
        print()
        print("Impact:")
        print("  • Integration tests will use mock tiktoken (fallback)")
        print("  • Unit tests already use mock tiktoken (unaffected)")
        print("  • Production code uses real tiktoken when embedding data is available")
        print()
        print("To use real tiktoken in production:")
        print("  1. Ensure network access to https://openaipublic.blob.core.windows.net")
        print("  2. OR pre-download tiktoken data in an environment with network access")
        print("  3. OR copy cached data to ~/.cache/tiktoken/")
        print()
        return False
    else:
        print("✓ All tiktoken encodings downloaded successfully!")
        print()
        print("Cache location:")
        # Try to get cache location
        try:
            import os

            cache_dir = os.path.expanduser("~/.cache/tiktoken")
            if os.path.exists(cache_dir):
                print(f"  {cache_dir}")
                # List files
                for file in Path(cache_dir).iterdir():
                    size_mb = file.stat().st_size / 1024 / 1024
                    print(f"    - {file.name} ({size_mb:.2f} MB)")
        except Exception:
            pass

        print()
        print("✓ Integration tests will now use real tiktoken!")
        return True


if __name__ == "__main__":
    success = download_tiktoken_encodings()
    sys.exit(0 if success else 1)
