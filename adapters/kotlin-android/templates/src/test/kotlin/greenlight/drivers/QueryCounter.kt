package greenlight.drivers

import java.util.concurrent.atomic.AtomicInteger

/**
 * Counting the database statements an action runs, so that an N+1 problem is a failing scenario.
 *
 * Attach the counter to the database the code under test uses, once, when the test database is built. With Room:
 *
 * ```
 * QueryCounter.shared.attach()
 * Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
 *     .setQueryCallback({ sql, _ -> QueryCounter.shared.record(sql) }, Runnable::run)
 *     .build()
 * ```
 *
 * Any other data layer reports its statements the same way. Savepoints and transaction control are not counted: they say
 * nothing about the data read.
 */
class QueryCounter {
    private val total = AtomicInteger()

    @Volatile
    var attached: Boolean = false
        private set

    val count: Int get() = total.get()

    fun attach() {
        attached = true
    }

    fun record(statement: String?) {
        val head = statement.orEmpty().trimStart().uppercase()
        if (IGNORED.none { head.startsWith(it) }) total.incrementAndGet()
    }

    companion object {
        val shared = QueryCounter()
        private val IGNORED = listOf("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT", "BEGIN", "COMMIT", "ROLLBACK", "SET ", "PRAGMA")
    }
}
