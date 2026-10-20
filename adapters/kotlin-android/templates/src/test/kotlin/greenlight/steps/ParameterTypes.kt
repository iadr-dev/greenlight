package greenlight.steps

import greenlight.drivers.Compare
import greenlight.drivers.Payload
import io.cucumber.datatable.DataTable
import io.cucumber.java.DataTableType
import io.cucumber.java.DocStringType

/** Lets one step method accept the table or the doc string that follows a step. */
class ParameterTypes {
    @DataTableType
    fun payloadFromTable(table: DataTable): Payload = Payload(Compare.cellsOf(table), null)

    @DocStringType
    fun payloadFromDocString(docString: String): Payload = Payload(null, docString)
}
