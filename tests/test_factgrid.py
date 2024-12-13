import datetime
import unittest

from factgridsyncwdbot.factgrid import FactGrid


class TestFactGrid(unittest.TestCase):
    """
    tests FactGrid
    """

    def test_get_all_referenced_wikidata_items(self):
        """
        tests get_all_referenced_wikidata_items
        """
        factgrid = FactGrid()
        wd_items = factgrid.get_all_referenced_wikidata_items()
        self.assertGreaterEqual(len(wd_items), 449000)

    def test_get_item(self):
        """
        tests get_item
        """
        factgrid = FactGrid()
        q7 = factgrid.get_item("Q7")
        self.assertEqual(q7.labels.get("en"), "Human")

    def test_get_items_modified_at(self):
        """
        tests get_items_modified_at
        """
        factgrid = FactGrid()
        item_ids = factgrid.get_items_modified_at(datetime.date.today())
        self.assertGreaterEqual(len(item_ids), 1)
