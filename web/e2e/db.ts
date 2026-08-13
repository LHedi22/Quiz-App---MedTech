import { Client } from "pg";

const DATABASE_URL =
  process.env.DATABASE_URL ?? "postgresql://postgres:postgres@127.0.0.1:54342/postgres";

/** Direct Postgres access for test setup only - mirrors backend/tests'
 * own `run_sql` pattern for seeding rows no API endpoint can create
 * (e.g. a `submissions` row with a known status, since only the real
 * OMR pipeline normally writes one). */
export async function runSql(sql: string, params: unknown[] = []): Promise<void> {
  await queryRows(sql, params);
}

export async function queryRows<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const client = new Client({ connectionString: DATABASE_URL });
  await client.connect();
  try {
    const result = await client.query(sql, params);
    return result.rows as T[];
  } finally {
    await client.end();
  }
}
