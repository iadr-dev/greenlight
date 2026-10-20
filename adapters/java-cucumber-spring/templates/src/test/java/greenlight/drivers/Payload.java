package greenlight.drivers;

import java.util.List;

/**
 * What a step carries after its last line: a table (as rows of cells), a doc string, or nothing. The converters in
 * {@code greenlight.steps.ParameterTypes} make Cucumber hand either kind to one step method.
 */
public record Payload(List<List<String>> table, String docString) {
    /** The data: a doc string as JSON or text, or a table (one row becomes an object). */
    public Object data() {
        return Compare.payload(table, docString);
    }

    /** The content as plain text (a table becomes CSV-like rows). */
    public String text() {
        return Compare.text(table, docString);
    }
}
