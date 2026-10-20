package greenlight.drivers

/** Calling the code under test by its logical name; the return value or the raised error is kept. */
object LibDriver {
    fun call(world: World, operation: String, data: Any?): World.Outcome {
        val function = Operations.LIB[operation] ?: throw NotMapped("library operation", operation, Operations.LIB.keys)
        world.outcome = try {
            World.Outcome(operation, body = function(data))
        } catch (error: Exception) {                          // the scenario decides whether this error was wanted
            World.Outcome(operation, exception = error)
        }
        return world.last()
    }

    fun assertResult(world: World, expected: Any?, exact: Boolean) {
        val outcome = world.last()
        outcome.exception?.let { throw AssertionError("the call raised ${it::class.simpleName}: ${it.message}") }
        if (exact) Compare.assertEqual(outcome.body, expected, "the result") else Compare.assertSubset(outcome.body, expected, "the result")
    }

    fun assertFails(world: World, error: String) {
        val outcome = world.last()
        val failure = outcome.exception ?: throw AssertionError("the call should fail but returned ${Json.write(outcome.body)}")
        if (!outcome.matchesError(error)) {
            throw AssertionError("the call failed, but not with '$error': ${failure::class.simpleName}: ${failure.message}")
        }
    }
}
