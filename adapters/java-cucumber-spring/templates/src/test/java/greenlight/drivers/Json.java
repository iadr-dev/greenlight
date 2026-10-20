package greenlight.drivers;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A small JSON reader and writer, so the drivers depend on no particular JSON library or version.
 *
 * <p>Objects are {@code Map<String, Object>}, arrays {@code List<Object>}, numbers {@code Long} or
 * {@code Double}, plus {@code String}, {@code Boolean} and {@code null}.
 */
public final class Json {
    private final String text;
    private int at;

    private Json(String text) {
        this.text = text;
    }

    /** The text as data, or the trimmed text itself when it is not JSON (a table cell such as {@code tea} stays text). */
    public static Object parseValue(String cell) {
        String trimmed = cell.strip();
        try {
            return parse(trimmed);
        } catch (IllegalArgumentException notJson) {
            return trimmed;
        }
    }

    /** Strict parsing; throws IllegalArgumentException when the text is not one JSON value. */
    public static Object parse(String source) {
        Json reader = new Json(source);
        reader.skipSpace();
        Object value = reader.value();
        reader.skipSpace();
        if (reader.at != source.length()) {
            throw reader.fail("unexpected text after the value");
        }
        return value;
    }

    public static String write(Object value) {
        StringBuilder out = new StringBuilder();
        write(value, out);
        return out.toString();
    }

    private static void write(Object value, StringBuilder out) {
        if (value == null) {
            out.append("null");
        } else if (value instanceof String string) {
            quote(string, out);
        } else if (value instanceof Map<?, ?> map) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                quote(String.valueOf(entry.getKey()), out);
                out.append(':');
                write(entry.getValue(), out);
            }
            out.append('}');
        } else if (value instanceof List<?> list) {
            out.append('[');
            for (int i = 0; i < list.size(); i++) {
                if (i > 0) {
                    out.append(',');
                }
                write(list.get(i), out);
            }
            out.append(']');
        } else {
            out.append(value);
        }
    }

    private static void quote(String string, StringBuilder out) {
        out.append('"');
        for (char c : string.toCharArray()) {
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        out.append('"');
    }

    private IllegalArgumentException fail(String why) {
        return new IllegalArgumentException("not JSON: " + why + " at " + at);
    }

    private void skipSpace() {
        while (at < text.length() && Character.isWhitespace(text.charAt(at))) {
            at++;
        }
    }

    private Object value() {
        if (at >= text.length()) {
            throw fail("empty");
        }
        char c = text.charAt(at);
        return switch (c) {
            case '{' -> object();
            case '[' -> array();
            case '"' -> string();
            default -> literal();
        };
    }

    private Map<String, Object> object() {
        Map<String, Object> map = new LinkedHashMap<>();
        at++;
        skipSpace();
        if (peek('}')) {
            at++;
            return map;
        }
        while (true) {
            skipSpace();
            if (!peek('"')) {
                throw fail("a key must be a string");
            }
            String key = string();
            skipSpace();
            expect(':');
            skipSpace();
            map.put(key, value());
            skipSpace();
            if (peek(',')) {
                at++;
            } else {
                expect('}');
                return map;
            }
        }
    }

    private List<Object> array() {
        List<Object> list = new ArrayList<>();
        at++;
        skipSpace();
        if (peek(']')) {
            at++;
            return list;
        }
        while (true) {
            skipSpace();
            list.add(value());
            skipSpace();
            if (peek(',')) {
                at++;
            } else {
                expect(']');
                return list;
            }
        }
    }

    private String string() {
        StringBuilder out = new StringBuilder();
        at++;
        while (at < text.length()) {
            char c = text.charAt(at++);
            if (c == '"') {
                return out.toString();
            }
            if (c != '\\') {
                out.append(c);
                continue;
            }
            if (at >= text.length()) {
                break;
            }
            char escaped = text.charAt(at++);
            switch (escaped) {
                case 'n' -> out.append('\n');
                case 'r' -> out.append('\r');
                case 't' -> out.append('\t');
                case 'b' -> out.append('\b');
                case 'f' -> out.append('\f');
                case 'u' -> {
                    if (at + 4 > text.length()) {
                        throw fail("short unicode escape");
                    }
                    out.append((char) Integer.parseInt(text.substring(at, at + 4), 16));
                    at += 4;
                }
                default -> out.append(escaped);
            }
        }
        throw fail("unterminated string");
    }

    private Object literal() {
        int start = at;
        while (at < text.length() && ",]} \t\r\n".indexOf(text.charAt(at)) < 0) {
            at++;
        }
        String word = text.substring(start, at);
        switch (word) {
            case "true":
                return Boolean.TRUE;
            case "false":
                return Boolean.FALSE;
            case "null":
                return null;
            default:
                break;
        }
        if (!word.matches("-?(0|[1-9]\\d*)(\\.\\d+)?([eE][+-]?\\d+)?")) {      // JSON's number grammar: 007 and 1. are text
            throw fail("unknown word '" + word + "'");
        }
        return word.matches("-?\\d+") ? (Object) Long.parseLong(word) : (Object) Double.parseDouble(word);
    }

    private boolean peek(char c) {
        return at < text.length() && text.charAt(at) == c;
    }

    private void expect(char c) {
        if (!peek(c)) {
            throw fail("expected '" + c + "'");
        }
        at++;
    }
}
