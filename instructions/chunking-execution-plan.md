# Chunking Execution Plan (Phase 4)

Purpose
- Implement robust, token-aware chunking for code and Markdown to prepare content for embeddings.
- Preserve provenance (precise start/end line ranges) and attach useful metadata (symbol info, headings) without embedding it.
- Keep dependencies minimal and rely on mature low-level libraries where it matters.

Guiding principles
- Token-aware windows: ~400 tokens per chunk with ~10% overlap (configurable).
- Stable provenance: 1-based inclusive start_line/end_line mapped to original files.
- Language-aware where it pays off: Tree-sitter for Python and TypeScript/TSX; simple heading extraction for Markdown.
- Idempotency friendly: chunk text canonicalized; hashing and dedup come in Phase 5.

Dependencies
- tiktoken (already present): model-aware tokenization and counts.
- tree_sitter (already present) + tree_sitter_languages (added): prebuilt grammars for Python and TS/TSX.
- markdown-it-py (added): robust Markdown parsing with AST and source line mapping.
- pyyaml (already present): YAML front matter parsing and title extraction.

Data contracts
- Extend Chunk (src/pb_kb/chunkers/__init__.py) to include optional heading metadata:
  - text: str (canonicalized; for embedding)
  - start_line: int (1-based inclusive)
  - end_line: int (1-based inclusive)
  - token_count: int (computed by tiktoken)
  - symbol_kind: str | None (function|class|method|module)
  - symbol_name: str | None
  - symbol_path: str | None (e.g., "path/to/file.py:Class.method")
  - h1: str | None (Markdown only)
  - h2: str | None (Markdown only)
  - h3: str | None (Markdown only)

Configuration knobs (defaults)
- token_target = 400
- overlap_pct = 0.10 (window overlap fraction)
- tolerance = ±15% (to avoid awkward splits)
- model = "small" | "large" (selects tokenizer)

Interfaces
- chunk_file(language: str, abs_path: Path, rel_path: str, text: str, *, model: str = "small", token_target: int = 400, overlap_pct: float = 0.10) -> list[Chunk]
- get_chunker(language: str) -> Callable[[...], list[Chunk]] (simple registry)

Tokenizer utilities (new)
- get_tokenizer(model: str) -> tiktoken tokenizer
- count_tokens(text: str, tokenizer) -> int
- window_tokens(tokens: list[int], *, target: int, overlap: int) -> iterable of (start_idx, end_idx)
- recompose_text(original_text: str, token_indices, tokenizer) -> str (only if needed; preferred approach is slicing via character/line offsets when possible)

Line-range mapping
- Primary: when symbol nodes provide byte ranges, map byte offsets to 1-based line numbers using a precomputed byte-to-line index for the file.
- Secondary: when chunk text comes from splitter heuristics (Markdown sections, fallback windows), map via binary search on precomputed line-start offsets:
  - Build a list of character offsets where each line starts in the section text.
  - For each window, find its first occurrence at/after the previous match.
  - Convert the match's char offset to a line number via bisect on the line-start offsets.
  - end_line = start_line + count('\n' in window_text).
  - If not found, fall back to approximation and log debug warning.

Markdown chunker (robust - ✅ IMPLEMENTED)
- Uses markdown-it-py for reliable AST parsing with source line maps.
- Extracts YAML front matter with title support (sets initial H1 if present).
- Maintains current nearest headings (H1, H2, H3) as state through section boundaries.
- Builds section text excluding heading line(s). For very long sections, applies token windows with overlap.
- Emits Chunk(s) with h1/h2/h3 set, token_count computed on trimmed text (newlines only), start_line/end_line via binary-search mapping.
- Headings excluded from embedded text but included as metadata.

Python chunker (Tree-sitter)
- Load Python parser from tree_sitter_languages.
- Identify symbols:
  - class_definition (class)
  - function_definition at module level (function)
  - function_definition inside class (method)
- For each symbol:
  - Compute start/end byte offsets from node; convert to 1-based line numbers.
  - Extract text slice (body; header line may optionally be included; decide: include full def/ class block for context, but chunk should reflect actual lines indexed).
  - Build symbol_kind/name/path (path = f"{rel_path}:{Class.method}" or "{rel_path}:{func}").
  - If token_count > token_target*(1 + tolerance), split into token windows with overlap within the body range.
- If parse fails or file contains no symbols, fall back to token windowing over the whole file.

TypeScript/TSX chunker (Tree-sitter)
- Load TS/TSX parser from tree_sitter_languages.
- Identify symbols:
  - class_declaration (class)
  - method_definition (method)
  - function_declaration (function)
  - variable_declaration with arrow function initializer (const name = (...) => { ... }) treated as function "name"
  - export default functions/classes (use name if present else "default")
- Apply the same body extraction, line mapping, symbol metadata, and windowing strategy as Python.

Fallback chunker (token windows)
- For unknown languages or parse failures, chunk by tokens with overlap across the entire file.
- Maintain stable start_line/end_line via line-windowing or forward cursor mapping.

Registry
- python -> python symbol chunker
- typescript, typescriptreact -> ts/tsx symbol chunker
- markdown -> markdown chunker
- default -> fallback chunker

Integration with pipeline (Phase 4 only)
- After Phase 3 scan, for each file candidate, call chunk_file(...) to get list[Chunk].
- Aggregation step: compute per-file total tokens and prepare for Phase 5 hashing.
- Do not persist chunk_texts or chunks_meta in Phase 4 (to avoid orphans). Persist in Phase 6 after idempotency checks and embeddings.

Testing strategy
- Unit tests
  - Markdown: headings are captured in h1/h2/h3; excluded from text; windows obey token_target/overlap; code fences ignored in heading scan.
  - Python: detect classes/functions/methods; produce correct symbol_kind/name/path; line ranges reflect node extents; large bodies windowed.
  - TS/TSX: detect classes/functions/methods/arrow functions; correct metadata; windowing works.
  - Fallback: token windows produce chunks with correct overlap; small files single chunk; line ranges consistent.
  - Token counts: all chunks have token_count > 0 and ~target with allowed tolerance; overlap ~overlap_pct.
- Integration tests
  - End-to-end on a small fixture repo with .py, .ts/.tsx, .md: produce chunk lists; verify metadata and approximate token sizes; ensure deterministic results across runs.

## Implementation Status

### ✅ Completed
1) Extended Chunk dataclass to support h1/h2/h3 and token_count
2) Implemented tokenizer utilities and windowing helpers (tiktoken-backed, 400 tokens, 10% overlap)
3) Implemented robust Markdown chunker using markdown-it-py:
   - YAML front matter extraction with title support
   - AST-based heading and fence detection
   - Binary-search line mapping for precise start_line/end_line
   - Trimming logic preserving indentation (strip newlines only)

### 🎯 Next Priority
4) Implement Python symbol chunker (Tree-sitter):
   - class_definition, function_definition, method detection
   - Hierarchical symbol_path: "rel_path:Class.method"
   - Token windowing for large symbols (>440 tokens)
   - Line mapping via tree-sitter node byte offsets
   - Fallback to token windowing on parse failure

### 📋 Remaining Sequence
5) Implement TS/TSX symbol chunker (same pattern as Python)
6) Implement fallback chunker (token windowing for unknown languages)
7) Wire registry and integrate with pipeline (Phase 4 emit-only)
8) Add unit tests for all chunkers and basic integration test

Performance and ergonomics
- Cache tree-sitter parsers per language.
- Avoid excessive allocations while tokenizing; reuse tokenizers.
- Concurrency: keep at current default (3) and adjust later if needed.
- Logging: no chunk text; log counts and identities only.

## Technical Decisions (Confirmed)
- **Symbol body span:** Include full construct (signature + body) for context; window inside body if very large (>440 tokens).
- **symbol_path format:** Use rel_path consistently (e.g., "src/app.py:MyClass.method").
- **Token target:** Keep 400 tokens for both small/large models in Sprint 1.
- **Trimming:** Strip leading/trailing newlines only (preserve indentation and spaces).
- **Line mapping:** Binary search on precomputed line-start offsets for robustness and performance.

## Architecture Notes
- **Markdown parsing:** Uses markdown-it-py for reliable heading/fence detection instead of custom state machine
- **Front matter:** Returns (offset, title) with YAML parsing for initial H1 seeding
- **Performance:** Cache tree-sitter parsers per language; binary-search mapping scales O(W log L)
