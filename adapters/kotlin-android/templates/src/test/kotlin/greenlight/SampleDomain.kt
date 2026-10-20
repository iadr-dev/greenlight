package greenlight

/** Code under test for the sample feature. Delete it together with the sample feature and its entry in Operations.kt. */
object SampleDomain {
    fun add(a: Long, b: Long): Long {
        require(a >= 0 && b >= 0) { "negative numbers are not allowed" }
        return a + b
    }
}
