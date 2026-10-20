package greenlight.drivers

import io.cucumber.datatable.DataTable
import java.math.BigDecimal
import java.time.Duration

/** Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say. */
object Compare {
    private val DURATION = Regex(
        "(\\d+(?:\\.\\d+)?)\\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\\b",
        RegexOption.IGNORE_CASE,
    )

    /** A table with a header row as a list of maps; cells are JSON when they parse, else text. */
    fun rows(table: DataTable?): List<Map<String, Any?>> = rows(table?.let { cellsOf(it) })

    /** The cells of a table as non-null strings (an empty cell is an empty string). */
    fun cellsOf(table: DataTable): List<List<String>> = table.cells().map { row -> row.map { it.orEmpty() } }

    fun rows(cells: List<List<String>>?): List<Map<String, Any?>> {
        if (cells.isNullOrEmpty()) return emptyList()
        val header = cells.first()
        return cells.drop(1).map { row ->
            header.zip(row).associate { (name, cell) -> name to Json.parseValue(cell) }
        }
    }

    /** The data a step carries: a doc string as JSON or text, or a table (one row becomes an object). */
    fun payload(table: List<List<String>>?, docString: String?): Any? {
        if (docString != null) return Json.parseValue(docString)
        val found = rows(table)
        return if (found.size == 1) found.first() else found
    }

    /** A table or doc string as plain text (CSV-like rows for a table). */
    fun text(table: List<List<String>>?, docString: String?): String =
        docString ?: table.orEmpty().joinToString("") { it.joinToString(",") + "\n" }

    /** A stable order for comparing record sets where the order does not matter. */
    val byContent: Comparator<Map<String, Any?>> = compareBy { Json.write(it) }

    fun assertEqual(actual: Any?, expected: Any?, what: String) {
        if (!same(actual, expected)) {
            throw AssertionError("$what: expected ${Json.write(expected)} but got ${Json.write(actual)}")
        }
    }

    /** Every field of [expected] is in [actual] (recursively); lists must contain each expected item. */
    fun assertSubset(actual: Any?, expected: Any?, what: String) {
        val problem = subsetProblem(actual, expected, "")
        if (problem != null) throw AssertionError("$what: $problem (actual: ${Json.write(actual)})")
    }

    internal fun subsetProblem(actual: Any?, expected: Any?, path: String): String? = when (expected) {
        is Map<*, *> -> objectProblem(actual, expected, path)
        is List<*> -> listProblem(actual, expected, path)
        else -> if (same(actual, expected)) null else "${where(path)} is ${Json.write(actual)}, expected ${Json.write(expected)}"
    }

    private fun where(path: String) = path.ifEmpty { "value" }

    private fun objectProblem(actual: Any?, expected: Map<*, *>, path: String): String? {
        if (actual !is Map<*, *>) return "${where(path)} should be an object"
        for ((key, wanted) in expected) {
            val here = if (path.isEmpty()) key.toString() else "$path.$key"
            val problem = if (actual.containsKey(key)) subsetProblem(actual[key], wanted, here) else "$here is missing"
            if (problem != null) return problem
        }
        return null
    }

    private fun listProblem(actual: Any?, expected: List<*>, path: String): String? {
        if (actual !is List<*>) return "${where(path)} should be a list"
        val missing = expected.indexOfFirst { item -> actual.none { subsetProblem(it, item, path) == null } }
        return if (missing < 0) null else "${where(path)} has no item matching ${Json.write(expected[missing])}"
    }

    /** Equality where 1 and 1.0 are the same number. */
    fun same(actual: Any?, expected: Any?): Boolean = when {
        actual is Number && expected is Number -> BigDecimal(actual.toString()).compareTo(BigDecimal(expected.toString())) == 0
        actual is Map<*, *> && expected is Map<*, *> ->
            actual.keys == expected.keys && actual.keys.all { same(actual[it], expected[it]) }
        actual is List<*> && expected is List<*> ->
            actual.size == expected.size && actual.indices.all { same(actual[it], expected[it]) }
        else -> actual == expected
    }

    /** Line endings and surrounding whitespace do not matter; blank lines do not either. */
    fun normaliseText(text: String): String =
        text.replace("\r\n", "\n").trim().split("\n").filter { it.isNotBlank() }.joinToString("\n") { it.trimEnd() }

    fun assertTextContains(actual: String, expected: String, what: String) {
        val wanted = normaliseText(expected)
        val got = normaliseText(actual)
        if (!got.contains(wanted)) throw AssertionError("$what does not contain '$wanted'; it is '$got'")
    }

    /** '2 days', '30 minutes', '1h 30m' as a Duration. */
    fun duration(text: String): Duration {
        val found = DURATION.findAll(text).toList()
        val rest = DURATION.replace(text, "").replace(",", "").replace("and", "").trim()
        if (found.isEmpty() || rest.isNotEmpty()) throw AssertionError("cannot read the duration '$text'")
        val seconds = found.sumOf { it.groupValues[1].toDouble() * unitSeconds(it.groupValues[2].lowercase().first()) }
        return Duration.ofMillis(Math.round(seconds * 1000))
    }

    private fun unitSeconds(unit: Char): Long = when (unit) {
        'm' -> 60
        'h' -> 3600
        'd' -> 86400
        'w' -> 604800
        else -> 1
    }
}
