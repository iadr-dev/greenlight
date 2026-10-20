package greenlight.drivers

/**
 * What a step carries after its last line: a table (as rows of cells), a doc string, or nothing. The converters in
 * `greenlight.steps.ParameterTypes` make Cucumber hand either kind to one step method.
 */
data class Payload(val table: List<List<String>>?, val docString: String?) {
    /** The data: a doc string as JSON or text, or a table (one row becomes an object). */
    fun data(): Any? = Compare.payload(table, docString)

    /** The content as plain text (a table becomes CSV-like rows). */
    fun text(): String = Compare.text(table, docString)
}
