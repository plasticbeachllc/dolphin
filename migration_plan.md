# Dolphin Personas → KiloCode Custom Modes Migration Plan

## Overview
This document outlines the migration strategy from the current Dolphin personas system to KiloCode's Custom Modes, leveraging KiloCode's configuration templating capabilities.

## Current System Analysis

### Dolphin Personas Structure
```
personas/
├── cast/
│   ├── smartest-guy/
│   │   ├── persona.toml          # Metadata & configuration
│   │   └── system.md            # System prompt
│   ├── journalist/
│   │   ├── persona.toml
│   │   └── prompt.md
│   └── deep-dive/
│       ├── persona.toml
│       └── prompt.md
└── src/
    ├── personas.py              # Main CLI and generation logic
    ├── persona_utils.py         # Core utilities
    └── system.md               # Shared guardrails
```

### KiloCode Custom Modes Structure
```
kilocode-config/
├── modes/
│   ├── smartest-guy.json       # Custom Mode configuration
│   ├── journalist.json
│   └── deep-dive.json
├── instructions/               # Custom Instructions
│   ├── smartest-guy-instructions.md
│   └── journalist-instructions.md
├── rules/                     # Custom Rules
│   └── global-guardrails.md
└── workflows/                 # Slash Commands & Workflows
    └── persona-workflows.md
```

## Migration Mapping Strategy

### 1. Direct Component Mapping

| Current Component | KiloCode Equivalent | Implementation |
|------------------|---------------------|----------------|
| `persona.toml` → `[persona]` | Custom Mode Metadata | Mode name, description, display info |
| `persona.toml` → `[provider]` | Model Configuration | Provider type, model name, API settings |
| `persona.toml` → `[params]` | Mode Parameters | Temperature, max_tokens, etc. |
| `persona.toml` → `[system]` | Custom Instructions | Token budget, behavior settings |
| `system.md/prompt.md` | Custom Instructions | System prompts, behavioral guidelines |
| Shared `system.md` | Global Rules | Common guardrails across all modes |

### 2. Enhanced KiloCode Features

| Feature | Current Support | KiloCode Enhancement |
|---------|----------------|---------------------|
| Token Budgeting | ✅ Manual management | ✅ Automatic with KiloCode limits |
| Provider Config | ✅ Static TOML | ✅ Dynamic configuration |
| System Prompts | ✅ Static files | ✅ Template-based with variables |
| Parameter Tuning | ✅ Hardcoded | ✅ Runtime adjustable |
| Workflows | ❌ Not available | ✅ Slash commands & automation |

## Implementation Roadmap

### Phase 1: Migration Framework (Week 1-2)
- [ ] Build `persona_to_kilocode.py` migration utility
- [ ] Create KiloCode config templates
- [ ] Implement provider mapping logic
- [ ] Handle parameter translation

### Phase 2: Configuration Generation (Week 2-3)
- [ ] Generate Custom Mode JSON files
- [ ] Create Custom Instructions from system prompts
- [ ] Build Custom Rules from guardrails
- [ ] Implement workflow automation

### Phase 3: Testing & Validation (Week 3-4)
- [ ] Test migration with all existing personas
- [ ] Validate KiloCode configuration syntax
- [ ] Test mode switching and functionality
- [ ] Performance comparison

### Phase 4: Documentation & Rollout (Week 4)
- [ ] Create migration guide
- [ ] Document KiloCode-specific enhancements
- [ ] Provide rollback procedures
- [ ] User training materials

## Migration Utilities Design

### Core Components

1. **PersonaAnalyzer**: Parse and analyze current personas
2. **ConfigMapper**: Map persona components to KiloCode format
3. **TemplateGenerator**: Generate KiloCode configuration files
4. **Validator**: Ensure generated configs are valid
5. **MigrationRunner**: Orchestrate the complete migration

### Key Design Decisions

1. **Backward Compatibility**: Keep original personas as reference
2. **Incremental Migration**: Support partial/complete migration
3. **Validation**: Ensure all generated configs work
4. **Customization**: Allow user modifications during migration

## Benefits of Migration

### Immediate Benefits
- ✅ Leverage KiloCode's native configuration management
- ✅ Access to KiloCode's UI for mode management
- ✅ Automatic parameter optimization
- ✅ Built-in workflow automation

### Enhanced Capabilities
- 🔄 Dynamic mode switching
- 🔄 Real-time configuration updates
- 🔄 Advanced parameter tuning
- 🔄 Integration with KiloCode's ecosystem

## Risk Assessment

### Technical Risks
- **Configuration Compatibility**: KiloCode may have different parameter limits
- **Migration Complexity**: Complex persona features may not map cleanly
- **Testing Coverage**: Need comprehensive validation of migrated modes

### Mitigation Strategies
- **Incremental Migration**: Start with simple personas, add complexity
- **Validation Tools**: Build thorough testing and validation
- **Rollback Plan**: Maintain original personas during transition

## Next Steps

1. Build core migration utilities
2. Create configuration templates
3. Test with sample personas
4. Validate KiloCode integration
5. Prepare migration documentation

---

**Status**: Planning Complete - Ready for Implementation
**Owner**: Kilo Code Migration Team
**Timeline**: 4 weeks to full migration