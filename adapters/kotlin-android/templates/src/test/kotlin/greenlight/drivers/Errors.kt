package greenlight.drivers

/** Errors the drivers raise. The marker in [ExpectedMissing] is what the red gate classifies on. */
const val MARKER = "BDD_EXPECTED_MISSING"

/** The system under test does not have this yet. During the red phase this is the right failure. */
class ExpectedMissing(what: String) : AssertionError("$MARKER: $what does not exist yet")

/** The system called an external dependency that the scenario did not stub. */
class UnstubbedCall(message: String) : AssertionError(message)

/**
 * A logical name in a feature has no entry in Operations.kt. This is a defect of the test, not a missing feature, and the
 * run classifies it as one.
 */
class NotMapped(kind: String, name: String, known: Collection<String>) :
    RuntimeException("NotMapped: no $kind named '$name' in Operations.kt (known: ${known.sorted()})")
