# Golden Scenarios

This directory contains curated test cases for evaluating Dolphin's retrieval quality.

## Structure

```
golden-scenarios/
├── code-search/           # Find specific code elements
│   ├── exact-match/      # Simple name lookups
│   └── description-based/# Natural language queries
├── semantic-search/       # Conceptual queries
│   └── architecture/     # System concepts
├── hybrid-search/         # Combined exact + semantic
│   └── framework-specific/# Technology-specific queries
└── navigation/            # Cross-file relationships
    └── usages/           # Find usages/references
```

## Running Evaluation

```bash
# Evaluate all scenarios
python scripts/eval_retrieval.py --scenarios golden-scenarios/

# Evaluate specific category
python scripts/eval_retrieval.py --scenarios golden-scenarios/code-search/

# Single scenario
python scripts/eval_retrieval.py --scenario golden-scenarios/code-search/exact-match/lancedb-store.json
```

## Adding Scenarios

1. Create JSON file in appropriate category
2. Follow schema in `docs/benchmarking/golden-scenarios.md`
3. Test with: `python scripts/eval_retrieval.py --scenario <file>`
4. Commit with descriptive message

## Maintenance

- Update scenarios when code structure changes
- Add scenarios for new features
- Remove scenarios for deleted functionality
- Keep difficulty distribution balanced (50% easy, 35% medium, 15% hard)

## Current Coverage

Run `python scripts/analyze_coverage.py` to see current scenario distribution.
