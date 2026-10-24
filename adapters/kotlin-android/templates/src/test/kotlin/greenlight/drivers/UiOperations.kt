package greenlight.drivers

/**
 * The screens and components of the application, by the logical names the features use. Features never contain resource
 * ids, activity names or deep links. The step-engineer fills this in from the system map (system.md).
 *
 * This is plain data, so it compiles for the local JVM tests too; only the device run (`src/device`) reads it.
 */
object UiOperations {
    /** How a screen is opened: the app is launched, at [activity] or at the deep link [uri] when one is given. */
    data class Screen(val packageName: String, val activity: String? = null, val uri: String? = null)

    /** How a component is found on the screen. For Compose, expose test tags as resource ids and use [Id]. */
    sealed interface Target {
        data class Id(val value: String) : Target
        data class Text(val value: String) : Target
        data class Description(val value: String) : Target
    }

    val SCREENS: MutableMap<String, Screen> = linkedMapOf(
        // "orders" to Screen("com.example.shop", uri = "shop://orders"),
    )

    val TARGETS: MutableMap<String, Target> = linkedMapOf(
        // "checkout button" to Target.Id("checkout"),
    )

    /** How long a screen or component may take to appear before it counts as missing. Every wait ends as soon as it can. */
    var waitMs: Long = 5_000
}
