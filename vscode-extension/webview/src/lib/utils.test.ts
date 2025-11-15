import { describe, expect, it } from "bun:test";

import { cn } from "./utils";

describe("cn", () => {
  it("combines arbitrary class values", () => {
    expect(cn("btn", "btn-primary", ["rounded"], { hidden: false, block: true })).toBe(
      "btn btn-primary rounded block",
    );
  });

  it("removes conflicting Tailwind utilities with last-one-wins semantics", () => {
    expect(cn("text-lg", "text-sm", "text-lg")).toBe("text-lg");
  });

  it("handles falsy inputs gracefully", () => {
    expect(cn("base", undefined, null, false && "hidden", "mt-2")).toBe("base mt-2");
  });
});
