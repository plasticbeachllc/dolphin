# Agent Project Flow Management Guide

## Task Templates

### Task Template: Feature Implementation
**Goal**: [Clear one-sentence objective]
**Files Involved**: [Primary files that will be modified]
**Test Coverage**: [Expected test files to update]
**Success Criteria**: [Specific, measurable outcomes]
**Common Pitfalls**: [Known issues to avoid]

### Task Template: Bug Fix  
**Problem**: [Clear description]
**Root Cause**: [Technical analysis]
**Fix Approach**: [Step-by-step solution]
**Testing Strategy**: [How to verify the fix]
**Regression Prevention**: [How to ensure it doesn't reoccur]

### Task Template: Code Refactoring
**Current State**: [Description of current code structure]
**Target State**: [Desired improved structure]
**Refactoring Steps**: [Specific refactoring operations]
**Risk Assessment**: [Potential breaking changes]
**Validation Method**: [How to ensure functionality preserved]

### Task Template: Documentation Update
**Documentation Type**: [API docs, README, inline comments, etc.]
**Scope**: [Specific sections/pages to update]
**Audience**: [Target readers - developers, users, etc.]
**Review Required**: [Who should review these changes]

### Task Template: Performance Optimization
**Performance Issue**: [Specific bottleneck or metric]
**Current Metrics**: [Baseline measurements]
**Target Metrics**: [Desired improvement]
**Monitoring**: [How to track performance changes]

## Project Flow Instructions

### 1. Task Assessment
- Always analyze existing codebase before making changes
- Check for similar implementations or patterns
- Review recent git history for context
- Identify dependencies and potential conflicts

### 2. Implementation Guidelines
- Follow existing code style and patterns
- Write tests for new functionality
- Update documentation alongside code changes
- Consider backward compatibility

### 3. Quality Assurance
- Run existing tests before and after changes
- Perform code review on complex changes
- Validate against success criteria
- Check for edge cases and error conditions

### 4. Deployment Considerations
- Impact on existing functionality
- Database migrations (if applicable)
- Configuration changes required
- Rollback strategy

## Common Workflows

### New Feature Development
1. Analyze requirements and existing architecture
2. Create implementation plan using Feature Implementation template
3. Develop with incremental commits
4. Write comprehensive tests
5. Update documentation
6. Perform final validation

### Bug Resolution
1. Reproduce the issue
2. Root cause analysis using Bug Fix template
3. Implement and test fix
4. Add regression tests
5. Document the fix

### Code Review Process
1. Self-review against templates and guidelines
2. Ensure all success criteria are met
3. Verify test coverage
4. Check documentation updates
5. Submit for peer review if required

## Agent Best Practices

### File Management
- Always check current directory structure before creating files
- Use descriptive file names following project conventions
- Group related files in appropriate directories
- Update import paths when moving files

### Code Quality
- Write self-documenting code with clear variable names
- Keep functions focused and single-purpose
- Add comments for complex logic
- Follow the project's existing patterns

### Communication
- Provide clear progress updates
- Flag potential issues early
- Ask clarifying questions when requirements are unclear
- Document decisions and rationale

## Template Usage Notes

- Copy and modify templates as needed for specific tasks
- All fields should be completed before starting implementation
- Update templates based on project-specific requirements
- Use these templates to maintain consistency across tasks