package greenlight.drivers

/**
 * Stubbed external dependencies.
 *
 * Route the code's outbound calls through `call(dependency, operation, request)` (a gateway interface whose test
 * implementation delegates here, or a fake of an Android service such as a push or a billing client). A call the scenario
 * did not stub fails the scenario.
 */
class Stubs {
    private data class Call(val dependency: String, val operation: String, val request: Any?)

    private val responses = HashMap<Pair<String, String>, Any?>()
    private val calls = ArrayList<Call>()

    fun respond(dependency: String, operation: String, response: Any?) {
        responses[dependency to operation] = response
    }

    fun call(dependency: String, operation: String, request: Any? = null): Any? {
        calls.add(Call(dependency, operation, request))
        val key = dependency to operation
        if (!responses.containsKey(key)) {
            throw UnstubbedCall("$dependency was asked to $operation but the scenario did not stub it")
        }
        return responses[key]
    }

    fun assertReceived(dependency: String, operation: String, expected: Any?) {
        val requests = calls.filter { it.dependency == dependency && it.operation == operation }.map { it.request }
        if (requests.isEmpty()) {
            throw AssertionError("$dependency never received $operation; it received ${calls.map { "${it.dependency}/${it.operation}" }}")
        }
        if (expected == null || (expected is List<*> && expected.isEmpty()) || (expected is Map<*, *> && expected.isEmpty())) return
        val problems = ArrayList<String>()
        for (request in requests) {
            try {
                Compare.assertSubset(request, expected, "$dependency $operation")
                return
            } catch (mismatch: AssertionError) {
                problems.add(mismatch.message.orEmpty())
            }
        }
        throw AssertionError(problems.joinToString("; "))
    }
}
