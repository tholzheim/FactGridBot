import datetime
import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.table import Table

from factgridbot.factgrid import FactGrid
from factgridbot.models.auth import Authorization
from factgridbot.models.error import SyncErrorRecord
from factgridbot.wikidata import Wikidata

logger = logging.getLogger(__name__)


class Bot:
    """Wikibase Bot"""

    AUTH_STORAGE = Path.home() / ".config" / "WikibaseMigrator" / "bot" / "bot_auth.json"

    def __init__(self, auth: Authorization):
        """constructor"""
        self.auth = auth
        self.factgrid = FactGrid(auth_config=self.auth.factgrid)
        self.wikidata = Wikidata(auth_config=self.auth.wikidata)
        self.console = Console()

    @classmethod
    def load_auth(cls) -> Authorization:
        """Load authorization config from file"""
        if cls.AUTH_STORAGE.exists():
            logger.info(f"Loading auth config from {cls.AUTH_STORAGE}")
            auth = Authorization.model_validate_json(cls.AUTH_STORAGE.read_text())
        else:
            logger.info("Authorization config is not defined using default fallback")
            auth = Authorization()
        return auth

    @classmethod
    def store_auth(cls, auth: Authorization) -> None:
        """Store authorization config in file"""
        cls.AUTH_STORAGE.parent.mkdir(exist_ok=True, parents=True)
        cls.AUTH_STORAGE.write_text(auth.model_dump_json(indent=2))

    def validate_property_mappings(self):
        """Validate the property mappings"""
        self.check_duplicates_property_mappings()
        self.check_property_type_mappings()

    def check_duplicates_property_mappings(self):
        """Check if duplicate property mappings exist and if so print them to the console"""
        factgrid_to_wd = self.factgrid.get_prop_mapping_factgrid_to_wikidata()
        wd_to_factgrid = self.factgrid.get_prop_mapping_wikidata_to_factgrid()
        factgrid_to_wd_table = Table(
            title="Property Mappings from FactGrid to Wikidata",
            show_header=True,
            header_style="bold magenta",
        )
        factgrid_to_wd_table.add_column("FactGrid")
        factgrid_to_wd_table.add_column("Count")
        factgrid_to_wd_table.add_column("Wikidata")
        factgrid_labels = self.factgrid.get_entity_label(list(factgrid_to_wd.keys()))
        wd_labels = self.wikidata.get_entity_label(list(wd_to_factgrid.keys()))
        for factgrid_prop, wd_props in factgrid_to_wd.items():
            if len(wd_props) > 1:
                factgrid_to_wd_table.add_row(
                    self._get_rich_url(factgrid_prop, factgrid_labels.get(factgrid_prop)),
                    str(len(wd_props)),
                    ", ".join([self._get_rich_url(wd_prop, wd_labels.get(wd_prop)) for wd_prop in wd_props]),
                )
        self.console.print(factgrid_to_wd_table)

        wd_to_factgrid_table = Table(
            title="Property Mappings from Wikidata to FactGrid",
            show_header=True,
            header_style="bold magenta",
        )
        wd_to_factgrid_table.add_column("Wikidata")
        wd_to_factgrid_table.add_column("Count")
        wd_to_factgrid_table.add_column("FactGrid")
        for wd_prop, factgrid_props in wd_to_factgrid.items():
            if len(factgrid_props) > 1:
                wd_to_factgrid_table.add_row(
                    self._get_rich_url(wd_prop, wd_labels.get(wd_prop)),
                    str(len(factgrid_props)),
                    ", ".join(
                        [
                            self._get_rich_url(factgrid_prop, factgrid_labels.get(factgrid_prop))
                            for factgrid_prop in factgrid_props
                        ],
                    ),
                )
        self.console.print(wd_to_factgrid_table)

    def _get_rich_url(self, entity_url: str, label: str) -> str:
        """Get rich url str
        :param entity_url:
        :param label:
        :return:
        """
        qid = entity_url.split("/")[-1]
        return f"[link={entity_url}]{label} ({qid})[/link]"

    def check_property_type_mappings(self):
        mappings = self.factgrid.get_prop_mappings()
        factgrid_labels = self.factgrid.get_entity_label([factgrid_prop for (wd_prop, factgrid_prop) in mappings])
        wd_labels = self.wikidata.get_entity_label([wd_prop for (wd_prop, factgrid_prop) in mappings])
        wd_types = self.wikidata.get_property_types_of({wd_prop for (wd_prop, factgrid_prop) in mappings})
        factgrid_types = self.factgrid.get_property_types_of({factgrid_prop for (wd_prop, factgrid_prop) in mappings})
        table = Table(
            title="Property Mappings with different Dataypes",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Wikidata")
        table.add_column("Wikidata Datatype")
        table.add_column("FactGrid Datatype")
        table.add_column("FactGrid")
        for wd_prop, factgrid_prop in mappings:
            if factgrid_types.get(factgrid_prop) != wd_types.get(wd_prop):
                table.add_row(
                    self._get_rich_url(wd_prop, wd_labels.get(wd_prop)),
                    wd_types.get(wd_prop),
                    factgrid_types.get(factgrid_prop),
                    self._get_rich_url(factgrid_prop, factgrid_labels.get(factgrid_prop)),
                )
        self.console.print(table)

    def get_all_missing_factgrid_items_in_wd(self) -> list[tuple[str, str]]:
        """Get all the wikidata items that are linked in FactGrid but not in Wikidata
        :return: List of tuples. first tuple item is the wikidata item second is the corresponding factgrid id
        """
        logger.info("Query all Wikidata item references in FactGrid")
        wd_references_wiki = self.factgrid.get_all_referenced_wikidata_items()
        wd_wiki_prefix = "https://www.wikidata.org/wiki/"
        wd_item_prefix = self.wikidata.item_prefix.unicode_string()
        wd_referenced_entities = {wd_item_prefix + wd_id.removeprefix(wd_wiki_prefix) for wd_id in wd_references_wiki}
        logger.info("Retrieving all Wikidata items with missing FactGrid reference")
        wd_missing_ref = self.wikidata.retrieve_missing_factgrid_reference(wd_referenced_entities)
        logger.info("Query FactGrid for the mapping between Wikidata and FactGrid")
        missing_wd_ref_mapping = self.factgrid.get_item_mapping_for(wd_missing_ref)
        return missing_wd_ref_mapping

    def get_missing_wd_to_factgrid_item_reference_for(
        self,
        date: datetime.date | datetime.datetime,
    ) -> list[tuple[str, str]]:
        """Get misssing Wikidata item references for the items that were modified on the given date
        :param date:
        :return:
        """
        logger.info(f"Querying entities that were modified at {date}")
        modified_entities = self.factgrid.get_items_modified_at(start_date=date)
        logger.info(f"{len(modified_entities)} were modified at the {date}")
        logger.info("Querying Wikidata mapping for edited entities")
        wd_to_factgrid_map = self.factgrid.get_reverse_item_mapping_for(modified_entities)
        referenced_wd_entities = {wd_id for wd_id, _ in wd_to_factgrid_map}
        logger.info(f"{len(referenced_wd_entities)} entities were linked to Wikidata")
        wd_missing_ref = self.wikidata.retrieve_missing_factgrid_reference(referenced_wd_entities)
        logger.info(f"{len(wd_missing_ref)} Wikidata entities are missing the FactGrid ID")
        return [(wd_id, factgrid_id) for wd_id, factgrid_id in wd_to_factgrid_map if wd_id in wd_missing_ref]

    def sync_wd_with_factgrid_ids(
        self,
        mappings: list[tuple[str, str]],
        progress_callback: Callable[[None], None] | None = None,
        fix_known_issues: bool = False,
        max_retries: int | None = None,
    ) -> list[SyncErrorRecord]:
        """Sync Wikidata with FactGrid by adding the FactGrid ids to the corresponding Wikidata entities
        :param fix_known_issues:
        :param progress_callback:
        :param mappings:
        :return:
        """
        failed = []
        # needs bot access to increase worker count
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = []
            for wd_id, factgrid_id in mappings:
                future = executor.submit(
                    self._sync_wd_with_factgrid_id,
                    wd_id=wd_id,
                    factgrid_id=factgrid_id,
                    fix_known_issues=fix_known_issues,
                    max_retries=max_retries,
                )
                futures.append(future)
                if progress_callback:
                    future.add_done_callback(progress_callback)  # type: ignore
            for future in as_completed(futures):
                result = future.result()
                if isinstance(result, SyncErrorRecord):
                    failed.append(result)
                    logger.debug(f"Failed to add {factgrid_id} to {wd_id}")
                    logger.error(result.error_message)
                else:
                    logger.debug(f"Added {factgrid_id} to {wd_id}")
        return failed

    def _sync_wd_with_factgrid_id(
        self,
        wd_id: str,
        factgrid_id: str,
        fix_known_issues: bool = False,
        max_retries: int | None = None,
    ) -> SyncErrorRecord | None:
        """:param wd_id:
        :param factgrid_id:
        :return:
        """
        result = None
        if not (factgrid_id and wd_id):
            result = SyncErrorRecord(
                wd_id=wd_id,
                factgrid_id=factgrid_id,
                error_message=f"Mapping error both ids bust be defined Wikidata:{wd_id} FactGrid:{factgrid_id}",
            )
        else:
            wd_item = self.wikidata.get_item(wd_id)
            self.wikidata.add_factgrid_id(wd_item, self.factgrid.get_entity_id(factgrid_id))
            try:
                self.wikidata.write_item(
                    wd_item,
                    summary="adds FactGrid ID",
                    fix_known_issues=fix_known_issues,
                    max_retries=max_retries,
                )
            except Exception as ex:
                result = SyncErrorRecord(wd_id=wd_id, factgrid_id=factgrid_id, error_message=str(ex))
        return result

    def get_label_matches_by_entity_class(
        self,
        factgrid_entity_class_id: str,
        wikidata_entity_class_id: str,
        language: str = "en",
    ) -> list[tuple[str, list[str], list[str]]]:
        """Get the entities from Wikidata and FactGrid that share the same label given the corresponding entity class
        Only FactGrid entities with missing wikidata id are included
        :param factgrid_entity_class_id: id of the entity class in FactGrid
        :param wikidata_entity_class_id: id of the entity class in Wikidata
        :param language: language of the label to match
        :return: List of tuples.
            Each tuple contains:
                the label,
                list of FactGrid entities with the label and,
                list of Wikidata entities with the label
        """
        if language is None:
            language = "en"
        factgrid_ids = self.factgrid.get_entities_with_missing_wikidata_id(
            entity_class_id=factgrid_entity_class_id,
        )  # Family Name
        factgrid_family_labels_map = self.factgrid.get_entity_label(entity_ids=list(factgrid_ids), language=language)
        wikidata_family_labels_map = self.wikidata.get_entities_by_labels(
            language=language,
            labels=set(factgrid_family_labels_map.values()),
            entity_class_id=wikidata_entity_class_id,
        )
        label_to_fact_grid = defaultdict(list)
        for qid, label in factgrid_family_labels_map.items():
            label_to_fact_grid[label].append(qid)
        label_to_wd = defaultdict(list)
        for wd_id, label in wikidata_family_labels_map:
            label_to_wd[label].append(wd_id)
        result = []
        for label, wd_ids in label_to_wd.items():
            fact_grid_ids = label_to_fact_grid.get(label, [])
            if fact_grid_ids:
                result.append((label, wd_ids, fact_grid_ids))
        return result

    def get_missing_family_name_mappings(self) -> list[tuple[str, list[str], list[str]]]:
        """Get mappings from label to FactGrid and Wikidata ids
        :return:
        """
        return self.get_label_matches_by_entity_class("Q24499", "Q101352", "en")

    def add_wikidata_id_to_factgrid_family_name(
        self,
        label_mappings: list[tuple[str, str, str]],
        progress_callback: Callable[[], None] | None = None,
    ):
        """Add missing family names to FactGrid"""
        fails = []
        for label, wikidata_id, factgrid_id in label_mappings:
            try:
                fact_grid_item = self.factgrid.get_item(factgrid_id)
                self.factgrid.add_wikidata_id_to(fact_grid_item, self.wikidata.get_entity_id(wikidata_id))
                self.factgrid.write_item(fact_grid_item, summary="adds Wikidata ID")
                logger.info(f"Added {wikidata_id} to {factgrid_id}")
            except Exception as ex:
                logger.error(f"Failed to add Wikidata id {wikidata_id} to FactGrid entity {factgrid_id}: {ex}")
                fails.append((label, factgrid_id, wikidata_id))
            if progress_callback:
                progress_callback()
        return fails
