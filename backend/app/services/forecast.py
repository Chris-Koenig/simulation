from __future__ import annotations
from typing import Dict
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression


class ForecastService:
	def __init__(self, transactions: pd.DataFrame) -> None:
		self.df = transactions.copy()
		self.df["month"] = self.df["date"].values.astype("datetime64[M]")
		self.df["revenue"] = self.df["quantity"] * self.df["price"]

	def _estimate_elasticity_per_product(self) -> Dict[str, float]:
		# Aggregate to product-month level to reduce noise
		agg = (
			self.df.groupby(["product_id", "month"], as_index=False)
			.agg(quantity=("quantity", "sum"), price=("price", "mean"))
		)
		agg = agg[(agg["quantity"] > 0) & (agg["price"] > 0)].copy()
		agg["ln_q"] = np.log(agg["quantity"])
		agg["ln_p"] = np.log(agg["price"])

		elasticities: Dict[str, float] = {}
		for product_id, g in agg.groupby("product_id"):
			if len(g) < 6:
				# not enough variation, default mild negative elasticity
				elasticities[product_id] = -0.5
				continue
			X = g[["ln_p"]].values
			y = g["ln_q"].values
			model = LinearRegression()
			model.fit(X, y)
			elasticities[product_id] = float(model.coef_[0])
		return elasticities

	def _seasonality_index(self) -> pd.DataFrame:
		# Compute month-of-year seasonality on revenue
		self.df["month_num"] = self.df["date"].dt.month
		monthly = self.df.groupby(["month", "month_num"], as_index=False)["revenue"].sum()
		# Normalize to mean 1
		season = monthly.groupby("month_num")["revenue"].mean()
		idx = (season / season.mean()).rename("season_index").reset_index()
		return idx  # columns: month_num, season_index

	def _baseline_quantity_per_product(self) -> pd.DataFrame:
		# Use last 12 months average quantity per product as baseline (per-transaction mean)
		last_month = self.df["month"].max()
		start = (pd.Period(last_month, freq="M") - 11).to_timestamp()
		recent = self.df[self.df["month"] >= start]
		base = (
			recent.groupby(["product_id"], as_index=False)["quantity"].mean()
			.rename(columns={"quantity": "baseline_quantity"})
		)
		return base

	def forecast_revenue(self, price_multipliers: Dict[str, float], horizon_months: int = 12, anchor_to_history: bool = True) -> pd.DataFrame:
		elasticities = self._estimate_elasticity_per_product()
		season_idx = self._seasonality_index()
		baseline = self._baseline_quantity_per_product()

		products = sorted(self.df["product_id"].unique())
		# Current average price per product
		avg_price = (
			self.df.groupby("product_id")["price"].mean().rename("avg_price").reset_index()
		)
		base_df = baseline.merge(avg_price, on="product_id", how="left")
		# fill missing baselines with overall mean quantity to avoid NaNs
		if base_df["baseline_quantity"].isna().any():
			mean_q = self.df["quantity"].mean()
			base_df["baseline_quantity"].fillna(mean_q if not np.isnan(mean_q) else 1.0, inplace=True)

		# Build future months index (start after the last historical month)
		last_month = self.df["month"].max()
		start_period = pd.Period(last_month, freq="M") + 1
		periods = [start_period + i for i in range(horizon_months)]
		future_months = pd.DataFrame({
			"month": [p.to_timestamp() for p in periods],
			"month_num": [p.month for p in periods]
		})
		future = future_months.merge(season_idx, on="month_num", how="left").fillna({"season_index": 1.0})

		rows = []
		for _, prod in base_df.iterrows():
			product_id = str(prod["product_id"])
			baseline_q = float(prod["baseline_quantity"])  # average per month
			current_price = float(prod["avg_price"]) if not np.isnan(prod["avg_price"]) else 1.0
			multiplier = float(price_multipliers.get(product_id, 1.0))
			new_price = current_price * multiplier
			elasticity = float(elasticities.get(product_id, -0.5))

			# Quantity adjustment via price elasticity: Q' = Q * (P'/P)^elasticity
			quantity_factor = (new_price / max(current_price, 1e-6)) ** elasticity
			for _, f in future.iterrows():
				q = baseline_q * quantity_factor * float(f["season_index"])  # seasonality scaling
				rev = q * new_price
				rows.append({
					"product_id": product_id,
					"month": f["month"],
					"revenue": rev,
				})

		forecast_df = pd.DataFrame(rows)
		if forecast_df.empty:
			return pd.DataFrame({"month": future["month"], "revenue": [0.0] * len(future)})
		out = forecast_df.groupby("month", as_index=False)["revenue"].sum()

		# Optional anchoring: align first forecast point(s) to last historical month when requested
		if anchor_to_history:
			# Compute last historical monthly revenue
			hist_monthly = self.df.groupby("month", as_index=False)["revenue"].sum().sort_values("month")
			if not hist_monthly.empty and not out.empty:
				# Use the last calendar day of the last historical month for the anchor point
				last_hist_month_period = pd.Period(hist_monthly.iloc[-1]["month"], freq="M")
				last_hist_month = last_hist_month_period.to_timestamp(how="end")
				last_hist_rev = float(hist_monthly.iloc[-1]["revenue"])
				# Scale entire forecast so first future month matches last historical level
				first_forecast_rev = float(out.iloc[0]["revenue"]) if float(out.iloc[0]["revenue"]) != 0 else 0.0
				if first_forecast_rev > 0 and last_hist_rev > 0:
					scale = last_hist_rev / max(first_forecast_rev, 1e-6)
					out["revenue"] = out["revenue"] * scale
				# Also prepend an anchor point at the last day of the last historical month for visual continuity
				anchor_row = pd.DataFrame({"month": [last_hist_month], "revenue": [last_hist_rev]})
				out = pd.concat([anchor_row, out], ignore_index=True)
		out["month"] = out["month"].dt.strftime("%Y-%m")
		return out
