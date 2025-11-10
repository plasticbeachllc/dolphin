# Dolphin MCP Tools Review

**Date**: 2025-11-10
**Reviewer**: Claude Code
**Purpose**: Analyze tool duplication and alignment with Claude Code's standard toolset

---

## Executive Summary

**Key Findings**:
1. ✅ **2 duplicate tool implementations found** in old `/tools/` directory (not in use)
2. ⚠️ **2 tools overlap** with Claude Code's built-in capabilities (`read_files`, `file_write`)
3. ⚠️ **1 tool partially overlaps** with built-in Read tool (`fetch_lines`)
4. ✅ **5 tools are unique** and provide valuable semantic search capabilities
5. ⚠️ **Alignment concern**: Claude is trained on different tool names/schemas

---

## Current Tool Inventory

### Active Tools (8 total)
Located in: `/home/user/dolphin/mcp-bridge/src/mcp/tools/`

| Tool | Purpose | Status |
|------|---------|--------|
| `search_knowledge` | Semantic code search with vector embeddings | ✅ Unique |
| `fetch_chunk` | Retrieve code chunk by ID | ✅ Unique |
| `fetch_lines` | Fetch file slice by line range | ⚠️ Partial overlap |
| `open_in_editor` | Generate VS Code URIs | ✅ Unique |
| `get_vector_store_info` | Vector store metadata | ✅ Unique |
| `get_metadata` | Chunk metadata retrieval | ✅ Unique |
| `file_write` | Write files with backup | ⚠️ Duplicates built-in |
| `read_files` | Batch read multiple files | ⚠️ Duplicates built-in |

### Inactive Duplicate Files (2 total)
Located in: `/home/user/dolphin/mcp-bridge/src/tools/`

- `read-files.ts` - Old version (not imported/used)
- `file-write.ts` - Old version (not imported/used)

**Recommendation**: Delete these files to avoid confusion.

---

## Detailed Analysis

### 1. `read_files` - Duplicates Claude Code's Built-in `Read` Tool

**Dolphin Implementation**:
- Location: `mcp-bridge/src/mcp/tools/read-files-tool.ts`
- Batch reads up to 50 files
- Returns structured JSON with metadata (size, line count, last modified)
- Workspace boundary security checks
- Partial failure handling with `fail_on_error` flag
- 1MB default size limit per file

**Claude Code Built-in `Read` Tool**:
- Single file reading
- Returns cat-style output with line numbers
- Supports offset/limit for large files
- Reads images, PDFs, Jupyter notebooks
- No batch capability

**Key Differences**:
| Feature | Dolphin `read_files` | Claude `Read` |
|---------|---------------------|---------------|
| Batch reads | ✅ Up to 50 files | ❌ Single file only |
| Output format | JSON with metadata | cat-style with line numbers |
| Partial failures | ✅ Graceful handling | N/A |
| Multimodal | ❌ Text only | ✅ Images, PDFs, notebooks |
| Metadata | ✅ Size, lines, modified | ❌ Not included |

**Recommendation**:
- **KEEP** `read_files` if batch reading is core to Dolphin's workflow
- **OR REMOVE** if Claude Code can make multiple parallel `Read` calls efficiently
- Consider: Claude can already make parallel tool calls, making batch functionality less critical

---

### 2. `file_write` - Duplicates Claude Code's Built-in `Write` Tool

**Dolphin Implementation**:
- Location: `mcp-bridge/src/mcp/tools/file-write-tool.ts`
- Atomic writes using temp file + rename
- Automatic backup creation (default: enabled)
- Auto-creates parent directories
- Workspace boundary security (rejects absolute paths)
- Returns structured JSON with write metadata

**Claude Code Built-in `Write` Tool**:
- Direct file overwriting
- Requires prior Read if file exists
- No automatic backups
- No automatic directory creation

**Key Differences**:
| Feature | Dolphin `file_write` | Claude `Write` |
|---------|---------------------|----------------|
| Atomic writes | ✅ Temp + rename | ❌ Direct overwrite |
| Backups | ✅ Automatic | ❌ None |
| Dir creation | ✅ Auto with flag | ❌ Manual |
| Security | ✅ Rejects absolute paths | ✅ General protection |
| Metadata | ✅ Returns details | ❌ Simple confirm |

**Recommendation**:
- **KEEP** `file_write` - significantly safer with atomic writes and backups
- These features are valuable for production use cases
- However, consider Claude Code may prefer its familiar `Write` tool interface

---

### 3. `fetch_lines` - Partially Overlaps with Built-in `Read` Tool

**Dolphin Implementation**:
- Location: `mcp-bridge/src/mcp/tools/fetch_lines.ts`
- Fetches from Dolphin REST API (not direct filesystem)
- Requires: `repo`, `path`, `start`, `end` (line range)
- Returns fenced code block with citation
- Returns MCP resource format with MIME type
- Designed for knowledge base integration

**Claude Code Built-in `Read` Tool**:
- Reads from local filesystem
- Supports offset/limit for line ranges
- Returns cat-style with line numbers
- No citation or resource formatting

**Key Differences**:
| Feature | Dolphin `fetch_lines` | Claude `Read` |
|---------|----------------------|---------------|
| Source | REST API (KB) | Local filesystem |
| Citation | ✅ Included | ❌ None |
| Resource format | ✅ MCP resource | ❌ Plain text |
| Repo awareness | ✅ Required param | ❌ N/A |

**Recommendation**:
- **KEEP** `fetch_lines` - fundamentally different from `Read`
- Serves knowledge base retrieval, not file system access
- Not actually duplicative despite similar line-range functionality

---

### 4. Unique Tools (No Overlap)

#### ✅ `search_knowledge`
- **Purpose**: Semantic vector search across indexed repositories
- **Status**: Core differentiation, no Claude equivalent
- **Features**: Graph context, MMR/ANN strategies, filtering, parallel snippet fetching
- **Recommendation**: **KEEP** - primary value proposition

#### ✅ `fetch_chunk`
- **Purpose**: Retrieve indexed code chunks by ID
- **Status**: Knowledge base specific, no Claude equivalent
- **Recommendation**: **KEEP** - essential for KB workflow

#### ✅ `get_vector_store_info`
- **Purpose**: Vector store introspection
- **Status**: Utility for KB system
- **Recommendation**: **KEEP** - helpful for debugging/transparency

#### ✅ `get_metadata`
- **Purpose**: Chunk metadata retrieval
- **Status**: KB-specific utility
- **Recommendation**: **KEEP** - supports chunk inspection

#### ✅ `open_in_editor`
- **Purpose**: Generate `vscode://file` URIs
- **Status**: Integration utility, no Claude equivalent
- **Recommendation**: **KEEP** - useful for IDE integration

---

## Alignment with Claude Code Training

### What Claude Code is Trained On

Claude Code's documentation and training data include these standard tools:

**File Operations**:
- `Read` - read single files with line numbers
- `Write` - write/overwrite files
- `Edit` - string replacement edits
- `Glob` - pattern-based file finding

**Search**:
- `Grep` - regex content search with ripgrep
- `Glob` - file pattern matching

**Execution**:
- `Bash` - shell command execution
- `Task` - spawn specialized agents

**Other**:
- `TodoWrite` - task management
- `WebFetch` - fetch web content
- `WebSearch` - search the web
- `NotebookEdit` - edit Jupyter notebooks

### Alignment Concerns

#### ⚠️ Tool Name Mismatch
Claude is trained to use:
- `Read` not `read_files`
- `Write` not `file_write`

**Impact**: Claude may not naturally discover or prefer Dolphin's tools even if they're superior.

#### ⚠️ Schema Differences
Claude expects:
- `Read` takes `file_path`, optional `offset`/`limit`
- `Write` takes `file_path`, `content`

Dolphin provides:
- `read_files` takes `paths[]`, `max_size_bytes`, `fail_on_error`
- `file_write` takes `path`, `content`, `create_backup`, `create_directories`

**Impact**: Claude must "learn" new schemas at inference time via tool descriptions.

#### ⚠️ Batch vs Single Operations
- Claude is trained to make **parallel single-file calls**
- Dolphin provides **batch operations in single call**

**Impact**: Unclear which approach Claude will prefer.

---

## Recommendations

### Immediate Actions

#### 1. Clean Up Duplicate Files
```bash
rm /home/user/dolphin/mcp-bridge/src/tools/read-files.ts
rm /home/user/dolphin/mcp-bridge/src/tools/file-write.ts
```

**Rationale**: Reduce confusion, these are not imported/used.

#### 2. Evaluate `read_files` Necessity

**Option A - Remove `read_files`**:
- Let Claude use built-in `Read` tool with parallel calls
- Simpler mental model aligned with training
- Loses batch convenience and metadata

**Option B - Keep `read_files`**:
- Retain batch capability and structured metadata
- Accept that Claude may prefer familiar `Read` tool
- Consider usage patterns: is batching actually used?

**Recommendation**: **Remove unless batch reading is actively used/needed**

#### 3. Evaluate `file_write` Necessity

**Option A - Remove `file_write`**:
- Let Claude use built-in `Write` tool
- Aligned with training data
- Loses atomic writes and backups

**Option B - Keep `file_write`**:
- Retain safety features (atomic, backups)
- Accept potential tool preference issues
- Valuable for production safety

**Recommendation**: **Keep `file_write`** - safety features are valuable enough to justify the duplication

#### 4. Consider Renaming for Alignment

If keeping custom tools, consider renaming to be more distinctive:
- `read_files` → `dolphin_read_batch` or remove entirely
- `file_write` → `dolphin_write_safe` or keep as differentiator

**Rationale**: Clearly signal these are Dolphin-specific extensions, not replacements.

### Strategic Considerations

#### Tool Discovery
- Claude will see all tools in the MCP tools list
- Tool descriptions must clearly explain when to use each
- Consider adding guidance like "Use this for batch operations" or "Use for safer atomic writes"

#### Performance Testing
- Test whether Claude prefers batch `read_files` or parallel `Read` calls
- Measure actual performance differences
- User experience may differ from theoretical benefits

#### Documentation Clarity
- Update tool descriptions to clarify relationship with built-in tools
- Example: "Similar to built-in Write but with atomic operations and automatic backups"

---

## Conclusion

**Summary**:
1. **Delete 2 old duplicate files** in `/tools/` directory
2. **Consider removing `read_files`** - likely redundant with parallel `Read` calls
3. **Keep `file_write`** - safety features justify the duplication
4. **Keep all 5 unique tools** - they provide core Dolphin functionality
5. **Clarify tool descriptions** - help Claude understand when to use Dolphin tools vs built-ins

**Overall Assessment**:
The tool set is largely well-designed with minimal true duplication. The main concern is alignment with Claude's training data, which may cause it to prefer built-in tools over Dolphin's custom implementations even when the custom versions are superior.

**Next Steps**:
1. Delete unused duplicate files
2. Discuss `read_files` removal with team
3. Update tool descriptions for clarity
4. Monitor usage patterns to validate decisions
