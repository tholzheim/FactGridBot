import datetime
import logging
from typing import Annotated

import click
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.table import Table

from factgridbot.bot import Bot
from factgridbot.models.auth import (
    Authorization,
    WikibaseAuthorizationConfig,
    WikibaseBotAuth,
    WikibaseLoginTypes,
    WikibaseOauth1,
    WikibaseOauth2,
    WikibaseUserAuth,
)
from factgridbot.models.error import SyncErrorRecord

app = typer.Typer()
factgrid_add_app = typer.Typer()
app.add_typer(factgrid_add_app, name="add", help="Add data to FactGrid")

console = Console()


FORMAT = "%(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()])


@app.command()
def check(
    types: Annotated[bool, typer.Option(help="Check for property type mismatches")] = True,
    mapping: Annotated[bool, typer.Option(help="Check if mappings are a 1:1 mapping")] = True,
):
    bot = Bot(Bot.load_auth())
    if types:
        bot.check_property_type_mappings()
    if mapping:
        bot.check_duplicates_property_mappings()


@app.command()
def sync(
    factgrid_entity: Annotated[str | None, typer.Option(help="FactGrid entity id to sync with wikidata")] = None,
    wd_entity: Annotated[str | None, typer.Option(help="Wikidata entity id to sync with FactGrid")] = None,
    all: Annotated[bool, typer.Option(help="Sync all missing entity links")] = False,
    date: Annotated[
        str | None,
        typer.Option(
            help="Sync all entities that were modified at given date. Use iso-format to specify a date or 'today' or 'yesterday'",  # noqa: E501
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="Check how many Wikidata entities would be affected without adding the FactGrid id"),
    ] = False,
    fix_known_issues: Annotated[
        bool,
        typer.Option(
            help="Fix known entity issues to avoid mediawiki api errors. Fixes errors such as missing coordinate precision",  # noqa: E501
        ),
    ] = False,
):
    """
    Sync Wikidata back references with FactGrid.
    Adds the FactGrid Qid to Items that are in FactGrid and linked to Wikidata
    """
    bot = Bot(Bot.load_auth())
    mappings = []
    if factgrid_entity:
        console.print(f"Starting sync for {factgrid_entity}")
        mappings = bot.factgrid.get_reverse_item_mapping_for(
            {bot.factgrid.item_prefix.unicode_string() + factgrid_entity},
        )
    elif wd_entity:
        console.print(f"Starting sync for {wd_entity}")
        mappings = bot.factgrid.get_item_mapping_for({bot.wikidata.item_prefix.unicode_string() + wd_entity})
    elif date:
        if date == "today":
            start_date = datetime.date.today()
        elif date == "yesterday":
            start_date = datetime.date.today() - datetime.timedelta(days=1)
        else:
            try:
                start_date = datetime.datetime.fromisoformat(date)
            except ValueError as ex:
                raise typer.Abort() from ex
        mappings = bot.get_missing_wd_to_factgrid_item_reference_for(start_date)
    elif all:
        console.print("Starting sync for all missing entities")
        mappings = bot.get_all_missing_factgrid_items_in_wd()
    else:
        console.print("No valid argument provided")
        raise typer.Abort()
    console.print(f"Starting sync for {len(mappings)} Wikidata entities that are missing the FactGrid ID")
    if not dry_run:
        with Progress() as progress:
            total = len(mappings)
            task = progress.add_task("[green]Adding FactGrid IDs to Wikidata...", total=total)
            failed_syncs = bot.sync_wd_with_factgrid_ids(
                mappings=mappings,
                progress_callback=lambda _: progress.advance(task, 1),
                fix_known_issues=fix_known_issues,
            )
            if failed_syncs:
                console.print(SyncErrorRecord.convert_list_to_table(failed_syncs))
                console.print(
                    f"During the sync {len(failed_syncs)} items failed sync with Wikidata due to the errors listed in the table above",  # noqa: E501
                )
                console.print(
                    "Try to run the sync with the option --fix-known-issues this can reduce the number of errors",
                )
    else:
        console.print("Skipping sync step in dry_run mode")


@app.command()
def init():
    """Set up the authorization for the bot. Must only be executed once."""
    factgrid_auth = wikibase_auth_dialog("FactGrid")
    console.print(factgrid_auth.password)
    wikidata_auth = wikibase_auth_dialog("Wikidata")
    console.print(f"Storing bot credentials at {Bot.AUTH_STORAGE}")
    auth = Authorization(
        factgrid=factgrid_auth,
        wikidata=wikidata_auth,
    )
    Bot.store_auth(auth)


@factgrid_add_app.command()
def family_names(force: Annotated[bool, typer.Option(help="If not set the changes have to be confirmed")] = False):
    """Add Wikidata ID to family names if a family name with the same name exists in Wikidata."""

    def show_mapping_table(mappings):
        table = Table(title="Family Names with missing Wikidata ID in FactGrid and same Name")

        table.add_column(
            "Family Name",
            justify="left",
            style="green",
        )
        table.add_column("Wikidata ID", justify="left", style="cyan", no_wrap=True)
        table.add_column("FactGrid ID", justify="left", style="blue", no_wrap=True)
        for row in mappings:
            table.add_row(*row)
        console.print(table)

    bot = Bot(Bot.load_auth())
    console.print(
        "Querying FactGrid and Wikidata for family names with the same name and missing Wikidata ID in FactGrid",
    )
    label_mappings = bot.get_missing_family_name_mappings()
    console.print(f"There exist {len(label_mappings)} family names in Wikidata with corresponding FactGrid Entry")
    valid_mappings = [
        (family_name, wd_ids[0], factgrid_ids[0])
        for family_name, wd_ids, factgrid_ids in label_mappings
        if len(factgrid_ids) == 1 or len(wd_ids) == 1
    ]
    # TODO add option to show errors
    # mappings_with_errors = [
    #     (family_name, wd_ids, factgrid_ids)
    #     for family_name, wd_ids, factgrid_ids in label_mappings
    #     if len(factgrid_ids) > 1 or len(wd_ids) > 1
    # ]
    console.print(
        f"{len(valid_mappings)} family names can be added to FactGrid. (have no collision with multiple entries)",
    )
    show_table = not force or typer.confirm("Show valid family name mappings?")
    if show_table:
        show_mapping_table(valid_mappings)
    add_wikidata_ids = force or typer.confirm("Are you sure you want to add the Wikidata Id to the FactGrid entities?")
    if add_wikidata_ids:
        with Progress() as progress:
            total = len(valid_mappings)
            task = progress.add_task("[green]Adding Wikidata IDs to FactGrid family names...", total=total)
            fails = bot.add_wikidata_id_to_factgrid_family_name(
                label_mappings=valid_mappings,
                progress_callback=lambda: progress.advance(task, 1),
            )
            if fails:
                show_mapping_table(fails)
                console.print(f"Failed to add Wikidata ID for {len(fails)} FactGrid entities.")
                console.print(
                    "Common issue is that the Wikidata ID is already used by another FactGrid entity most likely a given name which links to a family name. ",  # noqa: E501
                )


def wikibase_auth_dialog(name: str) -> WikibaseAuthorizationConfig | None:
    """Dialog to select a Wikibase authorization configuration.
    :return:
    """
    auth_type = typer.prompt(
        f"Which authorization type to use for {name}?",
        type=click.Choice([auth_method.value for auth_method in WikibaseLoginTypes]),
        show_choices=True,
    )
    match WikibaseLoginTypes(auth_type):
        case WikibaseLoginTypes.OAUTH2:
            return WikibaseOauth2(
                consumer_token=typer.prompt("Consumer Token", type=str),
                consumer_secret=typer.prompt("Consumer secret", type=str),
            )
        case WikibaseLoginTypes.OAUTH1:
            return WikibaseOauth1(
                consumer_token=typer.prompt("Consumer Token", type=str),
                consumer_secret=typer.prompt("Consumer secret", type=str),
                access_token=typer.prompt("Access Token", type=str),
                access_secret=typer.prompt("Access Secret", type=str),
            )
        case WikibaseLoginTypes.BOT:
            return WikibaseBotAuth(
                auth_type=WikibaseLoginTypes.BOT,
                user=typer.prompt("User", type=str),
                password=typer.prompt("Password", type=str),
            )
        case WikibaseLoginTypes.USER:
            return WikibaseUserAuth(
                user=typer.prompt("User", type=str),
                password=typer.prompt("Password", type=str),
            )
        case _:
            raise typer.Abort()
