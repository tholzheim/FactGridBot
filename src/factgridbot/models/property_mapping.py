from pydantic import BaseModel, HttpUrl


class WikibaseProperty(BaseModel):
    """
    Wikibase property
    """

    property_id: HttpUrl
    property_type: HttpUrl | None = None
    label: str | None = None


class PropertyMapping(BaseModel):
    factgrid: WikibaseProperty
    wikidata: WikibaseProperty

    def have_same_datatype(self) -> bool:
        """
        Check if property has same datatype
        :return:
        """
        return self.factgrid.property_type == self.wikidata.property_type
