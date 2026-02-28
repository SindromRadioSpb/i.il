import { describe, expect, it } from 'vitest';
import { RunBudget } from '../src/cron/budget';

describe('RunBudget', () => {
  it('hasTime() returns true when budget has headroom', () => {
    const budget = new RunBudget(25_000); // 25s budget, just started
    expect(budget.hasTime(2_000)).toBe(true);
  });

  it('hasTime() returns false when budget is exhausted', () => {
    // Simulate a budget that started 30s ago with a 25s limit
    const startMs = Date.now() - 30_000;
    const budget = new RunBudget(25_000, startMs);
    expect(budget.hasTime(2_000)).toBe(false);
  });

  it('hasTime() returns false when remaining time < reserveMs', () => {
    // 3s remaining, but we require 5s reserve
    const startMs = Date.now() - 22_000;
    const budget = new RunBudget(25_000, startMs);
    expect(budget.hasTime(5_000)).toBe(false);
  });

  it('remainingMs() returns a positive value when budget is fresh', () => {
    const budget = new RunBudget(25_000);
    expect(budget.remainingMs()).toBeGreaterThan(20_000);
  });

  it('remainingMs() returns 0 when budget is exhausted', () => {
    const startMs = Date.now() - 30_000;
    const budget = new RunBudget(25_000, startMs);
    expect(budget.remainingMs()).toBe(0);
  });

  it('signal() returns an AbortSignal', () => {
    const budget = new RunBudget(25_000);
    const signal = budget.signal();
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
  });

  it('signal() returns an AbortSignal with near-zero timeout when budget is exhausted', () => {
    const startMs = Date.now() - 30_000;
    const budget = new RunBudget(25_000, startMs);
    // remainingMs() is 0, so AbortSignal.timeout(0) is created — signal exists even if not yet fired
    const signal = budget.signal();
    expect(signal).toBeInstanceOf(AbortSignal);
    // remainingMs() must be 0 when budget is past
    expect(budget.remainingMs()).toBe(0);
  });
});
