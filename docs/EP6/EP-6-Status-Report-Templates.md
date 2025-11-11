# EP-6: Status Report Templates

This document provides templates for daily standups and weekly status reports.

---

## Daily Standup Template

**Date**: [YYYY-MM-DD]  
**Attendees**: [Names]  
**Duration**: 15 minutes

### Team Member: [Name]

**Yesterday**:
- Completed: [Specific tasks completed]
- Progress: [% completion on current story]
- Key Accomplishments: [Notable achievements]

**Today**:
- Plan: [Specific tasks planned]
- Focus: [Current story/task]
- Expected Outcome: [What will be completed today]

**Blockers**:
- [Blocker 1]: [Description and help needed]
- [Blocker 2]: [Description and help needed]

**Risks**:
- [Any new risks identified]
- [Status of existing risks]

---

## Weekly Status Report Template

**Week**: [Week # of Project] (Date Range: [Start] - [End])  
**Phase**: [Current Phase Name]  
**Overall Status**: 🟢 On Track / 🟡 At Risk / 🔴 Off Track  
**Report Date**: [YYYY-MM-DD]

---

### Executive Summary

**Current Week Highlights**:
- [Key accomplishment 1]
- [Key accomplishment 2]
- [Key accomplishment 3]

**Next Week Focus**:
- [Priority 1]
- [Priority 2]
- [Priority 3]

**Status Summary**:
- **Schedule**: [On Track / 1 week behind / etc.]
- **Scope**: [No changes / Minor adjustments / etc.]
- **Quality**: [Meeting standards / Issues identified / etc.]
- **Team Morale**: [High / Medium / Low]

---

### Progress This Week

#### Completed Stories
| Story ID | Story Title | Points | Notes |
|----------|-------------|--------|-------|
| 1.1 | [Story title] | 5 | [Brief notes] |
| 1.2 | [Story title] | 8 | [Brief notes] |

**Total Points Completed**: [X] points

#### In Progress Stories
| Story ID | Story Title | Points | % Complete | Expected Completion |
|----------|-------------|--------|------------|---------------------|
| 1.3 | [Story title] | 3 | 60% | [Date] |

#### Blocked Stories
| Story ID | Story Title | Blocker | Impact | Action Plan |
|----------|-------------|---------|--------|-------------|
| 2.1 | [Story title] | [Blocker description] | High | [Action] |

---

### Metrics

#### Performance Metrics (if applicable)
| Metric | Baseline | Target | Current | Status |
|--------|----------|--------|---------|--------|
| Indexing Throughput | 500 files/min | 2,500 files/min | [X] files/min | 🟡 |
| Search Latency (p50) | 300ms | 150ms | [X]ms | 🟢 |
| Cache Hit Rate | 0% | 70% | [X]% | 🟢 |

#### Project Health Metrics
| Metric | Value | Status |
|--------|-------|--------|
| Stories Completed | [X]/[Total] | 🟢 |
| Story Points Burned | [X]/[Total] | 🟢 |
| Velocity (pts/week) | [X] | 🟢 |
| Open Blockers | [X] | 🟡 |
| Risk Level | [Low/Med/High] | 🟢 |

#### Code Quality Metrics
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Test Coverage | [X]% | 80% | 🟢 |
| Tests Passing | [X]/[Total] | 100% | 🟡 |
| Code Review Status | [X pending] | 0 | 🟢 |

---

### Risks & Issues

#### New Risks Identified
| Risk ID | Description | Probability | Impact | Mitigation |
|---------|-------------|-------------|--------|------------|
| [ID] | [Description] | [%] | [1-10] | [Plan] |

#### Active Risks Status Update
| Risk ID | Description | Status | Change | Next Action |
|---------|-------------|--------|--------|-------------|
| EP6-R001 | Race conditions | 🟡 Monitoring | No change | Continue testing |
| EP6-R003 | Cache invalidation | 🟡 Monitoring | No change | Implement tests |

#### Issues Resolved
| Issue | Resolution | Impact |
|-------|------------|--------|
| [Issue description] | [How resolved] | [Lessons learned] |

---

### Key Decisions Made

| Decision | Rationale | Impact | Date |
|----------|-----------|--------|------|
| [Decision 1] | [Why made] | [Effect on project] | [YYYY-MM-DD] |
| [Decision 2] | [Why made] | [Effect on project] | [YYYY-MM-DD] |

---

### Blockers Needing Escalation

| Blocker | Story Impacted | Days Blocked | Help Needed From | Urgency |
|---------|----------------|--------------|------------------|---------|
| [Description] | [Story ID] | [X days] | [Role/Person] | 🔴 High |

---

### Next Week Plan

#### Stories Planned
| Story ID | Story Title | Points | Assignee | Priority |
|----------|-------------|--------|----------|----------|
| [ID] | [Title] | [X] | [Name] | High |
| [ID] | [Title] | [X] | [Name] | Medium |

**Estimated Points**: [X] points  
**Capacity**: [Y] points  
**Utilization**: [X/Y * 100]%

#### Key Milestones
- [ ] [Milestone 1] - [Date]
- [ ] [Milestone 2] - [Date]

#### Dependencies
- Waiting on: [External dependency description]
- Blocking: [What is blocked by our work]

---

### Team Updates

**Team Capacity**:
- Available: [X person-days]
- Planned PTO: [Y person-days]
- Other commitments: [Z person-days]
- **Effective Capacity**: [X-Y-Z person-days]

**Team Morale & Concerns**:
- [Any concerns about workload, morale, or team dynamics]
- [Positive feedback or wins to celebrate]

---

### Attachments & References

- **Flame Graphs**: [Link to profiling results]
- **Performance Reports**: [Link to benchmark results]
- **Code Reviews**: [Link to pending reviews]
- **Documentation Updates**: [Link to updated docs]

---

## Sample Daily Standup (Filled Out)

**Date**: 2025-11-18 (Monday of Week 2)  
**Attendees**: Lead Engineer, Tech Lead  
**Duration**: 15 minutes

### Team Member: Lead Engineer

**Yesterday**:
- Completed: Parallel scanner implementation (Story 2.1)
- Progress: 90% completion on parallel scanner
- Key Accomplishments: Achieved 8x speedup on 10K file test repo

**Today**:
- Plan: Write unit tests for parallel scanner, start integration testing
- Focus: Story 2.1 (Parallel File Scanning) - final testing
- Expected Outcome: Story 2.1 completed and merged

**Blockers**:
- None currently

**Risks**:
- Noticed intermittent test failures with 16 workers (potential race condition)
- Investigating today, may need to limit workers to 8 for stability

---

## Sample Weekly Status Report (Filled Out)

**Week**: Week 2 of 7 (2025-11-18 to 2025-11-22)  
**Phase**: Phase 2 - Indexing Optimization  
**Overall Status**: 🟢 On Track  
**Report Date**: 2025-11-22

---

### Executive Summary

**Current Week Highlights**:
- Completed parallel file scanning with 8x speedup on test repos
- Implemented parallel tree-sitter parsing with controlled memory usage
- Started incremental embedding implementation
- Identified and mitigated race condition risk early

**Next Week Focus**:
- Complete incremental embedding (Story 2.3)
- Implement adaptive batch sizing (Story 2.4)
- Begin tree-sitter AST caching (Story 2.5)

**Status Summary**:
- **Schedule**: On Track (ahead by 1 day)
- **Scope**: No changes
- **Quality**: Meeting standards (test coverage 85%)
- **Team Morale**: High

---

### Progress This Week

#### Completed Stories
| Story ID | Story Title | Points | Notes |
|----------|-------------|--------|-------|
| 2.1 | Implement Parallel File Scanning | 8 | Achieved 8x speedup, all tests passing |
| 2.2 | Implement Parallel Tree-Sitter Parsing | 8 | Memory usage <3GB, integration complete |

**Total Points Completed**: 16 points

#### In Progress Stories
| Story ID | Story Title | Points | % Complete | Expected Completion |
|----------|-------------|--------|------------|---------------------|
| 2.3 | Implement Incremental Embedding | 5 | 30% | Mon, Nov 25 |

#### Blocked Stories
None

---

### Metrics

#### Performance Metrics
| Metric | Baseline | Target | Current | Status |
|--------|----------|--------|---------|--------|
| Indexing Throughput | 500 files/min | 2,500 files/min | 4,000 files/min | 🟢 Exceeds |
| Parse Time Reduction | 0% | 40% | 45% | 🟢 Exceeds |
| Memory Usage | 2GB | <4GB | 3GB | 🟢 |

#### Project Health Metrics
| Metric | Value | Status |
|--------|-------|--------|
| Stories Completed | 4/24 | 🟢 |
| Story Points Burned | 21/133 | 🟢 |
| Velocity (pts/week) | 16 pts/week | 🟢 (Target: 15) |
| Open Blockers | 0 | 🟢 |
| Risk Level | Medium | 🟢 |

#### Code Quality Metrics
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Test Coverage | 85% | 80% | 🟢 |
| Tests Passing | 48/48 | 100% | 🟢 |
| Code Review Status | 0 pending | 0 | 🟢 |

---

### Risks & Issues

#### New Risks Identified
| Risk ID | Description | Probability | Impact | Mitigation |
|---------|-------------|-------------|--------|------------|
| EP6-R009 | Memory usage spikes with 50K files | 15% | Medium (6) | Add memory monitoring, limit workers if needed |

#### Active Risks Status Update
| Risk ID | Description | Status | Change | Next Action |
|---------|-------------|--------|--------|-------------|
| EP6-R001 | Race conditions | 🟢 Resolved | Improved | Race condition found and fixed, extensive testing added |
| EP6-R002 | LanceDB scaling | 🟢 Monitoring | No change | Will test with 100K files in Week 3 |

#### Issues Resolved
| Issue | Resolution | Impact |
|-------|------------|--------|
| Intermittent test failures with 16 workers | Limited workers to 8, added file-level locking | Improved stability, slight throughput reduction (acceptable) |

---

### Key Decisions Made

| Decision | Rationale | Impact | Date |
|----------|-----------|--------|------|
| Limit parallel workers to 8 | Race conditions with 16 workers, 8 provides good balance of speed and stability | Still achieve 5x target, more stable | 2025-11-20 |
| Use pickle for AST caching | Faster than JSON, Python-native, acceptable for local cache | Simpler implementation | 2025-11-21 |

---

### Blockers Needing Escalation

None currently.

---

### Next Week Plan

#### Stories Planned
| Story ID | Story Title | Points | Assignee | Priority |
|----------|-------------|--------|----------|----------|
| 2.3 | Implement Incremental Embedding | 5 | Lead Engineer | High |
| 2.4 | Implement Adaptive Batch Sizing | 5 | Lead Engineer | Medium |
| 2.5 | Implement Tree-Sitter AST Caching | 5 | Lead Engineer | Medium |
| 2.6 | Indexing Integration Testing | 5 | Lead Engineer | High |

**Estimated Points**: 20 points  
**Capacity**: 20 points (5 days × 4 points/day)  
**Utilization**: 100%

#### Key Milestones
- [x] M2: Indexing Optimized (End of Week 3) - On track
- [ ] Phase 3 Start (End of Week 3) - On track

#### Dependencies
None

---

### Team Updates

**Team Capacity**:
- Available: 5 person-days
- Planned PTO: 0 person-days
- Other commitments: 0 person-days
- **Effective Capacity**: 5 person-days (100%)

**Team Morale & Concerns**:
- Team is energized by early wins (exceeding throughput targets)
- No concerns about workload or scope
- Good collaboration between engineer and tech lead on risk mitigation

---

### Attachments & References

- **Flame Graphs**: [Link to indexing flame graphs]
- **Performance Reports**: [Link to Week 2 benchmark results]
- **Code Reviews**: All reviews completed and merged
- **Documentation Updates**: Updated indexing optimization guide with parallel processing section

---

## Status Report Best Practices

### For Daily Standups:
1. **Be specific**: "Completed parallel scanner" not "Made progress"
2. **Quantify**: "90% complete" not "Almost done"
3. **Identify blockers early**: Don't wait until you're stuck
4. **Be concise**: 2-3 minutes per person maximum
5. **Focus on tasks, not activities**: "Wrote tests" not "Worked on testing"

### For Weekly Reports:
1. **Use metrics to tell the story**: Numbers are more convincing than words
2. **Highlight wins**: Celebrate progress and achievements
3. **Be honest about challenges**: Don't hide problems
4. **Provide context**: Explain why decisions were made
5. **Look forward**: Always include next week's plan
6. **Use visual indicators**: 🟢🟡🔴 make status immediately clear
7. **Include enough detail**: Report should stand alone without explanation
8. **Update risks proactively**: Don't wait for risks to become issues

### For Stakeholder Communication:
1. **Lead with status**: Start with 🟢🟡🔴 and executive summary
2. **Use tables and bullets**: Make information scannable
3. **Explain variances**: If behind schedule, explain why and recovery plan
4. **Escalate early**: If you need help, ask before it's critical
5. **Link to detailed info**: Don't include everything, link to attachments
6. **Be consistent**: Use same format every week for comparability

---

## Report Frequency & Distribution

### Daily Standup:
- **When**: Every weekday at 10:00 AM
- **Duration**: 15 minutes maximum
- **Attendees**: Core team (Lead Engineer, Tech Lead)
- **Format**: Verbal + notes in Slack/Teams
- **Skip when**: No progress or all team members unavailable

### Weekly Status Report:
- **When**: Friday end of day
- **Distribution**: Team lead → Tech lead → Stakeholders
- **Format**: This template, filled out in Markdown or Google Doc
- **Audience**: 
  - Full report: Internal team
  - Executive summary: Stakeholders, management
- **Archive**: All reports saved in project repository (`docs/status-reports/`)

### Phase Completion Report:
- **When**: End of each phase (Weeks 1, 3, 5, 6, 7)
- **Distribution**: Entire team + stakeholders
- **Format**: Comprehensive report with metrics, learnings, next phase plan
- **Include**: 
  - Phase objectives vs actual outcomes
  - Performance metrics
  - Lessons learned
  - Recommendations for next phase

### Ad-Hoc Updates:
- **When**: Critical issues, major blockers, significant changes
- **Distribution**: Immediate notification to Tech Lead
- **Format**: Slack message + follow-up meeting if needed
- **Examples**: Production bug, resource unavailability, scope change request

---

## Change History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-11 | 1.0 | Initial templates created | Project Lead |

