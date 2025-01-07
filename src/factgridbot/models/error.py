from pydantic import BaseModel
from rich.table import Table


class SyncErrorRecord(BaseModel):
    """
    contains information about the sync failure
    """

    wd_id: str
    factgrid_id: str
    error_message: str

    @classmethod
    def convert_list_to_table(cls, records: list["SyncErrorRecord"]) -> Table:
        table = Table(title="Failed Syncs")

        table.add_column("Wikidata ID", justify="left", style="cyan", no_wrap=True)
        table.add_column("FactGrid ID", justify="left", style="cyan", no_wrap=True)
        table.add_column(
            "Error Message",
            justify="left",
            style="red",
        )
        for record in records:
            table.add_row(record.wd_id, record.factgrid_id, record.error_message)
        return table
