package sample.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp

/** A small Compose screen for the contract test: a counter, a text field and a checkbox, each with a test tag. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var count by rememberSaveable { mutableIntStateOf(0) }
            var name by rememberSaveable { mutableStateOf("") }
            var agreed by rememberSaveable { mutableStateOf(false) }
            Column(Modifier.padding(24.dp).semantics { testTagsAsResourceId = true }) {
                Text("$count", Modifier.testTag("count"))
                Button(onClick = { count += 1 }, modifier = Modifier.testTag("add")) { Text("Add one") }
                TextField(value = name, onValueChange = { name = it }, modifier = Modifier.testTag("name"))
                Checkbox(checked = agreed, onCheckedChange = { agreed = it }, modifier = Modifier.testTag("agree"))
                if (!agreed) Text("Agree first", Modifier.testTag("error"))
            }
        }
    }
}
