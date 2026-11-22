"""Audit an acyclic crafting economy using exact rational unit costs."""

from collections import defaultdict
from fractions import Fraction
import csv
import io
import math
import re

TITLE = "Recipe Balance Foundry"
DESCRIPTION = "Expand crafting recipes into raw costs and batch requirements, then export approved sell-price adjustments."
PROMPT = "Explain item costs and the raw inputs driving each adjustment. Distinguish normalized long-run unit cost from the whole-batch procurement run. Do not claim real player demand."


def rows(data, key, limit=250, empty=False):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list) or len(value) > limit or (not value and not empty):
        raise ValueError(
            f"{key} must be a list with {'0' if empty else '1'} to {limit} entries"
        )
    if any(not isinstance(entry, dict) for entry in value):
        raise ValueError(f"Every {key} entry must be an object")
    return value


def text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank text, at most {limit} characters")
    return value.strip()


def integer(value, name, lo=0, hi=1_000_000):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer between {lo} and {hi}")
    return value


def selected(evidence, approved):
    by_id = {c["id"]: c for c in evidence["candidates"]}
    result = []
    seen = set()
    for item in approved:
        key = item.get("id") if isinstance(item, dict) else None
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise ValueError("Unknown or duplicate approval")
        seen.add(key)
        result.append(by_id[key])
    return result


def prepare(data: dict) -> dict:
    catalog = {}
    inputs = {}
    records = []
    memo = {}
    path = []
    margin = (
        integer(data.get("margin_percent", 25), "margin_percent", 0, 95)
        if isinstance(data, dict)
        else 25
    )
    for item in rows(data, "items", 100):
        key = text(item.get("id"), "item id", 60)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key) or key in catalog:
            raise ValueError("Use unique ASCII item IDs")
        price = integer(item.get("sell_price"), "sell_price", 0, 1_000_000_000)
        has_raw = "raw_cost" in item
        has_recipe = "recipe" in item
        if has_raw == has_recipe:
            raise ValueError("Choose raw_cost or recipe for each item")
        if has_raw:
            raw = integer(item["raw_cost"], "raw_cost", 0, 1_000_000)
            catalog[key] = (price, raw, 1, 0)
            inputs[key] = {}
        else:
            out = integer(item.get("batch_yield", 1), "batch_yield", 1, 100)
            fee = integer(item.get("batch_fee", 0), "batch_fee", 0, 1_000_000)
            parts = {}
            for part in rows(item, "recipe", 30):
                child = text(part.get("item"), "ingredient id", 60)
                if child in parts:
                    raise ValueError("Aggregate each ingredient into one recipe row")
                parts[child] = integer(part.get("quantity"), "quantity", 1, 1000)
            catalog[key] = (price, None, out, fee)
            inputs[key] = parts

    def expand(key):
        if key not in catalog:
            raise ValueError("Unknown ingredient: " + key)
        if key in path:
            raise ValueError("Craft cycle: " + " -> ".join(path + [key]))
        if key in memo:
            return memo[key]
        _, raw, yield_, fee = catalog[key]
        if raw is not None:
            memo[key] = (Fraction(raw), {key: Fraction(1)}, 0)
        else:
            path.append(key)
            cost = Fraction(fee, yield_)
            leaves = defaultdict(Fraction)
            depth = 0
            for child, qty in inputs[key].items():
                child_cost, child_bom, child_depth = expand(child)
                scale = Fraction(qty, yield_)
                cost += scale * child_cost
                depth = max(depth, child_depth + 1)
                for base, amount in child_bom.items():
                    leaves[base] += scale * amount
            path.pop()
            memo[key] = (cost, dict(leaves), depth)
        return memo[key]

    for key in catalog:
        expand(key)
    demand = defaultdict(int)
    for req in rows(data, "order", 100, empty=True):
        key = text(req.get("item"), "order item")
        if key not in catalog:
            raise ValueError("Unknown order item: " + key)
        demand[key] += integer(req.get("quantity"), "order quantity", 1, 100_000)
    candidates = []
    for key in sorted(catalog, key=lambda k: (-memo[k][2], k)):
        price, raw, yield_, fee = catalog[key]
        cost, leaves, depth = memo[key]
        wanted = demand[key]
        batches = (wanted + yield_ - 1) // yield_ if raw is None else 0
        for child, qty in inputs[key].items():
            demand[child] += batches * qty
        minimum = math.ceil(cost * 100 / (100 - margin))
        biggest = max(sorted(leaves), key=lambda k: leaves[k] * catalog[k][1])
        rec = {
            "id": "item:" + key,
            "item": key,
            "unit_cost_exact": str(cost),
            "sell_price": price,
            "price_floor": minimum,
            "craft_depth": depth,
            "largest_raw_cost_driver": biggest,
            "raw_units_per_item": {k: str(v) for k, v in sorted(leaves.items())},
            "demand_units": wanted,
            "batches": batches,
            "surplus": batches * yield_ - wanted if raw is None else 0,
            "raw_to_buy": wanted if raw is not None else 0,
        }
        records.append(rec)
        if raw is None and price < minimum:
            candidates.append(
                {
                    "id": "price:" + key,
                    "action": f"Raise {key} from {price} to {minimum} coins",
                    "evidence_ids": ["item:" + key]
                    + ["item:" + i for i in sorted(inputs[key])],
                    "item": key,
                    "new_price": minimum,
                }
            )
    return {
        "summary": f"{len(candidates)} crafted items fall below the configured {margin}% gross margin.",
        "metrics": {
            "Items": len(catalog),
            "Price proposals": len(candidates),
            "Target margin (%)": margin,
        },
        "records": records,
        "candidates": candidates,
    }


def export(data, evidence, approved):
    changes = {p["item"]: p["new_price"] for p in selected(evidence, approved)}
    prices = io.StringIO(newline="")
    order = io.StringIO(newline="")
    w = csv.writer(prices)
    o = csv.writer(order)
    w.writerow(
        ["item", "previous_sell_price", "approved_sell_price", "normalized_cost_exact"]
    )
    o.writerow(
        ["item", "required_units", "craft_batches", "batch_surplus", "raw_to_buy"]
    )
    for r in evidence["records"]:
        w.writerow(
            [
                r["item"],
                r["sell_price"],
                changes.get(r["item"], r["sell_price"]),
                r["unit_cost_exact"],
            ]
        )
        if r["demand_units"]:
            o.writerow(
                [
                    r[k]
                    for k in (
                        "item",
                        "demand_units",
                        "batches",
                        "surplus",
                        "raw_to_buy",
                    )
                ]
            )
    return {
        "economy-prices.csv": prices.getvalue(),
        "production-order.csv": order.getvalue(),
    }
