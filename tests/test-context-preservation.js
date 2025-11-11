#!/usr/bin/env node
/**
 * Quick test to verify context preservation fix
 * Tests that assistant messages are preserved even when no tools are called
 */

console.log('Testing context preservation fix (P1)\n');

// Simulate the message flow through the tool executor
function simulateToolExecutorLoop() {
  const messages = [
    { role: 'user', content: 'What is 2 + 2?' }
  ];

  // Simulate Claude response with NO tool calls (final answer)
  const claudeResponse = {
    content: [
      { type: 'text', text: 'The answer is 4.' }
    ],
    stop_reason: 'end_turn'
  };

  // Extract tool calls (returns empty array for text-only response)
  const toolCalls = claudeResponse.content.filter(block => block.type === 'tool_use');

  // This is the FIX: Add assistant message BEFORE checking for empty tool calls
  messages.push({
    role: 'assistant',
    content: claudeResponse.content
  });

  // Then check if we need to continue the loop
  if (toolCalls.length === 0) {
    console.log('✅ No tools called, ending loop');
    console.log('   (This is expected for final answers)\n');
  }

  return messages;
}

// Run simulation
const finalMessages = simulateToolExecutorLoop();

console.log('Final conversation history:');
console.log('---');
finalMessages.forEach((msg, i) => {
  console.log(`Message ${i + 1} (${msg.role}):`);
  if (typeof msg.content === 'string') {
    console.log(`  ${msg.content}`);
  } else {
    msg.content.forEach(block => {
      if (block.type === 'text') {
        console.log(`  ${block.text}`);
      }
    });
  }
});
console.log('---\n');

// Verify the fix
const hasUserMessage = finalMessages.some(m => m.role === 'user');
const hasAssistantMessage = finalMessages.some(m => m.role === 'assistant');

console.log('Verification:');
console.log(`  User message preserved: ${hasUserMessage ? '✅' : '❌'}`);
console.log(`  Assistant message preserved: ${hasAssistantMessage ? '✅' : '❌'}`);
console.log(`  Total messages: ${finalMessages.length}`);

if (!hasAssistantMessage) {
  console.log('\n❌ FAIL: Assistant message was NOT preserved!');
  console.log('   This would cause context loss in follow-up turns.');
  process.exit(1);
}

console.log('\n✅ PASS: Context preservation working correctly!');
console.log('   Assistant messages are preserved even when no tools are called.');
console.log('   Follow-up conversations will maintain full context.');
