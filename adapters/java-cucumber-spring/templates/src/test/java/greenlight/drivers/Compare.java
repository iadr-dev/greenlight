package greenlight.drivers;

import io.cucumber.datatable.DataTable;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say. */
public final class Compare {
    private static final Pattern DURATION = Pattern.compile(
            "(\\d+(?:\\.\\d+)?)\\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\\b",
            Pattern.CASE_INSENSITIVE);

    private Compare() {
    }

    /** A table with a header row as a list of maps; cells are JSON when they parse, else text. */
    public static List<Map<String, Object>> rows(DataTable table) {
        return rows(table == null ? null : table.asLists());
    }

    public static List<Map<String, Object>> rows(List<List<String>> cells) {
        List<Map<String, Object>> found = new ArrayList<>();
        if (cells == null || cells.isEmpty()) {
            return found;
        }
        List<String> header = cells.get(0);
        for (List<String> row : cells.subList(1, cells.size())) {
            Map<String, Object> record = new LinkedHashMap<>();
            for (int i = 0; i < header.size() && i < row.size(); i++) {
                record.put(header.get(i), Json.parseValue(row.get(i)));
            }
            found.add(record);
        }
        return found;
    }

    /** The data a step carries: a doc string as JSON or text, or a table (one row becomes an object). */
    public static Object payload(List<List<String>> table, String docString) {
        if (docString != null) {
            return Json.parseValue(docString);
        }
        List<Map<String, Object>> found = rows(table);
        return found.size() == 1 ? found.get(0) : found;
    }

    /** A table or doc string as plain text (CSV-like rows for a table). */
    public static String text(List<List<String>> table, String docString) {
        if (docString != null) {
            return docString;
        }
        StringBuilder out = new StringBuilder();
        if (table != null) {
            for (List<String> row : table) {
                out.append(String.join(",", row)).append('\n');
            }
        }
        return out.toString();
    }

    /** A stable order for comparing record sets where the order does not matter. */
    public static Comparator<Map<String, Object>> byContent() {
        return Comparator.comparing(Json::write);
    }

    public static void assertEqual(Object actual, Object expected, String what) {
        if (!same(actual, expected)) {
            throw new AssertionError(what + ": expected " + Json.write(expected) + " but got " + Json.write(actual));
        }
    }

    /** Every field of {@code expected} is in {@code actual} (recursively); lists must contain each expected item. */
    public static void assertSubset(Object actual, Object expected, String what) {
        String problem = subsetProblem(actual, expected, "");
        if (problem != null) {
            throw new AssertionError(what + ": " + problem + " (actual: " + Json.write(actual) + ")");
        }
    }

    static String subsetProblem(Object actual, Object expected, String path) {
        String where = path.isEmpty() ? "value" : path;
        if (expected instanceof Map<?, ?> wanted) {
            if (!(actual instanceof Map<?, ?> found)) {
                return where + " should be an object";
            }
            for (Map.Entry<?, ?> entry : wanted.entrySet()) {
                String key = String.valueOf(entry.getKey());
                String here = path.isEmpty() ? key : path + "." + key;
                if (!found.containsKey(entry.getKey())) {
                    return here + " is missing";
                }
                String problem = subsetProblem(found.get(entry.getKey()), entry.getValue(), here);
                if (problem != null) {
                    return problem;
                }
            }
            return null;
        }
        if (expected instanceof List<?> wantedItems) {
            if (!(actual instanceof List<?> foundItems)) {
                return where + " should be a list";
            }
            for (Object item : wantedItems) {
                boolean present = false;
                for (Object candidate : foundItems) {
                    if (subsetProblem(candidate, item, path) == null) {
                        present = true;
                        break;
                    }
                }
                if (!present) {
                    return where + " has no item matching " + Json.write(item);
                }
            }
            return null;
        }
        return same(actual, expected) ? null : where + " is " + Json.write(actual) + ", expected " + Json.write(expected);
    }

    /** Equality where 1 and 1.0 are the same number. */
    public static boolean same(Object actual, Object expected) {
        if (actual instanceof Number a && expected instanceof Number b) {
            return new BigDecimal(a.toString()).compareTo(new BigDecimal(b.toString())) == 0;
        }
        if (actual instanceof Map<?, ?> a && expected instanceof Map<?, ?> b) {
            if (!a.keySet().equals(b.keySet())) {
                return false;
            }
            for (Object key : a.keySet()) {
                if (!same(a.get(key), b.get(key))) {
                    return false;
                }
            }
            return true;
        }
        if (actual instanceof List<?> a && expected instanceof List<?> b) {
            if (a.size() != b.size()) {
                return false;
            }
            for (int i = 0; i < a.size(); i++) {
                if (!same(a.get(i), b.get(i))) {
                    return false;
                }
            }
            return true;
        }
        return actual == null ? expected == null : actual.equals(expected);
    }

    /** Line endings and surrounding whitespace do not matter; blank lines do not either. */
    public static String normaliseText(String text) {
        StringBuilder out = new StringBuilder();
        for (String line : text.replace("\r\n", "\n").strip().split("\n")) {
            if (!line.isBlank()) {
                out.append(out.length() > 0 ? "\n" : "").append(line.stripTrailing());
            }
        }
        return out.toString();
    }

    public static void assertTextContains(String actual, String expected, String what) {
        String wanted = normaliseText(expected);
        String got = normaliseText(actual);
        if (!got.contains(wanted)) {
            throw new AssertionError(what + " does not contain '" + wanted + "'; it is '" + got + "'");
        }
    }

    /** '2 days', '30 minutes', '1h 30m' as a Duration. */
    public static Duration duration(String text) {
        Matcher matcher = DURATION.matcher(text);
        double seconds = 0;
        int end = 0;
        while (matcher.find()) {
            seconds += Double.parseDouble(matcher.group(1)) * unitSeconds(matcher.group(2).toLowerCase(Locale.ROOT).charAt(0));
            end = matcher.end();
        }
        String rest = DURATION.matcher(text).replaceAll("").replace(",", "").replace("and", "").strip();
        if (end == 0 || !rest.isEmpty()) {
            throw new AssertionError("cannot read the duration '" + text + "'");
        }
        return Duration.ofMillis(Math.round(seconds * 1000));
    }

    private static long unitSeconds(char unit) {
        return switch (unit) {
            case 'm' -> 60;
            case 'h' -> 3600;
            case 'd' -> 86400;
            case 'w' -> 604800;
            default -> 1;
        };
    }
}
