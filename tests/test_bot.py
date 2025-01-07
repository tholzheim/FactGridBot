import csv
import logging
import unittest

from factgridbot.bot import Bot


class TestBot(unittest.TestCase):
    """test Bot"""

    @unittest.skip("Only for manual validation")
    def test_get_missing_factgrid_items_in_wd(self):
        """Tests get_missing_factgrid_items_in_wd"""
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logging.basicConfig()
        bot = Bot(Bot.load_auth())
        missing_ref_items = bot.get_all_missing_factgrid_items_in_wd()
        # missing_ref_items = [
        #     (
        #         "http://www.wikidata.org/entity/Q5",
        #         "https://database.factgrid.de/entity/Q7",
        #     )
        # ]
        print(len(missing_ref_items))
        factgrid_ids = {factgrid_id for _, factgrid_id in missing_ref_items}
        wd_ids = {wikidata_id for wikidata_id, _ in missing_ref_items}
        factgrid_labels = bot.factgrid.get_entity_label(entity_ids=factgrid_ids)
        wd_labels = bot.wikidata.get_entity_label(entity_ids=wd_ids)
        with open("/tmp/factgrid_mappings.csv", "w", newline="") as csvfile:
            fieldnames = [
                "wd_id",
                "wd_label",
                "wd_url",
                "factgrid_id",
                "factgrid_label",
                "factgrid_url",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for wd_id, factgrid_id in missing_ref_items:
                writer.writerow(
                    {
                        "wd_id": wd_id,
                        "wd_label": wd_labels.get(wd_id, None),
                        "factgrid_id": factgrid_id,
                        "factgrid_label": factgrid_labels.get(factgrid_id, None),
                    },
                )
        # on manual overview and validation of a few all the mappings are correct and can be applied
