#!/usr/bin/env python3
"""
Test script to demonstrate KiloCode migration from Dolphin personas
This shows what the migration would produce without running the full CLI
"""

import sys
import os
from pathlib import Path

# Add personas directory to path for imports
personas_dir = Path(__file__).parent / "personas" / "src"
sys.path.insert(0, str(personas_dir))

from persona_utils import load_persona, compile_system_message
from kilocode_utils import build_kilocode_mode_config

def demo_kilocode_migration():
    """Demonstrate KiloCode migration for working personas"""
    
    # Set up paths
    personas_root = Path(__file__).parent / "personas"
    personas_dir = personas_root / "cast"
    output_dir = Path(__file__).parent / "demo-output"
    
    print("🦄 Dolphin Personas → KiloCode Migration Demo")
    print("=" * 50)
    
    # Test personas that should work (have system.md)
    working_personas = ["chief-of-staff", "smartest-guy", "popeye"]
    
    print("\n📋 Testing personas that have system.md:")
    
    for persona_id in working_personas:
        try:
            persona_path = personas_dir / persona_id
            if not persona_path.exists():
                print(f"  ❌ {persona_id}: Directory not found")
                continue
                
            persona = load_persona(persona_path)
            
            # Load guardrails (simple version)
            try:
                guardrails_path = personas_root / "src" / "system.md"
                if guardrails_path.exists():
                    guardrails = guardrails_path.read_text(encoding="utf-8")
                else:
                    guardrails = "# Global Guardrails\n\nShared constraints for all personas."
            except:
                guardrails = "# Global Guardrails\n\nShared constraints for all personas."
            
            # Compile system message
            compiled, info = compile_system_message(
                system=persona.system_text,
                guardrails=guardrails,
                overlay="",
                model=persona.provider_model,
                budget=persona.token_budget,
            )
            
            print(f"\n✅ {persona_id}: {persona.name}")
            print(f"   Provider: {persona.provider_kind}:{persona.provider_model}")
            print(f"   Tokens: {info['final_tokens']}/{persona.token_budget}")
            
            # Build KiloCode config
            mode_config = build_kilocode_mode_config(persona, compiled)
            
            print(f"   KiloCode Mode: {mode_config['name']} ({mode_config['slug']})")
            print(f"   Model: {mode_config['model']}")
            print(f"   Instructions: {mode_config['instructions_file']}")
            
        except Exception as e:
            print(f"  ❌ {persona_id}: {e}")
    
    print("\n🔧 For personas with prompt.md (big-balls, deep-dive, etc.):")
    print("   These should work once the persona loading logic is fixed")
    print("   to accept prompt.md files in addition to system.md")
    
    print("\n📝 Example KiloCode Custom Mode Structure:")
    
    # Show example output structure
    example_structure = {
        "modes": {
            "popeye": {
                "name": "Popeye",
                "slug": "popeye",
                "model": "gpt-5",
                "provider": "openai",
                "instructions_file": "instructions/popeye-instructions.md",
                "context": {
                    "max_tokens": 1200,
                    "budget_management": "trim_oldest"
                }
            }
        },
        "instructions": {
            "popeye-instructions.md": "Full compiled system message..."
        },
        "workflows": {
            "persona-switch": "Slash command for mode switching"
        }
    }
    
    import json
    print(json.dumps(example_structure, indent=2))
    
    print("\n🚀 Commands to run once fixed:")
    print("   uv run personas/src/personas.py generate --kilocode --dry-run")
    print("   uv run personas/src/personas.py generate --kilocode")
    print("   uv run personas/src/personas.py generate --kilocode --global")

if __name__ == "__main__":
    demo_kilocode_migration()