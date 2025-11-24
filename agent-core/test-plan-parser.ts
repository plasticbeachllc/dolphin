/**
 * Simple test script for the plan parser
 * Run with: npx tsx test-plan-parser.ts
 */

import { parsePlanFromMarkdown, parseLegacyMarkdownPlan } from "./src/workflows/plan-parser.js";

// Test 1: TOML in fenced block
const test1 = `
# Implementation Plan

Here's the plan for implementing the feature:

\`\`\`toml
plan_version = 1

overview = """
This plan implements user authentication using JWT tokens.
We'll add middleware for token validation and secure routes.
"""

complexity = "medium"
estimated_tokens = 3000

files_to_modify = [
  "src/server.ts",
  "src/middleware/auth.ts"
]

files_to_create = [
  "src/utils/jwt.ts",
  "tests/auth.test.ts"
]

[[steps]]
id = 1
description = "Create JWT utility functions for token generation and validation"
files = ["src/utils/jwt.ts"]
estimated_tokens = 500

[[steps]]
id = 2
description = "Implement authentication middleware"
files = ["src/middleware/auth.ts"]
estimated_tokens = 800

[[steps]]
id = 3
description = "Update server routes to use auth middleware"
files = ["src/server.ts"]
estimated_tokens = 400

[[risks]]
description = "Token expiration handling may require additional testing"
mitigation = "Add comprehensive unit tests for expiration edge cases"

dependencies = ["jsonwebtoken", "bcrypt"]
generated_at = "2025-01-15T10:30:00Z"
\`\`\`

The plan is structured to implement authentication incrementally.
`;

// Test 2: Unlabeled fence with TOML
const test2 = `
# Plan

\`\`\`
plan_version = 1
overview = "Simple refactoring task"
complexity = "low"
files_to_modify = ["src/utils.ts"]
\`\`\`
`;

// Test 3: Legacy markdown format (fallback)
const test3 = `
# Implementation Plan

## Overview
Refactor the authentication system for better maintainability.

## Files to Modify
- \`src/auth.ts\`
- \`src/middleware/auth.ts\`

## Files to Create
- \`tests/auth.test.ts\`

## Implementation Steps
1. Extract token validation logic into separate function
2. Add unit tests for validation logic
3. Update middleware to use new validation function

Complexity: medium
`;

// Test 4: TOML with common LLM mistakes (smart quotes, trailing commas)
const test4 = `
\`\`\`toml
plan_version = 1
overview = "Test with "smart quotes" and mistakes"
complexity = "high"
files_to_modify = [
  "file1.ts",
  "file2.ts",
]
\`\`\`
`;

console.log("Testing Plan Parser\n");
console.log("=".repeat(60));

// Run tests
const tests = [
  { name: "Fenced TOML", content: test1 },
  { name: "Unlabeled TOML", content: test2 },
  { name: "Legacy Markdown", content: test3 },
  { name: "TOML with mistakes", content: test4 },
];

for (const test of tests) {
  console.log(`\n${test.name}:`);
  try {
    const result = parsePlanFromMarkdown(test.content);
    console.log(`✓ Parsed successfully from ${result.source}`);
    console.log(`  Overview: ${result.plan.overview?.substring(0, 50)}...`);
    console.log(`  Complexity: ${result.plan.complexity}`);
    console.log(`  Files to modify: ${result.plan.files_to_modify.length}`);
    console.log(`  Steps: ${result.plan.steps.length}`);
  } catch (error) {
    // Try legacy parser
    try {
      const result = parseLegacyMarkdownPlan(test.content);
      console.log("✓ Parsed with legacy parser (fallback)");
      console.log(`  Overview: ${result.overview?.substring(0, 50)}...`);
      console.log(`  Complexity: ${result.complexity}`);
      console.log(`  Files to modify: ${result.files_to_modify?.length || 0}`);
      console.log(`  Steps: ${result.steps?.length || 0}`);
    } catch {
      console.log(`✗ Failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

console.log("\n" + "=".repeat(60));
console.log("Tests complete!\n");
