package sample.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp
import kotlin.math.abs

/** A small Compose app for the contract test: a counter, a form, a scrolling list, a swipe area and a second screen. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var onNextScreen by rememberSaveable { mutableStateOf(false) }
            BackHandler(enabled = onNextScreen) { onNextScreen = false }
            Column(Modifier.padding(24.dp).semantics { testTagsAsResourceId = true }) {
                if (onNextScreen) Text("Next page", Modifier.testTag("title")) else FirstScreen { onNextScreen = true }
            }
        }
    }
}

@androidx.compose.runtime.Composable
private fun FirstScreen(onNext: () -> Unit) {
    var count by rememberSaveable { mutableIntStateOf(0) }
    var name by rememberSaveable { mutableStateOf("") }
    var agreed by rememberSaveable { mutableStateOf(false) }
    var swiped by rememberSaveable { mutableStateOf("none") }
    val feed = rememberLazyListState()
    Text("First page", Modifier.testTag("title"))
    Text("$count", Modifier.testTag("count"))
    Button(onClick = { count += 1 }, modifier = Modifier.testTag("add")) { Text("Add one") }
    TextField(value = name, onValueChange = { name = it }, modifier = Modifier.testTag("name"))
    Checkbox(checked = agreed, onCheckedChange = { agreed = it }, modifier = Modifier.testTag("agree"))
    if (!agreed) Text("Agree first", Modifier.testTag("error"))
    LazyColumn(Modifier.height(96.dp).fillMaxWidth().testTag("feed"), state = feed) {
        items(30) { Text("Item $it") }
    }
    Text(if (feed.firstVisibleItemIndex > 0) "scrolled" else "top", Modifier.testTag("scrolled"))
    Box(Modifier.height(96.dp).fillMaxWidth().testTag("deck").pointerInput(Unit) {
        var travelled = androidx.compose.ui.geometry.Offset.Zero
        detectDragGestures(
            onDragStart = { travelled = androidx.compose.ui.geometry.Offset.Zero },
            onDragEnd = {
                swiped = if (abs(travelled.x) >= abs(travelled.y)) (if (travelled.x < 0) "left" else "right") else (if (travelled.y < 0) "up" else "down")
            },
        ) { _, drag -> travelled += drag }
    }) { Text("deck") }
    Text(swiped, Modifier.testTag("swiped"))
    Button(onClick = onNext, modifier = Modifier.testTag("next")) { Text("Next") }
}
