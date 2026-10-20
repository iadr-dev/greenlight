package greenlight.steps;

import greenlight.drivers.Payload;
import io.cucumber.datatable.DataTable;
import io.cucumber.java.DataTableType;
import io.cucumber.java.DocStringType;

/** Lets one step method accept the table or the doc string that follows a step. */
public class ParameterTypes {
    @DataTableType
    public Payload payloadFromTable(DataTable table) {
        return new Payload(table.cells(), null);
    }

    @DocStringType
    public Payload payloadFromDocString(String docString) {
        return new Payload(null, docString);
    }
}
