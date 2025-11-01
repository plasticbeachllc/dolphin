#!/usr/bin/env python3
"""
Test script for KiloCode migration functionality.
Run this to test the personas -> KiloCode migration.
"""

import sys
from pathlib import Path

# Add personas src to path
sys.path.insert(0, str(Path("personas/src")))

from personas import app
import typer

def test_migration():
    """Test the KiloCode migration with sample personas."""
    print("Testing KiloCode migration...")
    
    # Test KiloCode dry run first (now requires --global)
    print("\n1. Testing KiloCode dry run...")
    try:
        app(["generate", "--personas", "personas", "--kilocode", "--global", "--dry-run", "--verbose"])
        print("✓ KiloCode dry run completed successfully")
    except Exception as e:
        print(f"✗ KiloCode dry run failed: {e}")
        return False
    
    # Test Continue dry run
    print("\n2. Testing Continue dry run...")
    try:
        app(["generate", "--personas", "personas", "--continue", "--dry-run"])
        print("✓ Continue dry run completed successfully")
    except Exception as e:
        print(f"✗ Continue dry run failed: {e}")
        return False
    
    # Test actual KiloCode generation (now requires --global)
    print("\n3. Testing actual KiloCode generation...")
    try:
        app(["generate", "--personas", "personas", "--kilocode", "--global", "--out", "test-output/kilocode"])
        print("✓ KiloCode generation completed successfully")
    except Exception as e:
        print(f"✗ KiloCode generation failed: {e}")
        return False
    
    # Test actual Continue generation
    print("\n4. Testing actual Continue generation...")
    try:
        app(["generate", "--personas", "personas", "--continue", "--out", "test-output/continue.yaml"])
        print("✓ Continue generation completed successfully")
    except Exception as e:
        print(f"✗ Continue generation failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_migration()
    if success:
        print("\n🎉 KiloCode migration test completed successfully!")
        print("\nNext steps:")
        print("1. Review generated files:")
        print("   - KiloCode: test-output/kilocode/ (global configuration)")
        print("   - Continue: test-output/continue.yaml")
        print("2. Test KiloCode integration with generated configurations")
        print("3. Test Continue integration with generated configurations")
        print("4. Validate provider mappings match KiloCode schema")
    else:
        print("\n❌ Migration test failed. Please check the errors above.")
        sys.exit(1)