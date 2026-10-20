package greenlight.drivers

/**
 * A small JSON reader and writer, so the drivers depend on no particular JSON library or version.
 *
 * Objects are `Map<String, Any?>`, arrays `List<Any?>`, numbers `Long` or `Double`, plus `String`, `Boolean` and `null`.
 */
object Json {
    private val NUMBER = Regex("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")

    /** The text as data, or the trimmed text itself when it is not JSON (a table cell such as `tea` stays text). */
    fun parseValue(cell: String): Any? {
        val trimmed = cell.trim()
        return try {
            parse(trimmed)
        } catch (notJson: IllegalArgumentException) {
            trimmed
        }
    }

    /** Strict parsing; throws IllegalArgumentException when the text is not exactly one JSON value. */
    fun parse(source: String): Any? {
        val reader = Reader(source)
        reader.skipSpace()
        val value = reader.value()
        reader.skipSpace()
        require(reader.at == source.length) { "not JSON: unexpected text after the value at ${reader.at}" }
        return value
    }

    fun write(value: Any?): String = StringBuilder().also { write(value, it) }.toString()

    private fun write(value: Any?, out: StringBuilder) {
        when (value) {
            null -> out.append("null")
            is String -> quote(value, out)
            is Map<*, *> -> {
                out.append('{')
                var first = true
                for ((key, item) in value) {
                    if (!first) out.append(',')
                    first = false
                    quote(key.toString(), out)
                    out.append(':')
                    write(item, out)
                }
                out.append('}')
            }
            is List<*> -> {
                out.append('[')
                value.forEachIndexed { index, item ->
                    if (index > 0) out.append(',')
                    write(item, out)
                }
                out.append(']')
            }
            else -> out.append(value)
        }
    }

    private fun quote(text: String, out: StringBuilder) {
        out.append('"')
        for (c in text) {
            when {
                c == '"' -> out.append("\\\"")
                c == '\\' -> out.append("\\\\")
                c == '\n' -> out.append("\\n")
                c == '\r' -> out.append("\\r")
                c == '\t' -> out.append("\\t")
                c < ' ' -> out.append(String.format("\\u%04x", c.code))
                else -> out.append(c)
            }
        }
        out.append('"')
    }

    private class Reader(private val text: String) {
        var at = 0

        fun fail(why: String): IllegalArgumentException = IllegalArgumentException("not JSON: $why at $at")

        fun skipSpace() {
            while (at < text.length && text[at].isWhitespace()) at++
        }

        fun value(): Any? {
            if (at >= text.length) throw fail("empty")
            return when (text[at]) {
                '{' -> obj()
                '[' -> array()
                '"' -> string()
                else -> literal()
            }
        }

        private fun obj(): Map<String, Any?> {
            val map = LinkedHashMap<String, Any?>()
            at++
            skipSpace()
            if (peek('}')) {
                at++
                return map
            }
            while (true) {
                skipSpace()
                if (!peek('"')) throw fail("a key must be a string")
                val key = string()
                skipSpace()
                expect(':')
                skipSpace()
                map[key] = value()
                skipSpace()
                if (peek(',')) at++ else {
                    expect('}')
                    return map
                }
            }
        }

        private fun array(): List<Any?> {
            val list = ArrayList<Any?>()
            at++
            skipSpace()
            if (peek(']')) {
                at++
                return list
            }
            while (true) {
                skipSpace()
                list.add(value())
                skipSpace()
                if (peek(',')) at++ else {
                    expect(']')
                    return list
                }
            }
        }

        private fun string(): String {
            val out = StringBuilder()
            at++
            while (at < text.length) {
                val c = text[at++]
                if (c == '"') return out.toString()
                if (c != '\\') {
                    out.append(c)
                    continue
                }
                if (at >= text.length) break
                when (val escaped = text[at++]) {
                    'n' -> out.append('\n')
                    'r' -> out.append('\r')
                    't' -> out.append('\t')
                    'b' -> out.append('\b')
                    'f' -> out.append('\u000c')
                    'u' -> {
                        if (at + 4 > text.length) throw fail("short unicode escape")
                        out.append(text.substring(at, at + 4).toInt(16).toChar())
                        at += 4
                    }
                    else -> out.append(escaped)
                }
            }
            throw fail("unterminated string")
        }

        private fun literal(): Any? {
            val start = at
            while (at < text.length && text[at] !in ",]} \t\r\n") at++
            return when (val word = text.substring(start, at)) {
                "true" -> true
                "false" -> false
                "null" -> null
                else -> when {
                    !NUMBER.matches(word) -> throw fail("unknown word '$word'")          // JSON's number grammar: 007 and 1. are text
                    word.all { it == '-' || it.isDigit() } -> word.toLong()
                    else -> word.toDouble()
                }
            }
        }

        private fun peek(c: Char) = at < text.length && text[at] == c

        private fun expect(c: Char) {
            if (!peek(c)) throw fail("expected '$c'")
            at++
        }
    }
}
