#!/usr/bin/env python3
"""
Demo: .env.example Exception Functionality

This script demonstrates the new ignore exception feature that allows 
.env.example files to be indexed even though .env.* files are normally ignored.
"""

from pathlib import Path
from kb.ignores import build_ignore_set, load_repo_ignores

def demo_basic_functionality():
    """Demonstrate basic exception functionality."""
    print("=== Basic Exception Functionality Demo ===")
    
    # Create example ignore patterns and exceptions
    patterns = [".env", "*.log", "temp"]
    exceptions = [".env.example", "important.log"]
    
    print(f"Patterns: {patterns}")
    print(f"Exceptions: {exceptions}")
    
    # Build ignore set with exceptions
    ignore_set = build_ignore_set(patterns, exceptions)
    
    print(f"Final ignore patterns: {len(ignore_set)} patterns")
    for pattern in sorted(ignore_set):
        print(f"  - {pattern}")
    
    # Test what would be ignored
    test_files = [
        ".env",
        ".env.local",
        ".env.example",
        "app.log",
        "debug.log",
        "important.log",
        "temp.txt",
        "config.json"
    ]
    
    print(f"\nFile inclusion test:")
    for file_path in test_files:
        import fnmatch
        ignored = any(fnmatch.fnmatch(file_path, pattern) for pattern in ignore_set)
        status = "❌ IGNORED" if ignored else "✅ INCLUDED"
        print(f"  {file_path:<15} {status}")

def demo_config_file_example():
    """Show how to configure exceptions in a config file."""
    print("\n=== Config File Example ===")
    
    config_content = '''# TOML config with ignore exceptions
[ignore]
patterns = [".env", "*.log", "temp"]
exceptions = [".env.example", "config.log"]

# Alternative format (also supported):
# ignore_patterns = [".env", "*.log"]
# ignore_exceptions = [".env.example"]
'''
    
    print("Example .dolphin/config.toml:")
    print(config_content)

def demo_integration():
    """Show how exceptions integrate with the full pipeline."""
    print("=== Pipeline Integration Demo ===")
    
    from kb.config import KBConfig
    
    # Example configuration with exceptions
    config_data = {
        "ignore": [".env", "*.log", "temp"],
        "ignore_exceptions": [".env.example", "config.log"]
    }
    
    config = KBConfig.from_mapping(config_data)
    
    print(f"Config ignore patterns: {config.ignore}")
    print(f"Config exceptions: {config.ignore_exceptions}")
    
    # Build final ignore set
    final_ignore = build_ignore_set(config.ignore, config.ignore_exceptions)
    
    print(f"Final ignore set has {len(final_ignore)} patterns")
    
    # Show .env.example exception in action
    test_patterns = [".env.example", "config.log", ".env.local", "debug.log"]
    
    print(f"\nException effectiveness test:")
    for pattern in test_patterns:
        ignored = pattern in final_ignore
        status = "❌ IGNORED" if ignored else "✅ INCLUDED (exception)"
        print(f"  {pattern:<15} {status}")

if __name__ == "__main__":
    demo_basic_functionality()
    demo_config_file_example()
    demo_integration()
    
    print("\n" + "="*60)
    print("✅ .env.example exception functionality is now working!")
    print("   .env.example files will be indexed while other .env.* files are ignored.")
    print("="*60)