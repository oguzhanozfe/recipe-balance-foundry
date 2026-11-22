import json
from pathlib import Path
import unittest

from pipeline import prepare, export


def fixture():
    return json.loads(
        Path(__file__).with_name("example.json").read_text(encoding="utf-8")
    )


class PipelineTests(unittest.TestCase):
    def test_shared_demand_aggregates_before_rounding(self):
        r = prepare(fixture())
        by = {x["item"]: x for x in r["records"]}
        self.assertEqual(by["hinge"]["demand_units"], 5)
        self.assertEqual(by["hinge"]["batches"], 2)
        self.assertEqual(by["ingot"]["demand_units"], 6)
        self.assertEqual(by["ore"]["raw_to_buy"], 9)
        self.assertEqual(by["hinge"]["unit_cost_exact"], "6")

    def test_selective_price_export(self):
        import csv, io

        d = fixture()
        r = prepare(d)
        pick = next(c for c in r["candidates"] if c["item"] == "ingot")
        out = list(
            csv.DictReader(io.StringIO(export(d, r, [pick])["economy-prices.csv"]))
        )
        prices = {v["item"]: v for v in out}
        self.assertEqual(prices["ingot"]["approved_sell_price"], "11")
        self.assertEqual(prices["toolbox"]["approved_sell_price"], "15")

    def test_cycle_and_unknown_ingredient(self):
        d = fixture()
        d["items"][2]["recipe"][0]["item"] = "toolbox"
        with self.assertRaisesRegex(ValueError, "cycle"):
            prepare(d)
        d["items"][2]["recipe"][0]["item"] = "void"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            prepare(d)

    def test_fractional_unit_cost_exact(self):
        d = fixture()
        d["items"][2]["batch_fee"] = 0
        r = prepare(d)
        self.assertEqual(
            next(x for x in r["records"] if x["item"] == "ingot")["unit_cost_exact"],
            "15/2",
        )


if __name__ == "__main__":
    unittest.main()
