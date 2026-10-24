package greenlight.drivers

import android.content.Intent
import android.net.Uri
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.util.regex.Pattern

/**
 * What a user does and sees on a device, through UI Automator (the device's accessibility tree, so Compose and View
 * screens alike). Names come from [UiOperations]; the steps and the features only use logical names. Every check waits
 * for the condition and ends as soon as it holds: there are no fixed sleeps.
 *
 * A component or screen that is not there is [ExpectedMissing]: the feature is not built yet, which is a valid red.
 */
object UiDriver {
    enum class Action { CLICKS, FILLS, SELECTS, UPLOADS, TYPES, TOGGLES, SWIPES, SCROLLS }

    /** How much of the component a swipe or a scroll covers. */
    private const val GESTURE_SHARE = 0.6f

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val device: UiDevice get() = UiDevice.getInstance(instrumentation)
    private val opened = linkedSetOf<String>()

    private fun selector(name: String): BySelector = when (val target = UiOperations.TARGETS[name]
        ?: throw NotMapped("target", name, UiOperations.TARGETS.keys)) {
        is UiOperations.Target.Id -> By.res(target.value)
        is UiOperations.Target.Text -> By.text(target.value)
        is UiOperations.Target.Description -> By.desc(target.value)
    }

    private fun present(name: String): UiObject2 =
        device.wait(Until.findObject(selector(name)), UiOperations.waitMs)
            ?: throw ExpectedMissing("the $name component on the screen")

    fun open(name: String) {
        val screen = UiOperations.SCREENS[name] ?: throw NotMapped("screen", name, UiOperations.SCREENS.keys)
        val context = instrumentation.targetContext
        val intent = when {
            screen.uri != null -> Intent(Intent.ACTION_VIEW, Uri.parse(screen.uri)).setPackage(screen.packageName)
            screen.activity != null -> Intent().setClassName(screen.packageName, screen.activity)
            else -> context.packageManager.getLaunchIntentForPackage(screen.packageName)
                ?: throw ExpectedMissing("the app ${screen.packageName} installed on the device")
        }
        context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        if (!device.wait(Until.hasObject(By.pkg(screen.packageName).depth(0)), UiOperations.waitMs)) {
            throw ExpectedMissing("the screen $name (the app ${screen.packageName} did not come to the front)")
        }
        opened += screen.packageName
    }

    private fun directionOf(value: String?): Direction = when (value?.trim()?.lowercase()) {
        "up" -> Direction.UP
        "down" -> Direction.DOWN
        "left" -> Direction.LEFT
        "right" -> Direction.RIGHT
        else -> throw AssertionError("give a direction in a table (| direction |): up, down, left or right, not '$value'")
    }

    /** Go back, the way the platform does (the system back action or gesture). */
    fun back() {
        device.pressBack()
        device.waitForIdle()
    }

    fun act(action: Action, target: String, value: String?) {
        val component = present(target)
        when (action) {
            Action.CLICKS, Action.TOGGLES -> component.click()
            Action.FILLS, Action.TYPES -> component.text = value ?: throw AssertionError("give the value in a table (| value |) or a doc string")
            Action.SELECTS -> {
                component.click()
                val option = value ?: throw AssertionError("give the value in a table (| value |) or a doc string")
                (device.wait(Until.findObject(By.text(option)), UiOperations.waitMs)
                    ?: throw ExpectedMissing("the option '$option' of $target")).click()
            }
            Action.SWIPES -> component.swipe(directionOf(value), GESTURE_SHARE)       // the finger moves in the direction
            Action.SCROLLS -> component.scroll(directionOf(value), GESTURE_SHARE)     // the view moves in the direction
            Action.UPLOADS -> throw ExpectedMissing(
                "a way to hand a file to the screen (the device's file picker is another app: give the app a seam)",
            )
        }
        device.waitForIdle()
    }

    /** The texts shown inside [component], in the order the screen lists them. */
    private fun textsInside(component: UiObject2): List<String> =
        component.findObjects(By.text(Pattern.compile(".+"))).mapNotNull { it.text }

    /** The visible state of a component: `text`, `value`, `enabled`, `checked`, `visible` columns, or `item` rows. */
    fun assertShows(target: String, rows: List<Map<String, Any?>>, docString: String?) {
        if (docString != null) {
            expect("the text of $target", docString.trim(), present(target).text.orEmpty())
            return
        }
        if (rows.isNotEmpty() && rows.all { "item" in it }) {
            expect("the items of $target", rows.map { it["item"].toString() }, textsInside(present(target)))
            return
        }
        val expected = rows.firstOrNull().orEmpty()
        if (expected["visible"] == false) {
            if (!device.wait(Until.gone(selector(target)), UiOperations.waitMs)) throw AssertionError("$target should be hidden")
            return
        }
        val component = present(target)
        for ((column, value) in expected) {
            when (column) {
                "text", "value" -> expect("the $column of $target", value.toString(), component.text.orEmpty())
                "enabled" -> expect("whether $target is enabled", value != false, component.isEnabled)
                "checked" -> expect("whether $target is checked", value != false, component.isChecked)
                "visible" -> Unit                                                   // it is on the screen: that is what visible asks
                else -> throw NotMapped("column", column, listOf("text", "value", "enabled", "checked", "visible", "item"))
            }
        }
    }

    fun assertHidden(target: String) {
        if (!device.wait(Until.gone(selector(target)), UiOperations.waitMs)) {
            throw AssertionError("$target should not be on the screen")
        }
    }

    /**
     * Called after every scenario: go home, and stop the other apps the scenario opened so that the next scenario starts from
     * nothing. The app under test is never stopped: in an application module the tests run inside its process, so stopping
     * it would end the test run. Opening a screen starts a fresh task, which gives the next scenario a new screen.
     */
    fun reset() {
        val own = instrumentation.targetContext.packageName
        opened.filter { it != own }.forEach { device.executeShellCommand("am force-stop $it") }
        opened.clear()
        device.pressHome()
    }

    private fun expect(what: String, expected: Any?, actual: Any?) {
        if (expected != actual) throw AssertionError("$what: expected $expected but got $actual")
    }
}
