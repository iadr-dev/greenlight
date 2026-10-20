package greenlight.drivers

import java.time.Clock
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeParseException

/**
 * The injected clock. Give the code under test a [java.time.Clock] (Android's core library desugaring makes it available
 * on every API level) and read time only through it; pass `world.clock` in the seams. Until a scenario sets the time it
 * follows the real clock.
 */
class MutableClock : Clock() {
    @Volatile
    private var frozen: Instant? = null

    fun set(text: String) {
        val iso = text.trim().replace(' ', 'T')
        frozen = try {
            ZonedDateTime.parse(iso).toInstant()
        } catch (noZone: DateTimeParseException) {
            LocalDateTime.parse(iso).toInstant(ZoneOffset.UTC)
        }
    }

    fun advance(text: String) {
        val moment = frozen ?: throw AssertionError("set the current time first (Given the current time is ...)")
        frozen = moment.plus(Compare.duration(text))
    }

    override fun instant(): Instant = frozen ?: Instant.now()

    override fun getZone(): ZoneId = ZoneOffset.UTC

    override fun withZone(zone: ZoneId): Clock = fixed(instant(), zone)
}
