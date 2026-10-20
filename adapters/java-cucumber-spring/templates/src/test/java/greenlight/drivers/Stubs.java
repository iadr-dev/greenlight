package greenlight.drivers;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Stubbed external dependencies.
 *
 * <p>Route the application's outbound calls through {@code call(dependency, operation, request)} (a gateway interface
 * whose test implementation delegates here) or point an HTTP stub library at {@link #respond}. A call the scenario
 * did not stub fails the scenario.
 */
public final class Stubs {
    private record Call(String dependency, String operation, Object request) {
    }

    private final Map<String, Object> responses = new HashMap<>();
    private final List<Call> calls = new ArrayList<>();

    private static String key(String dependency, String operation) {
        return dependency + "\u0000" + operation;
    }

    public void respond(String dependency, String operation, Object response) {
        responses.put(key(dependency, operation), response);
    }

    public Object call(String dependency, String operation, Object request) {
        calls.add(new Call(dependency, operation, request));
        String key = key(dependency, operation);
        if (!responses.containsKey(key)) {
            throw new Errors.UnstubbedCall(dependency + " was asked to " + operation + " but the scenario did not stub it");
        }
        return responses.get(key);
    }

    public void assertReceived(String dependency, String operation, Object expected) {
        List<Object> requests = new ArrayList<>();
        for (Call call : calls) {
            if (call.dependency().equals(dependency) && call.operation().equals(operation)) {
                requests.add(call.request());
            }
        }
        if (requests.isEmpty()) {
            List<String> seen = new ArrayList<>();
            calls.forEach(c -> seen.add(c.dependency() + "/" + c.operation()));
            throw new AssertionError(dependency + " never received " + operation + "; it received " + seen);
        }
        boolean nothingToCompare = expected == null || (expected instanceof List<?> l && l.isEmpty())
                || (expected instanceof Map<?, ?> m && m.isEmpty());
        if (nothingToCompare) {
            return;
        }
        List<String> problems = new ArrayList<>();
        for (Object request : requests) {
            try {
                Compare.assertSubset(request, expected, dependency + " " + operation);
                return;
            } catch (AssertionError mismatch) {
                problems.add(mismatch.getMessage());
            }
        }
        throw new AssertionError(String.join("; ", problems));
    }
}
