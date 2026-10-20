package greenlight.drivers

/**
 * Seams for the sample feature only: an in-memory store, so that a fresh scaffold has a green scenario before the project
 * has any seams. Delete it together with the sample feature, FEAT-000.
 */
class SampleSeams(world: World) : Seams(world) {
    private val store = HashMap<String, MutableList<Map<String, Any?>>>()

    override fun seed(entity: String, rows: List<Map<String, Any?>>) {
        store.getOrPut(entity) { ArrayList() }.addAll(rows)
    }

    override fun records(entity: String): List<Map<String, Any?>> = store[entity].orEmpty().map { LinkedHashMap(it) }

    override fun runJob(job: String) {
        world.stubs.call("payments", "charge", mapOf("amount" to 5L, "job" to job))
    }
}
