package greenlight.drivers;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The map from the logical names used in features to this system. Features never contain paths, class names or SQL.
 * The step-engineer fills this in from the system map (system.md).
 */
public final class Operations {
    private Operations() {
    }

    /** An API operation. The path may contain {field}, filled from the request data. */
    public record Api(String method, String path) {
    }

    /** What a logical error looks like. Any field that is set must match. */
    public record ErrorRule(List<Integer> statuses, String text) {
        public static ErrorRule status(Integer... statuses) {
            return new ErrorRule(List.of(statuses), "");
        }

        public static ErrorRule text(String text) {
            return new ErrorRule(List.of(), text);
        }
    }

    public static final Map<String, Api> API = new LinkedHashMap<>();
    public static final Map<String, ErrorRule> ERRORS = new LinkedHashMap<>();

    static {
        // API.put("place order", new Api("POST", "/orders"));
        // ERRORS.put("validation error", ErrorRule.status(400, 422));
    }
}
