package greenlight.drivers;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

/**
 * The injected clock. Give the application a {@link java.time.Clock} bean (see GreenlightTestConfig, which replaces it
 * with this one in tests) and read time only through it. Before a scenario sets the time it follows the real clock.
 */
public final class MutableClock extends Clock {
    private volatile Instant frozen;

    public void set(String text) {
        String iso = text.strip().replace(' ', 'T');
        Instant moment;
        try {
            moment = ZonedDateTime.parse(iso).toInstant();
        } catch (java.time.format.DateTimeParseException noZone) {
            moment = LocalDateTime.parse(iso).toInstant(ZoneOffset.UTC);
        }
        frozen = moment;
    }

    public void advance(String text) {
        if (frozen == null) {
            throw new AssertionError("set the current time first (Given the current time is ...)");
        }
        frozen = frozen.plus(Compare.duration(text));
    }

    /** Back to the real clock; called before every scenario because the bean outlives it. */
    public void reset() {
        frozen = null;
    }

    @Override
    public Instant instant() {
        Instant moment = frozen;
        return moment != null ? moment : Instant.now();
    }

    @Override
    public ZoneId getZone() {
        return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return Clock.fixed(instant(), zone);
    }
}
