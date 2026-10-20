package greenlight.drivers;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Seams for the sample feature only: an in-memory store, so that a fresh scaffold has a green scenario before the
 * project has any seams. Delete it together with the sample feature, FEAT-000.
 */
public class SampleSeams extends Seams {
    private final Map<String, List<Map<String, Object>>> store = new HashMap<>();

    public SampleSeams(World world) {
        super(world);
    }

    @Override
    public void seed(String entity, List<Map<String, Object>> rows) {
        store.computeIfAbsent(entity, name -> new ArrayList<>()).addAll(rows);
    }

    @Override
    public List<Map<String, Object>> records(String entity) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> row : store.getOrDefault(entity, List.of())) {
            rows.add(new LinkedHashMap<>(row));
        }
        return rows;
    }

    @Override
    public void runJob(String job) {
        world.stubs.call("payments", "charge", Map.of("amount", 5L, "job", job));
    }
}
