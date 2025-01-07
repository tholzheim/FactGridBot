from string import Template

from wikibaseintegrator.entities import ItemEntity

from factgridbot.models.auth import WikibaseAuthorizationConfig
from factgridbot.wikibase import Wikibase


class FactGrid(Wikibase):
    """FactGrid Wikibase instance"""

    def __init__(self, auth_config: WikibaseAuthorizationConfig | None = None):
        super().__init__(
            sparql_endpoint="https://database.factgrid.de/sparql",
            website="https://database.factgrid.de",
            item_prefix="https://database.factgrid.de/entity/",
            property_prefix="https://database.factgrid.de/prop/direct/",
            mediawiki_api_url="https://database.factgrid.de/w/api.php",
            auth_config=auth_config,
        )

    def get_all_properties_linked_to_wikidata(self) -> set[str]:
        """Get all properties from FactGrid that are linked to Wikidata"""
        query = """
        SELECT ?property {

            ?property rdf:type wikibase:Property.
            ?property wdt:P343 ?wd_id.
        }
        """
        lod = self.execute_query(query, endpoint_url=self.sparql_endpoint)
        property_ids: set[str] = {d.get("property", "") for d in lod if isinstance(d.get("property"), str)}
        return property_ids

    def get_prop_mapping_factgrid_to_wikidata(self) -> dict[str, list[str]]:
        """Get all properties from FactGrid that are linked to Wikidata"""
        query = """
        SELECT ?factgrid_prop (COUNT(?wd_prop) as ?count) (GROUP_CONCAT(?wd_prop; SEPARATOR="|") as ?ids) WHERE {
          ?factgrid_prop rdf:type wikibase:Property;
            wdt:P343 ?wd_id.
          BIND(IRI(CONCAT("http://www.wikidata.org/entity/", ?wd_id)) as ?wd_prop)
        }
        GROUP BY ?factgrid_prop
        """
        lod = self.execute_query(query, endpoint_url=self.sparql_endpoint)
        mapping = {
            d.get("factgrid_prop", ""): d.get("ids", "").split("|")
            for d in lod
            if isinstance(d.get("factgrid_prop"), str) and isinstance(d.get("ids"), str)
        }
        return mapping

    def get_prop_mapping_wikidata_to_factgrid(self) -> dict[str, list[str]]:
        """Get the property mapping from wikidata property to factgrid property
        :return:
        """
        query = """
        SELECT ?wd_prop (COUNT(?factgrid_prop) as ?count) (GROUP_CONCAT(?factgrid_prop; SEPARATOR="|") as ?ids) WHERE {
          ?factgrid_prop rdf:type wikibase:Property;
            wdt:P343 ?wd_id.
          BIND(IRI(CONCAT("http://www.wikidata.org/entity/", ?wd_id)) as ?wd_prop)
        }
        GROUP BY ?wd_prop
        """
        lod = self.execute_query(query, endpoint_url=self.sparql_endpoint)
        mapping = {
            d.get("wd_prop", ""): d.get("ids", "").split("|")
            for d in lod
            if isinstance(d.get("wd_prop"), str) and isinstance(d.get("ids"), str)
        }
        return mapping

    def get_prop_mappings(self) -> list[tuple[str, str]]:
        """Get plain property mappings from wikidata to factgrid property as list of tuples"""
        query = """
        SELECT ?wd_prop ?factgrid_prop WHERE {
          ?factgrid_prop rdf:type wikibase:Property;
            wdt:P343 ?wd_id.
          BIND(IRI(CONCAT("http://www.wikidata.org/entity/", ?wd_id)) as ?wd_prop)
        }
        """
        lod = self.execute_query(query, endpoint_url=self.sparql_endpoint)
        return [
            (d.get("wd_prop", ""), d.get("factgrid_prop", ""))
            for d in lod
            if isinstance(d.get("wd_prop"), str) and isinstance(d.get("factgrid_prop"), str)
        ]

    def get_item_mapping_for(self, wd_item_ids: set[str]) -> list[tuple[str, str]]:
        """Get mapping from wikidata to factgrid item
        :param wd_item_ids:
        :return:
        """
        query = Template("""
        PREFIX schema: <http://schema.org/>
        SELECT ?wd_qid ?factgrid_item
        WHERE{
    
          VALUES ?wd_qid {
            $source_entities
          }
          ?wd_qid schema:isPartOf <https://www.wikidata.org/>.
          ?wd_qid schema:about ?factgrid_item.
        }
        """)
        values = [f"<{self.get_wikidata_sitelink_from_entity_id(wd_item)}>" for wd_item in wd_item_ids]
        lod = self.execute_values_query_in_chunks(
            query_template=query,
            param_name="source_entities",
            values=values,
            endpoint_url=self.sparql_endpoint,
        )
        return [(self.get_wikidata_entity_id_from_sitelink(d.get("wd_qid")), d.get("factgrid_item")) for d in lod]

    def get_reverse_item_mapping_for(self, factgrid_item_ids: set[str]) -> list[tuple[str, str]]:
        """Get mapping from wikidata to factgrid item for the given set of factgrid items
        :param wd_item_ids:
        :return:
        """
        query = Template("""
        PREFIX schema: <http://schema.org/>
        SELECT ?wd_qid ?factgrid_item
        WHERE{

          VALUES ?factgrid_item {
            $source_entities
          }
          ?wd_qid schema:isPartOf <https://www.wikidata.org/>.
          ?wd_qid schema:about ?factgrid_item.
        }
        """)
        values = [f"<{factgrid_item}>" for factgrid_item in factgrid_item_ids]
        lod = self.execute_values_query_in_chunks(
            query_template=query,
            param_name="source_entities",
            values=values,
            endpoint_url=self.sparql_endpoint,
        )
        return [(self.get_wikidata_entity_id_from_sitelink(d.get("wd_qid")), d.get("factgrid_item")) for d in lod]

    def get_all_referenced_wikidata_items(self) -> set[str]:
        """Get all referenced wikidata items"""
        query = """
        PREFIX schema: <http://schema.org/>
        SELECT DISTINCT ?wd_qid 
        WHERE { ?wd_qid schema:isPartOf <https://www.wikidata.org/>. }
        """
        lod = self.execute_query(query, endpoint_url=self.sparql_endpoint)
        return {d.get("wd_qid", "") for d in lod if isinstance(d.get("wd_qid"), str)}

    def get_wikidata_entity_id_from_sitelink(self, sitelink_url: str) -> str:
        """Get wikidata entity id from sitelink
        :param sitelink_url:
        :return:
        """
        item_prefix = "http://www.wikidata.org/entity/"
        wiki_page_prefix = "https://www.wikidata.org/wiki/"
        return sitelink_url.replace(wiki_page_prefix, item_prefix)

    def get_wikidata_sitelink_from_entity_id(self, entity_id: str) -> str:
        """Get wikidata sitelink from entity id
        :param entity_id:
        :return:
        """
        item_prefix = "http://www.wikidata.org/entity/"
        wiki_page_prefix = "https://www.wikidata.org/wiki/"
        return entity_id.replace(item_prefix, wiki_page_prefix)

    def get_entities_with_missing_wikidata_id(self, entity_class_id: str) -> set[str]:
        """:param entity_class_id:
        :return:
        """
        query_template = Template("""
        SELECT ?item
        WHERE{
          ?item wdt:P2 wd:$entity_class_id.
          MINUS{
            ?wd_qid schema:isPartOf <https://www.wikidata.org/>.
            ?wd_qid schema:about ?item.
          }
        }
        """)
        query = query_template.substitute(entity_class_id=self.get_entity_id(entity_class_id))
        lod = self.execute_query(
            query=query,
            endpoint_url=self.sparql_endpoint,
        )
        return {d.get("item", "") for d in lod if isinstance(d.get("item", None), str)}

    def add_wikidata_id_to(self, factgrid_entity: ItemEntity, wikidata_entity_id: str):
        """Add wikidata id as sitelink to the given FactGrid entity id
        :param factgrid_entity:
        :param wikidata_entity_id:
        :return:
        """
        factgrid_entity.sitelinks.set(site="wikidatawiki", title=wikidata_entity_id)


if __name__ == "__main__":
    fact_grid = FactGrid()
    property_ids = fact_grid.get_all_properties_linked_to_wikidata()
    prop_types = fact_grid.get_property_types_of(property_ids)
    print(prop_types)
