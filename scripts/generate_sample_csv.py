import csv
import os
from datetime import date
from dateutil.relativedelta import relativedelta
import random

# Configuration
NUM_CUSTOMERS = 1000
PRODUCTS = [
	{"product_id": "A", "base_price": 10.0, "elasticity": -0.8},
	{"product_id": "B", "base_price": 20.0, "elasticity": -0.6},
	{"product_id": "C", "base_price": 40.0, "elasticity": -0.4},
]
START_YEARS_AGO = 10
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "sample_transactions.csv")

random.seed(42)


def month_range(start: date, months: int):
	current = start
	for _ in range(months):
		yield current
		current = current + relativedelta(months=1)


def main():
	os.makedirs(OUTPUT_DIR, exist_ok=True)

	end = date.today().replace(day=1)
	start = end - relativedelta(years=START_YEARS_AGO)
	months = (end.year - start.year) * 12 + (end.month - start.month)

	customers = [f"C{str(i).zfill(4)}" for i in range(1, NUM_CUSTOMERS + 1)]

	rows = []
	for month_start in month_range(start, months):
		# Simple seasonality: higher in Nov/Dec
		season = 1.0
		if month_start.month in (11, 12):
			season = 1.25
		elif month_start.month in (6, 7):
			season = 0.95

		for customer_id in customers:
			# Each customer has an activity propensity
			activity = 0.4 + random.random() * 0.4  # 0.4 - 0.8
			if random.random() > activity:
				continue

			# For each active customer, buy 1-3 products probabilistically
			for prod in PRODUCTS:
				if random.random() < 0.5:
					continue
				base_qty = 1 + int(random.random() * 3)
				# introduce randomness and seasonality
				quantity = max(1, int(round(base_qty * season * (0.7 + random.random() * 0.6))))
				# small price noise over time
				price = round(prod["base_price"] * (0.9 + random.random() * 0.2), 2)
				rows.append({
					"customer_id": customer_id,
					"date": month_start.strftime("%Y-%m-%d"),
					"product_id": prod["product_id"],
					"quantity": quantity,
					"price": price,
				})

	with open(OUTPUT_PATH, "w", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=["customer_id", "date", "product_id", "quantity", "price"])
		writer.writeheader()
		writer.writerows(rows)

	print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
	main()
