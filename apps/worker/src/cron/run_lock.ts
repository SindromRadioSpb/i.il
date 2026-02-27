const LOCK_NAME = 'cron';

/**
 * Attempt to acquire the named cron lease lock.
 *
 * Strategy (two-step batch, atomic from D1's perspective per connection):
 * 1. DELETE expired lock (lease_until < now)
 * 2. INSERT OR IGNORE new lock row
 *
 * Returns true if the lock was acquired (insert succeeded), false if
 * another run still holds a valid lease.
 */
export async function acquireLock(
  db: D1Database,
  runId: string,
  ttlSec: number,
): Promise<boolean> {
  const now = new Date().toISOString();
  const leaseUntil = new Date(Date.now() + ttlSec * 1000).toISOString();

  const [, insertResult] = await db.batch([
    db
      .prepare(`DELETE FROM run_lock WHERE lock_name = ? AND lease_until < ?`)
      .bind(LOCK_NAME, now),
    db
      .prepare(
        `INSERT OR IGNORE INTO run_lock (lock_name, lease_owner, lease_until)
         VALUES (?, ?, ?)`,
      )
      .bind(LOCK_NAME, runId, leaseUntil),
  ]);

  return (insertResult?.meta?.changes ?? 0) > 0;
}

/**
 * Release the lock held by runId.
 * No-op if the lock has already expired or been taken by another run.
 */
export async function releaseLock(db: D1Database, runId: string): Promise<void> {
  await db
    .prepare(`DELETE FROM run_lock WHERE lock_name = ? AND lease_owner = ?`)
    .bind(LOCK_NAME, runId)
    .run();
}
