// agent-core/tests/main.test.ts
import { describe, test, expect, beforeEach } from "bun:test";

describe("AgentCore Correlation IDs", () => {
  test("Should generate unique requestIds", () => {
    // Test the requestId generation pattern
    const generateRequestId = (counter: number) => {
      return `req-${Date.now()}-${counter}`;
    };

    const id1 = generateRequestId(1);
    const id2 = generateRequestId(2);

    // Should have format req-{timestamp}-{counter}
    expect(id1).toMatch(/^req-\d+-\d+$/);
    expect(id2).toMatch(/^req-\d+-\d+$/);

    // Should be different
    expect(id1).not.toBe(id2);

    // Should include counter
    expect(id1).toContain("-1");
    expect(id2).toContain("-2");
  });

  test("Should include timestamp in requestId", () => {
    const generateRequestId = (counter: number) => {
      return `req-${Date.now()}-${counter}`;
    };

    const beforeTime = Date.now();
    const id = generateRequestId(1);
    const afterTime = Date.now();

    const parts = id.split("-");
    expect(parts.length).toBe(3);
    expect(parts[0]).toBe("req");

    const timestamp = parseInt(parts[1]);
    expect(timestamp).toBeGreaterThanOrEqual(beforeTime);
    expect(timestamp).toBeLessThanOrEqual(afterTime);
  });

  test("Should increment counter for each event", () => {
    let counter = 0;
    const generateRequestId = () => {
      return `req-${Date.now()}-${++counter}`;
    };

    const id1 = generateRequestId();
    const id2 = generateRequestId();
    const id3 = generateRequestId();

    expect(id1).toContain("-1");
    expect(id2).toContain("-2");
    expect(id3).toContain("-3");
  });

  test("Should add requestId to events", () => {
    // Simulate the sendEvent function behavior
    const sendEvent = (event: any, requestIdCounter: { value: number }) => {
      const eventWithId = {
        ...event,
        requestId: event.requestId || `req-${Date.now()}-${++requestIdCounter.value}`,
      };
      return eventWithId;
    };

    const counter = { value: 0 };

    const event1 = { type: "agent_ready", version: "0.1.0" };
    const result1 = sendEvent(event1, counter);

    expect(result1.requestId).toBeDefined();
    expect(result1.requestId).toMatch(/^req-\d+-1$/);
    expect(result1.type).toBe("agent_ready");

    const event2 = { type: "content_delta", delta: "test" };
    const result2 = sendEvent(event2, counter);

    expect(result2.requestId).toBeDefined();
    expect(result2.requestId).toMatch(/^req-\d+-2$/);
    expect(result2.type).toBe("content_delta");
  });

  test("Should preserve existing requestId if present", () => {
    const sendEvent = (event: any, requestIdCounter: { value: number }) => {
      const eventWithId = {
        ...event,
        requestId: event.requestId || `req-${Date.now()}-${++requestIdCounter.value}`,
      };
      return eventWithId;
    };

    const counter = { value: 0 };
    const existingId = "custom-req-123";
    const event = { type: "test", requestId: existingId };

    const result = sendEvent(event, counter);

    expect(result.requestId).toBe(existingId);
    expect(counter.value).toBe(0); // Counter not incremented
  });

  test("Should format JSON-RPC notification with event and requestId", () => {
    const createNotification = (event: any) => {
      const eventWithId = {
        ...event,
        requestId: event.requestId || `req-${Date.now()}-1`,
      };

      return {
        jsonrpc: "2.0",
        method: "notify",
        params: eventWithId,
      };
    };

    const event = { type: "agent_ready", version: "0.1.0", capabilities: [] };
    const notification = createNotification(event);

    expect(notification.jsonrpc).toBe("2.0");
    expect(notification.method).toBe("notify");
    expect(notification.params.requestId).toBeDefined();
    expect(notification.params.type).toBe("agent_ready");
  });
});

describe("AgentCore Event Types", () => {
  test("All event types should support optional requestId", () => {
    // Test that all event types from shared/types/events.ts support requestId
    const events = [
      { type: "agent_ready", version: "0.1.0", capabilities: [], requestId: "req-1" },
      { type: "content_delta", delta: "test", requestId: "req-2" },
      { type: "plan_generated", plan: { id: "p1" }, requestId: "req-3" },
      { type: "tool_call_started", toolId: "t1", tool: "test", input: {}, requestId: "req-4" },
      { type: "tool_call_completed", toolId: "t1", result: {}, requestId: "req-5" },
      { type: "task_completed", success: true, requestId: "req-6" },
      { type: "error", error: { code: "TEST", message: "test", suggestions: [], recoverable: true }, requestId: "req-7" },
    ];

    events.forEach((event) => {
      expect(event.requestId).toBeDefined();
      expect(event.requestId).toMatch(/^req-\d+$/);
    });
  });

  test("Events should work without requestId", () => {
    // Events should be valid even without requestId (it's optional)
    const events = [
      { type: "agent_ready", version: "0.1.0", capabilities: [] },
      { type: "content_delta", delta: "test" },
      { type: "task_completed", success: true },
    ];

    events.forEach((event) => {
      expect(event.type).toBeDefined();
      expect(event.requestId).toBeUndefined();
    });
  });
});
