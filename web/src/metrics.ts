import type { Observation } from "./types";

export function summarize(rows: Observation[], metric: string) {
  const data = rows.filter((r) => r.metric === metric);
  const ratios = data.filter(
    (r) => r.numerator !== null && r.denominator !== null,
  );
  const denominator = ratios.reduce((s, r) => s + r.denominator!, 0);
  return {
    n: data.length,
    value: denominator
      ? ratios.reduce((s, r) => s + r.numerator!, 0) / denominator
      : null,
  };
}

export function percentile(values: number[], p: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)];
}
