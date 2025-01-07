import logging
from string import Template

from wikibaseintegrator import datatypes
from wikibaseintegrator.entities import ItemEntity, PropertyEntity
from wikibaseintegrator.models import Reference, References

from factgridbot.models.auth import WikibaseAuthorizationConfig
from factgridbot.wikibase import Wikibase

logger = logging.getLogger(__name__)


class Wikidata(Wikibase):
    """Wikidata Wikibase instance"""

    FACTGRID_ITEM_ID: str = "P8168"
    FACTGRID_PROPERTY_ID: str = "P10787"

    def __init__(self, auth_config: WikibaseAuthorizationConfig | None = None):
        super().__init__(
            sparql_endpoint="https://query.wikidata.org/sparql",
            website="https://wikidata.org",
            item_prefix="http://www.wikidata.org/entity/",
            property_prefix="http://www.wikidata.org//prop/direct/",
            mediawiki_api_url="https://www.wikidata.org/w/api.php",
            auth_config=auth_config,
        )

    def retrieve_missing_factgrid_reference(self, item_ids: set[str]) -> set[str]:
        """Retrieve the wikidata item IDs for which the factGrid link ( FactGrid item ID (P8168) ) is missing
        :param item_ids:
        :return:
        """
        query_template = Template("""
        SELECT DISTINCT ?wd_id
        WHERE{
          VALUES ?wd_id {
            $wd_ids
          }
          ?wd_id schema:version ?version.
          MINUS{?wd_id wdt:P8168 ?factgrid_id.}
        }
        """)
        values = [f"<{entity_id}>" for entity_id in item_ids]
        lod = self.execute_values_query_in_chunks(
            query_template=query_template,
            param_name="wd_ids",
            values=values,
            endpoint_url=self.sparql_endpoint,
            chunk_size=15000,
        )
        return {d.get("wd_id") for d in lod}

    def add_factgrid_id(self, entity: ItemEntity | PropertyEntity, factgrid_id: str):
        """Add the given FactGrid ID to the wikidata item
        if the factgrid id already exists do nothing
        if a different factgrid id exists raise an error
        :param entity:
        :param factgrid_id:
        :return:
        """
        if factgrid_id is None:
            logger.debug("No factgrid id provided")
            return
        property_id = None
        if isinstance(entity, ItemEntity):
            property_id = self.FACTGRID_ITEM_ID
        elif isinstance(entity, PropertyEntity):
            property_id = self.FACTGRID_PROPERTY_ID
        else:
            logger.debug("unsupported entity type {type(entity)}! No property defined for this type")
            return
        claims = entity.claims.get(property_id)
        if claims:
            logger.debug("FactGrid property {property_id} already exists for entity {entity_id}")
            # check if duplicate or if different
            if len(claims) > 1:
                logger.debug(f"Wikidata entity {entity.id} has multiple claims for property {property_id}")
            else:
                claim = claims[0]
                value = claim.mainsnak.datavalue.get("value")
                if value == factgrid_id:
                    pass
                elif value is None:
                    logger.info(f"FactGrid property {property_id} has no value for entity {entity.id}")
                else:
                    logger.debug(
                        f"Wikidata entity {entity.id} is linked to a different FactGrid entity {value} != {factgrid_id}",  # noqa: E501
                    )
        else:
            references = References()
            reference = Reference()
            reference.add(datatypes.Item(prop_nr="P248", value="Q90405608"))  # stated in FactGrid
            reference.add(datatypes.Time(prop_nr="P813", time="now"))  # retrieved now
            references.add(reference)
            new_claim = datatypes.ExternalID(prop_nr=property_id, value=factgrid_id, references=references)
            entity.add_claims(new_claim)

    def get_entities_by_labels(self, labels: set[str], language: str, entity_class_id: str) -> list[tuple[str, str]]:
        """Get entity that have on of the labels of the given set
        :param language:
        :param entity_class_id:
        :param labels:
        :return:
        """
        query_template = Template("""
        SELECT DISTINCT ?item ?label
        WHERE{
            VALUES ?label{
                $labels
            }
            ?item rdfs:label ?label.
            ?item wdt:P31 wd:$entity_class_id
        }
        """)
        query = Template(query_template.safe_substitute(entity_class_id=self.get_entity_id(entity_class_id)))
        string_template = Template('"$class_id"@$lang')
        values = [
            string_template.safe_substitute(class_id=entity_class_id.replace('"', r"\""), lang=language)
            for entity_class_id in labels
        ]
        lod = self.execute_values_query_in_chunks(
            query_template=query,
            param_name="labels",
            values=values,
            endpoint_url=self.sparql_endpoint,
            chunk_size=3000,
        )
        return [(d.get("item"), d.get("label")) for d in lod]
