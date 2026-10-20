package greenlight.drivers;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** Calling an API operation by its logical name and judging the response by logical result. */
public final class ApiDriver {
    private ApiDriver() {
    }

    @SuppressWarnings("unchecked")
    public static World.Outcome call(World world, String actor, String operation, Object data) {
        Operations.Api route = Operations.API.get(operation);
        if (route == null) {
            throw new Errors.NotMapped("API operation", operation, Operations.API.keySet());
        }
        Map<String, Object> given = data instanceof Map<?, ?> map ? (Map<String, Object>) map : new LinkedHashMap<>();
        Map<String, Object> fields = world.seams.complete(operation, new LinkedHashMap<>(given));   // the project may add what the scenario left out
        String path = route.path();
        Map<String, Object> sent = new LinkedHashMap<>();
        for (Map.Entry<String, Object> field : fields.entrySet()) {
            String placeholder = "{" + field.getKey() + "}";
            if (path.contains(placeholder)) {
                path = path.replace(placeholder, String.valueOf(field.getValue()));
            } else {
                sent.put(field.getKey(), field.getValue());
            }
        }
        boolean query = route.method().equalsIgnoreCase("GET") || route.method().equalsIgnoreCase("DELETE");
        MockHttpServletRequestBuilder request = MockMvcRequestBuilders.request(HttpMethod.valueOf(route.method().toUpperCase()), path);
        world.headers.getOrDefault(actor, Map.of()).forEach(request::header);
        if (query) {
            sent.forEach((name, value) -> request.param(name, String.valueOf(value)));
        } else if (!sent.isEmpty() || data instanceof java.util.List<?>) {
            request.contentType(MediaType.APPLICATION_JSON).content(Json.write(data instanceof java.util.List<?> ? data : sent));
        }
        try {
            MockHttpServletResponse response = world.mvc().perform(request).andReturn().getResponse();
            String text = response.getContentAsString(StandardCharsets.UTF_8);
            world.outcome = new World.Outcome(operation, response.getStatus(), text.isBlank() ? null : Json.parseValue(text));
        } catch (Errors.ExpectedMissing missing) {
            throw missing;
        } catch (Exception failure) {
            throw new AssertionError("the call to " + operation + " could not be made: " + failure, failure);
        }
        return world.outcome;
    }

    public static void assertSucceeds(World world) {
        World.Outcome outcome = world.last();
        if (outcome.status() < 200 || outcome.status() >= 300) {
            throw new AssertionError("the request should succeed but got status " + outcome.status() + ": " + Json.write(outcome.body()));
        }
    }

    public static void assertRejected(World world, String error) {
        World.Outcome outcome = world.last();
        if (outcome.status() < 400) {
            throw new AssertionError("the request should be rejected but got status " + outcome.status());
        }
        if (!outcome.matchesError(error)) {
            throw new AssertionError("the request was rejected, but not with '" + error + "': status " + outcome.status() + ", " + Json.write(outcome.body()));
        }
    }
}
