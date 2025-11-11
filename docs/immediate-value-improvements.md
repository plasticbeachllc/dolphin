# Dolphin Immediate Value Improvements

**Focus**: Lightweight enhancements delivering immediate developer value
**Timeline**: Days to weeks, not months
**Priority**: User experience, productivity, and reliability

---

## Quick Win Projects

### 1. Agent Orchestration & Task Templates

**Value Proposition**: Pre-built AI workflows for common tasks reduce friction and improve consistency.

#### Function Templates

**Implementation**: Template system in `agent-core/src/templates/`

```typescript
// Built-in templates
templates/
  ├── debug.toml          # Debugging workflow
  ├── code-review.toml    # Review checklist
  ├── architect.toml      # Design analysis
  ├── document.toml       # Doc generation
  ├── test-gen.toml       # Test creation
  └── refactor.toml       # Safe refactoring
```

**Template Structure**:
```toml
[template]
name = "code-review"
description = "Comprehensive code review with best practices"
icon = "🔍"

[steps]
1 = { action = "search", query = "recent changes in {file}", context = "diff" }
2 = { action = "analyze", focus = ["security", "performance", "readability"] }
3 = { action = "checklist", items = ["tests", "docs", "error-handling"] }
4 = { action = "summarize", format = "markdown" }

[config]
auto_search_kb = true
include_tests = true
style_guide = ".dolphin/style-guide.md"
```

**Quick Implementation** (1 week):
- [ ] Template parser in agent-core
- [ ] 5 built-in templates (debug, review, architect, document, test)
- [ ] VSCode command palette integration: `Dolphin: Run Template`
- [ ] Template variables: `{file}`, `{selection}`, `{workspace}`
- [ ] User-defined templates in `.dolphin/templates/`

**User Experience**:
```
1. Right-click file → "Dolphin: Review This File"
2. Agent loads code-review.toml template
3. Automatically searches KB for context
4. Runs security, performance, style checks
5. Generates markdown report with issues + suggestions
```

#### Agent Orchestration Improvements

**Multi-Step Workflows**:
```typescript
// Current: Single prompt
await claude.sendMessage("Review this code")

// Enhanced: Orchestrated workflow
const workflow = new Workflow("code-review")
  .addStep("gather-context", { searchKB: true, includeDiff: true })
  .addStep("analyze-security", { tools: ["grep", "search"] })
  .addStep("check-tests", { findTests: true })
  .addStep("generate-report", { format: "markdown" })

await agent.execute(workflow)
```

**Features**:
- **Step visibility**: Show progress in webview ("Step 2/4: Analyzing security...")
- **Conditional branching**: Skip test generation if tests exist
- **Rollback**: Undo changes if user rejects
- **Resume**: Continue interrupted workflows
- **Audit trail**: Log all agent actions for review

**Quick Implementation** (3-4 days):
- [ ] Workflow class in agent-core
- [ ] Step progress indicator in webview
- [ ] Workflow state persistence (resume on crash)
- [ ] Simple branching: `if_condition` step type

---

### 2. Enhanced Agent Visibility & Transparency

**Value Proposition**: Users understand what the agent is doing and why, building trust and enabling better control.

#### Real-Time Action Stream

**Webview Enhancement**:
```svelte
<!-- Action timeline in sidebar -->
<ActionStream>
  <Action status="complete" time="2.3s">
    🔍 Searched KB for "authentication"
    <Results count={8} />
  </Action>

  <Action status="in-progress">
    📖 Reading src/auth/handler.ts
    <Progress percent={60} />
  </Action>

  <Action status="queued">
    ✏️ Generating test cases
  </Action>
</ActionStream>
```

**Quick Implementation** (2-3 days):
- [ ] Action events from agent-core via JSON-RPC
- [ ] Timeline component in webview
- [ ] Collapsible action details (show search results, files read)
- [ ] Action filtering (show only KB searches, edits, etc.)

#### Diff Viewer Enhancements

**Current State**: Basic diff viewing exists
**Enhancements**:

1. **Inline Diff Annotations**:
   ```typescript
   // Show AI reasoning inline
   + function authenticate(user: User) {
   + // AI: Added input validation for security
   +   if (!user || !user.id) throw new Error('Invalid user')
   ```

2. **Side-by-Side Comparison**:
   - Before/after in split view
   - Highlight AI changes in different color
   - Accept/reject individual hunks

3. **Diff History**:
   - Show all diffs in conversation
   - Jump to specific change
   - Undo specific edit without losing others

**Quick Implementation** (2-3 days):
- [ ] Inline annotation support in diff viewer
- [ ] Side-by-side toggle in webview
- [ ] Diff history panel with jump-to links

#### KB Search Visualization

**Show What the Agent Found**:
```svelte
<KBSearchResult query="authentication logic">
  <ResultCard rank={1} score={0.92}>
    <File>src/auth/handler.ts:45-67</File>
    <Snippet highlighted={true}>
      function authenticateRequest(req) { ... }
    </Snippet>
    <Metadata>
      Used in response: Yes
      Relevance: High
    </Metadata>
  </ResultCard>
</KBSearchResult>
```

**Features**:
- See all KB search results, not just what agent used
- Click result to jump to file
- Toggle: Show used vs. unused results
- Feedback: Mark results as helpful/not helpful

**Quick Implementation** (1-2 days):
- [ ] Expand KB tool call cards in webview
- [ ] Add "View All Results" button
- [ ] Click-to-open in editor
- [ ] Feedback buttons (improve future searches)

---

### 3. Semantic Search Quality Improvements

**Value Proposition**: Better search results = better AI responses and faster answers.

#### Query Quality Diagnostics

**In-Webview Search Debugger**:
```
Search: "where is authentication?"

📊 Query Analysis:
  - Intent: Code Lookup (95% confidence)
  - Key terms: authentication, auth, login
  - Expanded: ["authentication", "authenticateUser", "auth_handler"]

🎯 Search Strategy:
  - Vector search (embedding similarity)
  - BM25 keyword match
  - Graph: functions with "auth" in name

📈 Results:
  - 8 results found
  - Top score: 0.92 (very relevant)
  - Diversity: 0.78 (good variety)

💡 Suggestions:
  - Try: "authentication implementation"
  - Related: "login flow", "session management"
```

**Quick Implementation** (2-3 days):
- [ ] Query analysis endpoint in KB API
- [ ] Diagnostic panel in webview
- [ ] Query suggestions based on results
- [ ] Export diagnostics for debugging

#### Search Result Quality Feedback

**Thumbs Up/Down on Results**:
```typescript
// After each KB search, collect feedback
<SearchResult id="chunk-123">
  <Content>...</Content>
  <Feedback>
    <Button onClick={() => markRelevant(true)}>👍 Relevant</Button>
    <Button onClick={() => markRelevant(false)}>👎 Not Relevant</Button>
  </Feedback>
</SearchResult>

// Store feedback locally
.dolphin/feedback/search-feedback.jsonl
```

**Use Feedback to Improve**:
- Adjust ranking for similar queries
- Identify problematic queries (low ratings)
- Generate evaluation dataset from real usage
- Weekly report: "Search quality this week: 85% relevant"

**Quick Implementation** (2 days):
- [ ] Feedback buttons in webview
- [ ] Local storage (JSONL append-only log)
- [ ] Weekly digest command: `dolphin search-quality`
- [ ] Use feedback to boost/penalize similar results

#### Fast Approximate Search Mode

**Trade Quality for Speed**:
```toml
# .dolphin/config.toml
[search]
mode = "balanced"  # Options: fast, balanced, quality

[search.fast]
max_results = 5      # Fewer results
use_mmr = false      # Skip diversity
use_reranking = false # Skip cross-encoder
cache_ttl = 300      # Cache for 5 min

[search.quality]
max_results = 20
use_mmr = true
use_reranking = true
cache_ttl = 60
```

**Quick Implementation** (1 day):
- [ ] Add `mode` parameter to search API
- [ ] Implement fast path (skip expensive features)
- [ ] Expose in VSCode settings
- [ ] Show mode indicator in webview

---

### 4. Observability & Debuggability

**Value Proposition**: When things go wrong, users can diagnose and fix issues quickly.

#### Built-in Diagnostics

**Health Check Command**:
```bash
$ dolphin health

🏥 Dolphin Health Check

✅ OpenAI API: Connected (latency: 145ms)
✅ KB Server: Running (http://localhost:7777)
✅ SQLite: OK (database size: 45 MB)
✅ LanceDB: OK (3 collections, 12,450 chunks)
⚠️  Disk Space: 2.1 GB free (recommend >5 GB)
✅ Git: Available (version 2.39.0)

📊 Recent Activity:
  - Last index: 2 hours ago (my-project)
  - Searches today: 23
  - Avg search latency: 287ms

🔍 Common Issues: None detected

Run 'dolphin health --fix' to auto-repair issues.
```

**Quick Implementation** (2 days):
- [ ] Health check in KB CLI
- [ ] Check all dependencies and services
- [ ] Performance benchmarks (search 10 queries)
- [ ] Auto-fix common issues (restart KB, clear cache)

#### Detailed Logging

**Log Levels & Filtering**:
```bash
# Current: All or nothing
dolphin serve

# Enhanced: Configurable
dolphin serve --log-level info
dolphin serve --log-file ~/.dolphin/logs/kb-api.log
dolphin search "query" --debug  # Show search internals
```

**Log Format** (Structured JSON):
```json
{
  "timestamp": "2025-11-11T10:30:15.123Z",
  "level": "info",
  "component": "search",
  "message": "Vector search completed",
  "duration_ms": 45,
  "query": "[REDACTED]",
  "results": 8,
  "repo": "my-project"
}
```

**Quick Implementation** (1-2 days):
- [ ] Structured logging in KB API (Python `structlog`)
- [ ] Log level configuration (env var or CLI flag)
- [ ] Log file rotation (max 100 MB, keep 5 files)
- [ ] `dolphin logs` command to view recent logs

#### Performance Profiling

**Built-in Profiler**:
```bash
# Profile a search query
$ dolphin search "auth" --profile

Search Results: ...

⏱️ Performance Breakdown:
  Query embedding:     145ms (32%)
  Vector search:        87ms (19%)
  BM25 search:          34ms (8%)
  Re-ranking (MMR):     56ms (12%)
  Metadata fetch:       23ms (5%)
  Total:               445ms

💡 Optimization Ideas:
  - Enable query caching (would save ~200ms for repeated queries)
  - Reduce top_k from 20 to 10 (would save ~40ms)
```

**Quick Implementation** (2 days):
- [ ] Add `--profile` flag to search command
- [ ] Time each pipeline stage
- [ ] Show breakdown in webview for agent searches
- [ ] Suggest optimizations based on profile

#### Error Reporting

**Better Error Messages**:
```python
# Current
Error: Failed to connect to KB server

# Enhanced
Error: Failed to connect to KB server at http://localhost:7777

Possible causes:
  1. KB server is not running
     → Run: dolphin serve

  2. KB server is on different port
     → Check: dolphin config show | grep port

  3. Firewall blocking connection
     → Test: curl http://localhost:7777/v1/health

Need help? Run 'dolphin doctor' for automated diagnosis.
```

**Quick Implementation** (1 day):
- [ ] Enhance error messages with context and suggestions
- [ ] Link to docs for common errors
- [ ] Add error codes for easy searching
- [ ] Error reporting (optional telemetry)

---

### 5. No-Code Configuration & Setup

**Value Proposition**: Get started in 60 seconds without editing TOML files or running CLI commands.

#### Visual Configuration UI

**VSCode Settings Page**:
```svelte
<SettingsPage>
  <Section title="OpenAI Configuration">
    <Input
      label="API Key"
      type="password"
      secure={true}
      placeholder="sk-..."
      help="Get your key at platform.openai.com"
    />
    <Select
      label="Embedding Model"
      options={["text-embedding-3-small", "text-embedding-3-large"]}
      default="text-embedding-3-small"
      help="Large model: Better quality, 3x cost"
    />
  </Section>

  <Section title="Search Settings">
    <Slider
      label="Result Count"
      min={5}
      max={20}
      value={8}
      help="More results = better context, slower searches"
    />
    <Toggle
      label="Use Reranking"
      checked={false}
      help="20-30% better results, 2-3x slower"
    />
  </Section>

  <Section title="Repositories">
    <RepoList>
      <Repo name="my-project" status="indexed" chunks={1245} />
      <Button>+ Add Repository</Button>
    </RepoList>
  </Section>
</SettingsPage>
```

**Quick Implementation** (3-4 days):
- [ ] Settings webview route in extension
- [ ] Form components for all config options
- [ ] Save to `.dolphin/config.toml` on submit
- [ ] Validation and helpful error messages

#### Setup Wizard

**First-Run Experience**:
```
Step 1/4: Welcome to Dolphin 🐬
  [Video: 30-second overview]
  [Button: Get Started]

Step 2/4: Configure OpenAI
  [Input: API Key]
  [Link: Don't have a key? Get one here]
  [Button: Test Connection] ✅ Connected!

Step 3/4: Select Repositories
  [Checkbox] ✓ my-project (current workspace)
  [Checkbox] ✓ shared-library (detected in parent dir)
  [Button: Add Other Repository...]

Step 4/4: Index Your Code
  [Progress Bar: Indexing my-project... 45% (1,234/2,750 files)]
  Estimated time: 3 minutes

  ✅ Done! Your code is ready to search.
  [Button: Try a Search] [Button: Skip to Chat]
```

**Quick Implementation** (2-3 days):
- [ ] Multi-step wizard in webview
- [ ] Auto-detect repos in workspace
- [ ] Background indexing with progress
- [ ] Skip wizard if already configured

#### Smart Defaults

**Auto-Configuration**:
```typescript
// Detect project characteristics and configure accordingly
const projectProfile = {
  size: detectRepoSize(), // small, medium, large
  languages: detectLanguages(), // Python, TypeScript, etc.
  hasTests: existsSync('tests/') || existsSync('test/'),
  isMonorepo: detectMonorepo(),
}

// Recommend settings
if (projectProfile.size === 'large') {
  config.embedding_model = 'text-embedding-3-small' // Faster, cheaper
  config.search.top_k = 10 // Fewer results
  config.search.use_reranking = true // Better quality
}

if (projectProfile.languages.includes('Python')) {
  config.chunking.python.max_chunk_size = 512 // Smaller chunks
}
```

**Quick Implementation** (1-2 days):
- [ ] Project detection heuristics
- [ ] Recommended settings generator
- [ ] Show recommendations in setup wizard
- [ ] "Use recommended settings" button

#### One-Click Operations

**Common Tasks as Buttons**:
```svelte
<QuickActions>
  <Action icon="🔄" onClick={reindex}>
    Re-index Current Repo
    <Status>Last indexed: 2 hours ago</Status>
  </Action>

  <Action icon="🧹" onClick={clearCache}>
    Clear Search Cache
    <Status>Cache size: 45 MB</Status>
  </Action>

  <Action icon="📊" onClick={viewStats}>
    View Repository Stats
  </Action>

  <Action icon="🏥" onClick={runDiagnostics}>
    Run Health Check
  </Action>
</QuickActions>
```

**Quick Implementation** (1 day):
- [ ] Quick actions panel in webview
- [ ] Wire to existing CLI commands
- [ ] Show operation status (success/error)
- [ ] Progress indicators for long operations

---

## Implementation Priority

### Week 1-2: Foundation
1. **Agent Visibility** (3 days)
   - Action stream in webview
   - Expanded KB search results
   - Diff viewer enhancements

2. **Diagnostics** (2 days)
   - `dolphin health` command
   - Better error messages
   - Structured logging

### Week 3-4: Agent Orchestration
3. **Function Templates** (1 week)
   - Template system
   - 5 built-in templates
   - Command palette integration

4. **Workflow Progress** (2 days)
   - Step visibility
   - Progress indicators
   - State persistence

### Week 5-6: Search Quality
5. **Search Diagnostics** (3 days)
   - Query analysis
   - Result feedback
   - Search quality reports

6. **Performance** (2 days)
   - Search profiling
   - Fast mode
   - Cache improvements

### Week 7-8: User Experience
7. **Visual Configuration** (4 days)
   - Settings UI
   - Setup wizard
   - Smart defaults

8. **Quick Actions** (2 days)
   - One-click operations
   - Status indicators

---

## Success Metrics

**Quantitative**:
- Setup time: <60 seconds (from install to first search)
- Search satisfaction: >80% thumbs-up on results
- Agent transparency: Users understand 90%+ of agent actions
- Error resolution: 70% of errors self-diagnosed with `dolphin health`
- Template usage: 50%+ of sessions use at least one template

**Qualitative**:
- "I understand what the AI is doing"
- "Setup was painless"
- "Search results are relevant"
- "I can debug issues myself"
- "Templates save me time"

---

## Technical Notes

### No Breaking Changes
- All enhancements are additive
- Backward compatible with existing configs
- Templates are optional (fallback to current behavior)

### Minimal Dependencies
- Use existing UI components (shadcn/ui)
- No new heavy dependencies
- Reuse agent-core and KB API infrastructure

### Quick Wins First
- Prioritize high-impact, low-effort features
- Ship incrementally (weekly releases)
- Gather feedback and iterate

### User Testing
- Dogfood all features internally first
- Beta test with 5-10 external users
- Weekly feedback sessions
- Adjust based on real usage patterns

---

**Focus**: Ship fast, iterate quickly, maximize user value per development hour.
