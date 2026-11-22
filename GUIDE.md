# Crafting economy review

A designer prices individual items, but crafting often operates in batches. This workflow exposes both views. Raw items declare a purchase cost. Crafted items declare ingredients, quantities, a batch yield and a per-batch fee. All prices are in whole coins. The example shares ingots between hinges and toolboxes.

The dependency resolver rejects missing ingredients and cycles, expands every recipe into exact rational raw units and propagates fees through intermediate products. It reports the raw ingredient contributing the most cost. For the production order it processes finished goods before ingredients, aggregates demand shared by multiple recipes, and rounds up to whole batches only after that aggregation. The resulting sheet exposes surplus and required raw purchases. No initial inventory or sale of surplus is assumed.

The gross-margin floor is unit cost divided by one minus the target margin, rounded up. Approve price proposals individually to export `economy-prices.csv`. The independent `production-order.csv` lists required batches and purchases. Prices are planning suggestions for a single-recipe economy without player trading, alternate recipes or dynamic market prices.
