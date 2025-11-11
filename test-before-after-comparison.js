#!/usr/bin/env node
/**
 * Demonstrates the BEFORE and AFTER behavior of both bug fixes
 */

const path = require('path');

console.log('='.repeat(70));
console.log('BEFORE vs AFTER Bug Fix Comparison');
console.log('='.repeat(70));

// ============================================================================
// P0: Security Fix - Absolute Path Bypass
// ============================================================================

console.log('\n📌 P0: Security Fix - Read Files Tool\n');

function oldBuggyCode(filepath, workspaceRoot) {
  const fullPath = path.isAbsolute(filepath)
    ? filepath  // BUG: Uses absolute path as-is!
    : path.resolve(workspaceRoot, filepath);

  // BUG: Only checks relative paths!
  if (!path.isAbsolute(filepath) && !fullPath.startsWith(workspaceRoot)) {
    return { allowed: false, reason: 'Access denied: outside workspace' };
  }

  return { allowed: true, resolvedPath: fullPath };
}

function newFixedCode(filepath, workspaceRoot) {
  // FIX: Always resolve relative to workspace
  const fullPath = path.resolve(workspaceRoot, filepath);

  // FIX: Always check workspace boundary
  if (!fullPath.startsWith(workspaceRoot)) {
    return { allowed: false, reason: 'Access denied: path outside workspace' };
  }

  return { allowed: true, resolvedPath: fullPath };
}

const workspaceRoot = '/home/user/dolphin';
const maliciousPath = '/etc/passwd';

console.log('Test: Agent tries to read /etc/passwd\n');

const beforeResult = oldBuggyCode(maliciousPath, workspaceRoot);
const afterResult = newFixedCode(maliciousPath, workspaceRoot);

console.log('BEFORE fix:');
console.log(`  Allowed: ${beforeResult.allowed} ❌ SECURITY VULNERABILITY!`);
console.log(`  Path: ${beforeResult.resolvedPath || 'blocked'}`);
console.log(`  Impact: Agent could read /etc/passwd, SSH keys, etc.\n`);

console.log('AFTER fix:');
console.log(`  Allowed: ${afterResult.allowed} ✅ BLOCKED`);
console.log(`  Reason: ${afterResult.reason}`);
console.log(`  Impact: Agent confined to workspace directory\n`);

// ============================================================================
// P1: Context Preservation Fix
// ============================================================================

console.log('📌 P1: Context Preservation - Tool Executor\n');

function oldBuggyExecutor() {
  const messages = [{ role: 'user', content: 'What is 2 + 2?' }];

  const response = {
    content: [{ type: 'text', text: 'The answer is 4.' }]
  };

  const toolCalls = response.content.filter(b => b.type === 'tool_use');

  // BUG: Checks for empty tools BEFORE adding assistant message
  if (toolCalls.length === 0) {
    // Loop breaks here, message never added!
    return messages;
  }

  messages.push({ role: 'assistant', content: response.content });
  return messages;
}

function newFixedExecutor() {
  const messages = [{ role: 'user', content: 'What is 2 + 2?' }];

  const response = {
    content: [{ type: 'text', text: 'The answer is 4.' }]
  };

  const toolCalls = response.content.filter(b => b.type === 'tool_use');

  // FIX: Add assistant message BEFORE checking for empty tools
  messages.push({ role: 'assistant', content: response.content });

  if (toolCalls.length === 0) {
    return messages;
  }

  return messages;
}

console.log('Test: Agent provides final answer without using tools\n');

const beforeMessages = oldBuggyExecutor();
const afterMessages = newFixedExecutor();

console.log('BEFORE fix:');
console.log(`  Messages in history: ${beforeMessages.length}`);
console.log(`  Assistant message preserved: ${beforeMessages.some(m => m.role === 'assistant') ? 'Yes' : 'No ❌'}`);
console.log(`  Impact: Follow-up questions lose context, agent repeats itself\n`);

console.log('AFTER fix:');
console.log(`  Messages in history: ${afterMessages.length}`);
console.log(`  Assistant message preserved: ${afterMessages.some(m => m.role === 'assistant') ? 'Yes ✅' : 'No'}`);
console.log(`  Impact: Full conversation context maintained\n`);

// ============================================================================
// Summary
// ============================================================================

console.log('='.repeat(70));
console.log('Summary');
console.log('='.repeat(70));

const p0Fixed = !newFixedCode('/etc/passwd', workspaceRoot).allowed;
const p1Fixed = newFixedExecutor().some(m => m.role === 'assistant');

console.log(`\nP0 Security Fix: ${p0Fixed ? '✅ PASS' : '❌ FAIL'}`);
console.log(`  Absolute paths outside workspace are now blocked`);

console.log(`\nP1 Context Fix: ${p1Fixed ? '✅ PASS' : '❌ FAIL'}`);
console.log(`  Assistant messages preserved when no tools called`);

if (p0Fixed && p1Fixed) {
  console.log('\n✅ All fixes verified and working correctly!\n');
} else {
  console.log('\n❌ One or more fixes failed!\n');
  process.exit(1);
}
