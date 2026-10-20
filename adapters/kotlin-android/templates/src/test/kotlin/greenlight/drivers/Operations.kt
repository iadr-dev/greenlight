package greenlight.drivers

import greenlight.SampleDomain

/**
 * The map from the logical names used in features to this system. Features never contain class names, function names or
 * SQL. The step-engineer fills this in from the system map (system.md); the sample entries below belong to the sample
 * feature and can be deleted with it.
 */
object Operations {
    /** What a logical error looks like. Any field that is set must match. */
    data class ErrorRule(val exception: String = "", val text: String = "")

    /**
     * Library operations: the code under test that a scenario calls, such as a use case, a repository or a view model
     * method. The function gets the request data (an object, a list or a single value) and returns the result. Plain
     * lambdas, so a rename in the code is a compile error here, not a runtime surprise.
     */
    val LIB: MutableMap<String, (Any?) -> Any?> = linkedMapOf(
        "add" to { data ->
            val fields = data as Map<*, *>
            SampleDomain.add((fields["a"] as Number).toLong(), (fields["b"] as Number).toLong())
        },
    )

    val ERRORS: MutableMap<String, ErrorRule> = linkedMapOf(
        "negative input" to ErrorRule(exception = "IllegalArgumentException"),       // sample
        // "validation error" to ErrorRule(text = "invalid"),
    )
}
