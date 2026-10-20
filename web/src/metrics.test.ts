import { describe, expect, it } from "vitest";
import { percentile, summarize } from "./metrics";
import type { Observation } from "./types";

describe("metric denominators", () => {
  it("keeps missing data distinct from zero", () => {
    expect(summarize([], "plan_valid")).toEqual({ n: 0, value: null });
    expect(percentile([], 0.95)).toBeNull();
  });
  it("uses a pooled denominator instead of averaging percentages", () => {
    const rows = [
      { metric: "x", numerator: 1, denominator: 1 },
      { metric: "x", numerator: 0, denominator: 9 },
    ] as Observation[];
    expect(summarize(rows, "x")).toEqual({ n: 2, value: 0.1 });
  });
  it("uses nearest rank and leaves the input unchanged", () => {
    const values = [10, 2, 1];
    expect(percentile(values, 0.5)).toBe(2);
    expect(percentile(values, 0.95)).toBe(10);
    expect(values).toEqual([10, 2, 1]);
  });
});
