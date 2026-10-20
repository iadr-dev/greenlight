package greenlight.drivers

/**
 * Everything one scenario knows. A fresh World is made for every scenario (the Cucumber PicoContainer builds one per
 * scenario and hands it to the step classes), so nothing leaks between them.
 */
class World {
    /** What the last action did: a library call returned [body] or raised [exception]. */
    class Outcome(val operation: String, val body: Any? = null, val exception: Throwable? = null) {
        fun matchesError(name: String): Boolean {
            val rule = Operations.ERRORS[name] ?: throw NotMapped("error", name, Operations.ERRORS.keys)
            val failure = exception ?: return false
            val exceptionOk = rule.exception.isEmpty() || failure::class.simpleName == rule.exception
            val textOk = rule.text.isEmpty() || failure.message.orEmpty().contains(rule.text, ignoreCase = true)
            return exceptionOk && textOk && (rule.exception.isNotEmpty() || rule.text.isNotEmpty())
        }
    }

    val clock = MutableClock()
    val stubs = Stubs()
    val headers = HashMap<String, Map<String, String>>()               // actor -> what proves the sign-in
    val before = LinkedHashMap<String, List<Map<String, Any?>>>()
    val tracked = sortedSetOf<String>()
    var outcome: Outcome? = null
    var queriesBefore: Int? = null                                      // statements run before the last action
    var seams: Seams = ProjectSeams(this)
    private var snapshotTaken = false

    /** Called by the Before hook with the scenario's tags. */
    fun begin(tags: Collection<String>) {
        seams = if ("@FEAT-000" in tags) SampleSeams(this) else ProjectSeams(this)
    }

    fun track(entity: String) {
        tracked.add(entity)
    }

    /**
     * Called before every action: remember what every tracked entity looked like before the first one, and how many
     * database statements had run before this one.
     */
    fun act() {
        if (!snapshotTaken) {
            tracked.forEach { before[it] = seams.records(it).toList() }
            snapshotTaken = true
        }
        queriesBefore = try {
            seams.queriesExecuted()
        } catch (noCounter: ExpectedMissing) {
            null                                                         // only a scenario that counts needs the seam
        }
    }

    /** The last action ran at most [limit] statements (an N+1 problem shows as a count that grows with the rows). */
    fun assertQueriesAtMost(operation: String, limit: Int) {
        val last = outcome
        if (last != null && last.operation != operation) {
            throw AssertionError("the last action was '${last.operation}', not '$operation'")
        }
        val total = seams.queriesExecuted()                              // raises ExpectedMissing without a counter
        val start = queriesBefore ?: throw AssertionError("no action ran before this check: a When step has to run first")
        val ran = total - start
        if (ran > limit) {
            throw AssertionError(
                "$operation ran $ran queries, more than the $limit allowed " +
                    "(a count that grows with the number of records is an N+1 problem)",
            )
        }
    }

    fun last(): Outcome = outcome ?: throw AssertionError("there is no result yet: a When step has to run first")
}
