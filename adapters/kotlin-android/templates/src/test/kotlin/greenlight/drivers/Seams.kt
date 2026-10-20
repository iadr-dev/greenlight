package greenlight.drivers

/**
 * The seams into the system under test. [ProjectSeams] (the one file of drivers that is specific to the project)
 * overrides what the project has.
 *
 * Every method says what it does and raises [ExpectedMissing] until the project implements the seam: during the red
 * phase that is the right failure. Use the most realistic seam available: the use case or view model first, then the
 * repository, then the raw database.
 */
open class Seams(protected val world: World) {
    // -- Given ------------------------------------------------------------------------------------------------
    /** Create [rows] of [entity]. An unknown column is an error. */
    open fun seed(entity: String, rows: List<Map<String, Any?>>): Unit = throw ExpectedMissing("a way to create $entity records")

    /** Sign [actor] in with [role] and return whatever proves it (a token, a session id). */
    open fun authenticate(actor: String, role: String): Map<String, String> = throw ExpectedMissing("a way to sign in as $role")

    open fun setFlag(flag: String, enabled: Boolean): Unit = throw ExpectedMissing("the $flag feature flag")

    // -- When -------------------------------------------------------------------------------------------------
    open fun deliverEvent(event: String, payload: Any?): Unit = throw ExpectedMissing("a way to deliver the $event event")

    open fun runJob(job: String): Unit = throw ExpectedMissing("the $job job")

    // -- Then -------------------------------------------------------------------------------------------------
    /** Every stored [entity] record, read through a seam that does not change anything. */
    open fun records(entity: String): List<Map<String, Any?>> = throw ExpectedMissing("a way to read $entity records")

    /**
     * How many database statements have run so far, counted by the shared [QueryCounter]. Without a database attached
     * there is nothing to count, which is an expected failure. Only scenarios that check a query count need this seam.
     */
    open fun queriesExecuted(): Int {
        val counter = QueryCounter.shared
        if (!counter.attached) throw ExpectedMissing("a database whose statements can be counted")
        return counter.count
    }

    /** The payloads of [event] that the code under test published (a test double of the bus). */
    open fun published(event: String): List<Any?> = throw ExpectedMissing("a captured $event event")

    /** Called after every scenario: drop data, close databases. */
    open fun reset() {
        // nothing to clean by default
    }
}
