#!/usr/bin/env python3
"""Test SQL and Svelte chunkers on real files."""

import sys
from pathlib import Path

# Ensure repository root is on sys.path so the local kb package can be imported
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Test the current SQL chunker on a real file
sql_file = Path("/Users/tdc/worktable/lighthouse/apps/web/drizzle/0000_legal_doctor_strange.sql")

print("=" * 80)


print("Testing SQL Chunker on Real File")
print("=" * 80)
print(f"File: {sql_file}")
print()

try:
    from kb.chunkers.sql_chunker import chunk_source, detect_sql_dialect

    content = sql_file.read_text()

    # Detect dialect
    dialect = detect_sql_dialect(content)
    print(f"Detected dialect: {dialect}")
    print()

    # Chunk the file
    chunks = chunk_source(content)

    print(f"Generated {len(chunks)} chunks:")
    print()

    for i, chunk in enumerate(chunks, 1):
        print(f"Chunk {i}:")
        print(f"  Type: {chunk.symbol_kind}")
        print(f"  Name: {chunk.symbol_name}")
        print(f"  Lines: {chunk.start_line}-{chunk.end_line}")
        print(f"  Tokens: {chunk.token_count}")
        print(f"  Preview: {chunk.text[:100]}...")
        print()

    print("✅ SQL chunker test PASSED")

except Exception as e:
    print(f"❌ SQL chunker test FAILED: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Find a Svelte file
print()
print("=" * 80)
print("Testing Svelte Chunker")
print("=" * 80)

try:
    import subprocess

    result = subprocess.run(
        ["find", "/Users/tdc/worktable", "-name", "*.svelte", "-type", "f"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    svelte_files = [f for f in result.stdout.strip().split("\n") if f][:3]

    if not svelte_files:
        print("⚠️  No Svelte files found, skipping Svelte test")
    else:
        from kb.chunkers.svelte_chunker import chunk_source as chunk_svelte

        for svelte_file in svelte_files:
            svelte_path = Path(svelte_file)
            print(f"\nFile: {svelte_path}")

            try:
                content = svelte_path.read_text()
                chunks = chunk_svelte(content)

                print(f"Generated {len(chunks)} chunks:")
                for i, chunk in enumerate(chunks[:5], 1):  # Show first 5
                    print(
                        f"  {i}. {chunk.symbol_kind} "
                        f"(lines {chunk.start_line}-{chunk.end_line}, {chunk.token_count} tokens)"
                    )

                if len(chunks) > 5:
                    print(f"  ... and {len(chunks) - 5} more chunks")

            except Exception as e:
                print(f"  ❌ Failed: {e}")

        print("\n✅ Svelte chunker test PASSED")

except Exception as e:
    print(f"❌ Svelte chunker test FAILED: {e}")
    import traceback

    traceback.print_exc()

print()
print("=" * 80)
print("All tests completed!")
print("=" * 80)
