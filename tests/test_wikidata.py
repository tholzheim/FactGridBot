import unittest
from unittest import skipIf

from factgridbot.wikidata import Wikidata
from tests.basetest import IN_GITHUB_ACTIONS


class TestWikidata(unittest.TestCase):
    """test Wikidata class"""

    @skipIf(IN_GITHUB_ACTIONS, "Test queries Wikidata")
    def test_add_factgrid_id(self):
        """
        Test adding factgrid id
        """
        wikidata = Wikidata()
        item = wikidata.get_item("Q110634087")
        factgrid_id = "Q998314"
        self.assertTrue(item.claims.get(wikidata.FACTGRID_ITEM_ID))
        del item.claims.claims[wikidata.FACTGRID_ITEM_ID]
        self.assertFalse(item.claims.get(wikidata.FACTGRID_ITEM_ID))
        wikidata.add_factgrid_id(item, factgrid_id)
        claims = item.claims.get(wikidata.FACTGRID_ITEM_ID)
        self.assertTrue(claims)
        self.assertEqual(len(claims[0].references.references[0]), 2)
