// Counting the database statements an action runs, so that an N+1 problem is a failing scenario.
//
// Create one counter when the project's System is built, call `record(sql)` from the data layer's query hook (a Prisma
// `$on('query')` listener, a Knex `query` event, a TypeORM logger, a `pg` client wrapper) and return `count` from
// System.queriesExecuted.
export class QueryCounter {
  /** Savepoints and transaction control are not counted: they say nothing about the data read. */
  static readonly IGNORED = /^\s*(savepoint|release savepoint|rollback to savepoint|begin|commit|rollback)\b/i;

  count = 0;

  record(statement: string): void {
    if (!QueryCounter.IGNORED.test(statement)) {
      this.count += 1;
    }
  }
}
