# EP-6: Risk Register

**Project**: EP-6 - Performance Optimization Suite  
**Last Updated**: 2025-11-11  
**Version**: 1.0

---

## Risk Assessment Matrix

| Probability | Impact Low (1-3) | Impact Medium (4-7) | Impact High (8-10) |
|-------------|------------------|---------------------|-------------------|
| **High (70-100%)** | Medium Risk | High Risk | Critical Risk |
| **Medium (30-69%)** | Low Risk | Medium Risk | High Risk |
| **Low (0-29%)** | Low Risk | Low Risk | Medium Risk |

**Risk Score = Probability (%) × Impact (1-10)**

**Risk Levels**:
- **Critical**: Score 70-100 (Immediate action required)
- **High**: Score 40-69 (Close monitoring and mitigation required)
- **Medium**: Score 15-39 (Monitor and prepare mitigation)
- **Low**: Score 0-14 (Acknowledge and track)

---

## Active Risks

### Risk #1: Parallel Processing Introduces Race Conditions

**Risk ID**: EP6-R001  
**Category**: Technical  
**Phase**: Phase 2 (Indexing Optimization)

**Description**:
Implementing parallel file processing with multiprocessing may introduce race conditions when multiple workers attempt to write to shared resources (SQLite, LanceDB, file system). This could lead to data corruption, incorrect vector embeddings, or duplicate entries.

**Probability**: Medium (40%)  
**Impact**: High (9 - data corruption)  
**Risk Score**: 36 (High Risk)

**Indicators**:
- Test failures in concurrent scenarios
- Data inconsistencies in vector database
- Duplicate chunk IDs in SQLite
- Intermittent test failures
- Deadlocks or timeouts during indexing

**Mitigation Strategy**:
1. **Design Phase**:
   - Design immutable data structures for inter-process communication
   - Use file-level locking for critical sections (SQLite writes)
   - Implement atomic operations for database updates
   - Queue-based work distribution to avoid shared state

2. **Implementation Phase**:
   - Use `multiprocessing.Queue` for worker communication
   - Implement single writer thread for database updates
   - Use context managers for resource locking
   - Comprehensive logging of concurrent operations

3. **Testing Phase**:
   - Create stress tests with 50+ concurrent workers
   - Test with large repos (50K+ files)
   - Simulate worker failures and recovery
   - Run tests with ThreadSanitizer/DataRaceSanitizer if available

4. **Code Review**:
   - Dedicated code review focused on concurrency
   - Use static analysis tools (pylint, mypy with concurrency checks)
   - Review all shared state access patterns

**Contingency Plan**:
- Fall back to sequential processing as default
- Make parallel processing opt-in via configuration flag
- Limit number of workers to 2-4 initially (safer)
- Implement rollback mechanism for corrupted data
- Provide data validation tool to detect corruption

**Owner**: Lead Engineer  
**Review Date**: End of Week 2  
**Status**: 🟡 Monitoring

---

### Risk #2: LanceDB Performance Doesn't Scale as Expected

**Risk ID**: EP6-R002  
**Category**: Technical  
**Phase**: Phase 3 (Search Optimization)

**Description**:
LanceDB may not provide the expected performance improvements at scale (100K+ files), especially with complex queries or high concurrency. The IVF index may not be as efficient as expected, or the pre-filtering strategy may not reduce search space sufficiently.

**Probability**: Low (20%)  
**Impact**: High (9 - fails to meet latency targets)  
**Risk Score**: 18 (Medium Risk)

**Indicators**:
- Search latency >500ms with 100K file repo
- KNN search time dominates query execution
- IVF_PQ index doesn't improve performance
- Pre-filtering provides <50% search space reduction
- Concurrent queries cause performance degradation

**Mitigation Strategy**:
1. **Early Validation**:
   - Profile LanceDB queries in Phase 1 (baseline)
   - Test with 100K+ file repos early (Week 2)
   - Benchmark different index types (IVF_FLAT vs IVF_PQ)
   - Engage with LanceDB community for optimization tips

2. **Optimization Techniques**:
   - Experiment with different nprobes values (10, 20, 50, 100)
   - Test approximate filtering with refinement
   - Consider index parameters tuning (nlist, pq_m, nbits)
   - Implement query result caching aggressively (Phase 3)

3. **Alternative Evaluation**:
   - Keep Faiss/Annoy evaluation in backlog
   - Document LanceDB limitations if discovered
   - Prepare benchmark suite for alternative vector DBs

**Contingency Plan**:
- Evaluate Faiss in Phase 5 if LanceDB underperforms
- Consider hybrid approach: LanceDB for <50K files, Faiss for >50K
- Implement more aggressive caching to compensate
- Consider pre-computed embeddings for common queries
- Fall back to BM25-only search for extremely large repos

**Owner**: Lead Engineer  
**Review Date**: End of Week 4  
**Status**: 🟢 Monitoring

---

### Risk #3: Cache Invalidation Bugs Lead to Stale Results

**Risk ID**: EP6-R003  
**Category**: Technical  
**Phase**: Phase 3 (Search Optimization)

**Description**:
Query result caching introduces the risk of serving stale results if cache invalidation logic has bugs. Users may see outdated search results after reindexing, leading to confusion and incorrect code context.

**Probability**: Medium (30%)  
**Impact**: High (8 - incorrect search results)  
**Risk Score**: 24 (Medium Risk)

**Indicators**:
- User reports of outdated search results
- Test failures in cache invalidation tests
- Cache hit rate >90% (suspiciously high)
- Inconsistent results between cached and non-cached queries
- Cache not cleared after reindex

**Mitigation Strategy**:
1. **Conservative Invalidation**:
   - Invalidate entire cache on any index update (initial approach)
   - Track `last_indexed_at` timestamp per repo
   - Compare query time with repo's `last_indexed_at`
   - Invalidate only affected repo caches (optimization)

2. **Testing Strategy**:
   - Comprehensive integration tests for cache behavior
   - Test scenarios: reindex single file, add new file, delete file
   - Test concurrent reindex and search
   - Automated cache correctness validation

3. **User Control**:
   - Manual cache clear endpoint (`POST /api/cache/clear`)
   - Cache clear button in UI
   - "Bypass cache" query parameter for debugging
   - Show cache status in search results (for development)

4. **Monitoring**:
   - Log all cache invalidations with reason
   - Alert if cache not invalidated after reindex
   - Track cache correctness metrics (false positives)

**Contingency Plan**:
- Disable caching by default, make opt-in
- Implement conservative TTL (1 minute) initially
- Provide cache versioning to detect stale entries
- Add "fresh search" button in UI that bypasses cache
- Document cache behavior and limitations clearly

**Owner**: Lead Engineer  
**Review Date**: End of Week 5  
**Status**: 🟡 Monitoring

---

### Risk #4: Compression Overhead Negates Storage Savings

**Risk ID**: EP6-R004  
**Category**: Technical  
**Phase**: Phase 4 (Storage Optimization)

**Description**:
Content compression with zstd may introduce significant decompression overhead (>50ms) that negates the storage savings. This would increase search latency and reduce user experience, making the optimization counterproductive.

**Probability**: Low (20%)  
**Impact**: Medium (6 - storage goals not met, latency increased)  
**Risk Score**: 12 (Medium Risk)

**Indicators**:
- Decompression time >50ms per query
- Search latency increases by >30% with compression
- CPU usage spikes during search
- User complaints about slow search
- Storage savings <40% (not worth the overhead)

**Mitigation Strategy**:
1. **Benchmarking**:
   - Benchmark compression on representative data (Phase 1)
   - Test decompression on target hardware (MacBook Pro M4)
   - Measure compression ratio for various content types
   - Profile CPU usage during decompression

2. **Configuration**:
   - Make compression opt-in via configuration
   - Provide compression level tuning (1-22 for zstd)
   - Allow selective compression (e.g., only large chunks)
   - Document trade-offs clearly

3. **Optimization**:
   - Cache decompressed content in memory (LRU)
   - Compress only infrequently accessed data
   - Use faster compression (lz4) if zstd is too slow
   - Benchmark alternative compression algorithms

**Contingency Plan**:
- Disable compression if overhead >20ms per query
- Offer compression as optional feature for disk-constrained users
- Use lz4 (faster, lower ratio) instead of zstd
- Compress only archived data, not active chunks
- Accept lower storage savings if latency is critical

**Owner**: Lead Engineer  
**Review Date**: End of Week 6, Day 2  
**Status**: 🟢 Monitoring

---

### Risk #5: MessagePack IPC Breaks Existing Functionality

**Risk ID**: EP6-R005  
**Category**: Technical  
**Phase**: Phase 4 (Runtime Optimization)

**Description**:
Replacing JSON serialization with MessagePack for IPC may break existing message types or introduce encoding/decoding bugs. This could cause extension crashes, agent-core failures, or message loss.

**Probability**: Low (15%)  
**Impact**: Medium (7 - rollback required)  
**Risk Score**: 11 (Low Risk)

**Indicators**:
- IPC communication failures
- Extension crashes or freezes
- Agent-core crashes
- Message parsing errors in logs
- Integration tests failing

**Mitigation Strategy**:
1. **Comprehensive Testing**:
   - Test all existing message types with MessagePack
   - Create message compatibility test suite
   - Test with large messages (>1MB)
   - Test with edge cases (null, undefined, circular refs)

2. **Backward Compatibility**:
   - Implement JSON fallback mechanism
   - Detect MessagePack vs JSON by magic bytes
   - Support both formats simultaneously (transition period)
   - Graceful degradation on parse errors

3. **Staged Rollout**:
   - Implement MessagePack as opt-in flag first
   - Enable for development/testing
   - Enable for beta users
   - Enable for all users after validation

4. **Version Detection**:
   - Add protocol version to messages
   - Detect version mismatch and fall back
   - Warn user if versions incompatible

**Contingency Plan**:
- Keep JSON serialization as default
- Make MessagePack opt-in permanently
- Rollback to JSON if critical bugs found
- Implement message compatibility layer
- Document which message types work with MessagePack

**Owner**: Lead Engineer  
**Review Date**: End of Week 6, Day 5  
**Status**: 🟢 Monitoring

---

### Risk #6: Performance Tests Are Flaky in CI

**Risk ID**: EP6-R006  
**Category**: Process  
**Phase**: Phase 5 (Load Testing & Documentation)

**Description**:
Performance regression tests may be flaky in CI due to shared runners, inconsistent hardware, or background processes. This would slow down development as engineers repeatedly re-run tests or ignore failures.

**Probability**: Medium (35%)  
**Impact**: Medium (5 - slows development)  
**Risk Score**: 18 (Medium Risk)

**Indicators**:
- Performance tests fail intermittently
- Wide variance in test results (>20%)
- Tests fail more often on certain runners
- Engineers complain about flaky tests
- Tests are frequently re-run or skipped

**Mitigation Strategy**:
1. **Infrastructure**:
   - Use dedicated GitHub Actions runners if possible
   - Use consistent runner types (ubuntu-latest, specific size)
   - Isolate performance tests from other CI jobs
   - Run performance tests on schedule (nightly) instead of per-PR

2. **Test Design**:
   - Run tests multiple times and average results (3-5 runs)
   - Set reasonable thresholds (10-15% regression allowed)
   - Use relative measurements (vs baseline) not absolute
   - Warm up before measuring (discard first run)

3. **Statistical Analysis**:
   - Calculate standard deviation and confidence intervals
   - Fail only if regression is statistically significant
   - Track performance trends over time (not just point comparisons)

4. **Monitoring**:
   - Track test flakiness rate
   - Alert if flakiness >10%
   - Investigate and fix root causes

**Contingency Plan**:
- Run performance tests nightly instead of per-PR
- Require manual performance testing before major releases
- Use local benchmarking as source of truth
- Document expected variance and acceptable ranges
- Implement performance test quarantine (fail but don't block)

**Owner**: Lead Engineer  
**Review Date**: End of Week 7, Day 2  
**Status**: 🟡 Monitoring

---

### Risk #7: Optimization Breaks Backward Compatibility

**Risk ID**: EP6-R007  
**Category**: Technical  
**Phase**: All Phases

**Description**:
Performance optimizations may require API changes that break backward compatibility with existing clients (VSCode extension, MCP clients, CLI). This would require coordination and migration planning.

**Probability**: Low (10%)  
**Impact**: Low (3 - minor API changes)  
**Risk Score**: 3 (Low Risk)

**Indicators**:
- API signature changes required
- Database schema changes needed
- Configuration format changes
- Client integration tests failing

**Mitigation Strategy**:
1. **Design Principle**:
   - Maintain backward compatibility as core design goal
   - Version APIs if breaking changes needed (v2 endpoints)
   - Support old and new APIs simultaneously (transition period)

2. **Testing**:
   - Comprehensive integration tests with existing clients
   - Test with extension, MCP, and CLI
   - Test with old configuration formats
   - Test database migrations

3. **Documentation**:
   - Document all API changes clearly
   - Provide migration guide for breaking changes
   - Mark deprecated APIs and features
   - Communicate changes to users early

**Contingency Plan**:
- Support old API indefinitely if needed
- Provide migration tools for database/config changes
- Offer side-by-side deployment option
- Roll back breaking changes if migration is too complex
- Document migration path in detail

**Owner**: Lead Engineer  
**Review Date**: Ongoing (all phases)  
**Status**: 🟢 Monitoring

---

### Risk #8: Team Member Unavailability

**Risk ID**: EP6-R008  
**Category**: Resource  
**Phase**: All Phases

**Description**:
The primary engineer working on EP-6 may become unavailable due to illness, vacation, or other priorities. This would delay the project or require other team members to ramp up.

**Probability**: Low (15%)  
**Impact**: Medium (6 - project delay)  
**Risk Score**: 9 (Low Risk)

**Indicators**:
- Engineer reports illness or planned absence
- Engineer is pulled to urgent production issues
- Engineer appears overloaded with work
- Progress slows significantly

**Mitigation Strategy**:
1. **Knowledge Sharing**:
   - Document all work thoroughly and continuously
   - Regular progress updates to team (daily standups)
   - Code reviews involve multiple team members
   - Knowledge sharing sessions weekly

2. **Bus Factor Reduction**:
   - Pair programming for critical components
   - Cross-training on performance optimization
   - Multiple people understand profiling tools
   - Shared access to all resources and tools

3. **Planning**:
   - Build 1-2 week buffer into schedule
   - Identify critical path tasks early
   - Have backup engineer identified
   - Prepare handoff documentation

**Contingency Plan**:
- Extend timeline by 1-2 weeks if needed
- Bring in additional engineer (junior or senior)
- Reduce scope if necessary (cut medium priority items)
- Pause project temporarily if unavoidable

**Owner**: Tech Lead  
**Review Date**: Weekly (Monday standup)  
**Status**: 🟢 Monitoring

---

## Retired Risks

None yet. Risks will be moved here when they are resolved or no longer applicable.

---

## Risk Review Schedule

**Weekly Risk Review**: Every Monday during project standup
- Review all active risks
- Update status indicators
- Reassess probability and impact
- Update mitigation progress
- Escalate critical risks to leadership

**Phase Transition Review**: End of each phase
- Comprehensive review of all risks
- Close out phase-specific risks
- Identify new risks for next phase
- Update risk register

**Post-Project Review**: End of Week 7
- Analyze which risks materialized
- Evaluate effectiveness of mitigation strategies
- Document lessons learned
- Update organizational risk knowledge base

---

## Risk Escalation Path

**Low Risk**: Managed by Lead Engineer, reported in weekly standup

**Medium Risk**: 
- Lead Engineer manages with support from Tech Lead
- Reported in weekly standup
- Monthly report to project stakeholders

**High Risk**:
- Tech Lead manages with Lead Engineer
- Reported in daily standup
- Bi-weekly report to project stakeholders
- Mitigation plan reviewed by leadership

**Critical Risk**:
- Immediate escalation to Tech Lead and leadership
- Daily status updates required
- Mitigation plan approved by leadership
- Project timeline may be adjusted

---

## Risk Log

### 2025-11-11: Risk Register Created
- Initial risk assessment completed
- 8 risks identified and documented
- Mitigation strategies defined
- Review schedule established
- **Action**: Begin monitoring all risks

---

## Appendix: Risk Categories

**Technical Risks**: Related to technology, implementation, or performance
- Examples: Race conditions, scaling issues, bugs

**Resource Risks**: Related to people, time, or budget
- Examples: Team member unavailability, budget overruns

**Process Risks**: Related to development process or workflow
- Examples: Flaky tests, insufficient documentation

**External Risks**: Related to dependencies outside our control
- Examples: Library bugs, API changes, infrastructure issues

**Business Risks**: Related to business requirements or stakeholder expectations
- Examples: Changing priorities, scope creep

---

## Notes for Risk Owners

**Risk Monitoring Best Practices**:
1. Check indicators weekly (minimum)
2. Update status if indicators change
3. Document any changes in risk assessment
4. Communicate significant changes to team
5. Escalate if risk level increases

**Status Colors**:
- 🟢 **Green**: Risk is under control, monitoring continues
- 🟡 **Yellow**: Risk indicators are present, active mitigation in progress
- 🔴 **Red**: Risk has materialized or is imminent, immediate action required

**When to Update Risk Register**:
- New risk identified: Add immediately
- Risk status changes: Update within 24 hours
- Risk probability/impact changes: Update in next review
- Risk is resolved: Move to "Retired Risks" section
- Mitigation strategy changes: Update immediately

---

## Risk Register Change History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-11 | 1.0 | Initial risk register created | Project Lead |

