/**
 * RunBudget — wall-clock time budget for cron runs.
 *
 * Cloudflare Workers cron triggers have a ~30s wall-clock limit on paid plans.
 * We use a 25s budget by default to leave 5s for finishRun() and releaseLock().
 */
export class RunBudget {
  private readonly startMs: number;

  constructor(
    private readonly maxMs: number,
    startMs?: number,
  ) {
    this.startMs = startMs ?? Date.now();
  }

  /** Milliseconds remaining before budget is exhausted. */
  remainingMs(): number {
    return Math.max(0, this.maxMs - (Date.now() - this.startMs));
  }

  /**
   * Returns true if at least `reserveMs` milliseconds remain.
   * Use `reserveMs` to guarantee the upcoming operation has enough headroom.
   */
  hasTime(reserveMs = 2_000): boolean {
    return this.remainingMs() > reserveMs;
  }

  /**
   * AbortSignal that fires when the budget expires.
   * Useful for passing directly to fetch() or other async operations.
   */
  signal(): AbortSignal {
    return AbortSignal.timeout(this.remainingMs());
  }
}
