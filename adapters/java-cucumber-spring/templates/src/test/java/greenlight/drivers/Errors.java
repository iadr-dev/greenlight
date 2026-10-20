package greenlight.drivers;

import java.util.Collection;
import java.util.TreeSet;

/** Errors the drivers raise. The marker in {@link ExpectedMissing} is what the red gate classifies on. */
public final class Errors {
    public static final String MARKER = "BDD_EXPECTED_MISSING";

    private Errors() {
    }

    /** The system under test does not have this yet. During the red phase this is the right failure. */
    public static final class ExpectedMissing extends AssertionError {
        public ExpectedMissing(String what) {
            super(MARKER + ": " + what + " does not exist yet");
        }
    }

    /** The system called an external dependency that the scenario did not stub. */
    public static final class UnstubbedCall extends AssertionError {
        public UnstubbedCall(String message) {
            super(message);
        }
    }

    /** A real network connection was attempted. Stub the dependency instead. */
    public static final class OutboundNetworkBlocked extends AssertionError {
        public OutboundNetworkBlocked(String message) {
            super(message);
        }
    }

    /**
     * A logical name in a feature has no entry in Operations.java. This is a defect of the test, not a missing
     * feature, and the run classifies it as one.
     */
    public static final class NotMapped extends RuntimeException {
        public NotMapped(String kind, String name, Collection<String> known) {
            super("NotMapped: no " + kind + " named '" + name + "' in Operations.java (known: " + new TreeSet<>(known) + ")");
        }
    }
}
