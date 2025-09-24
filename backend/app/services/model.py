from __future__ import annotations
from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor


class ModelStore:
    _models: Dict[str, GradientBoostingRegressor] = {}
    _avg_price_by_product: Dict[str, float] = {}

    @classmethod
    def clear(cls) -> None:
        cls._models = {}
        cls._avg_price_by_product = {}

    @classmethod
    def train_from_transactions(cls, df: pd.DataFrame) -> Dict[str, str]:
        work = df.copy()
        work["month"] = work["date"].values.astype("datetime64[M]")
        # aggregate to monthly per product
        monthly = (
            work.groupby(["product_id", "month"], as_index=False)
            .agg(quantity=("quantity", "sum"), avg_price=("price", "mean"))
            .sort_values(["product_id", "month"]) 
        )

        monthly["month_num"] = monthly["month"].dt.month
        monthly["year"] = monthly["month"].dt.year

        cls._models = {}
        cls._avg_price_by_product = {}
        trained: Dict[str, str] = {}

        for product_id, g in monthly.groupby("product_id"):
            g = g.dropna(subset=["quantity", "avg_price"])  # basic hygiene
            if len(g) < 6:
                trained[str(product_id)] = "skipped: not enough history"
                continue
            X = g[["month_num", "year", "avg_price"]].values
            y = g["quantity"].values
            model = GradientBoostingRegressor(random_state=42)
            model.fit(X, y)
            cls._models[str(product_id)] = model
            # store latest average price as baseline
            cls._avg_price_by_product[str(product_id)] = float(g.iloc[-1]["avg_price"]) if not np.isnan(g.iloc[-1]["avg_price"]) else 1.0
            trained[str(product_id)] = "trained"

        return trained

    @classmethod
    def has_models(cls) -> bool:
        return len(cls._models) > 0

    @classmethod
    def predict_future_months(
        cls,
        df: pd.DataFrame,
        horizon_months: int,
        price_multipliers: Dict[str, float],
    ) -> pd.DataFrame:
        """Predict monthly revenue per month using learned quantity model and user prices.
        Returns DataFrame with columns: month (timestamp), revenue (float)
        """
        if not cls._models:
            # no models, return empty
            return pd.DataFrame({"month": pd.Series(dtype="datetime64[ns]"), "revenue": pd.Series(dtype=float)})

        work = df.copy()
        work["month"] = work["date"].values.astype("datetime64[M]")

        last_month = work["month"].max()
        start_period = pd.Period(last_month, freq="M") + 1
        periods = [start_period + i for i in range(horizon_months)]
        future_months = pd.DataFrame({
            "month": [p.to_timestamp() for p in periods],
            "month_num": [p.month for p in periods],
            "year": [p.year for p in periods],
        })

        rows = []
        products = sorted(work["product_id"].astype(str).unique())
        # fall back avg price per product from data if not stored
        current_avg_price = (
            work.groupby("product_id")["price"].mean().rename("avg_price").reset_index()
        )
        for product_id in products:
            pid = str(product_id)
            model = cls._models.get(pid)
            if model is None:
                continue
            base_price = cls._avg_price_by_product.get(
                pid,
                float(current_avg_price[current_avg_price["product_id"] == product_id]["avg_price"].values[0])
                if (current_avg_price["product_id"] == product_id).any() else 1.0,
            )
            multiplier = float(price_multipliers.get(pid, 1.0))
            new_price = base_price * multiplier

            Xf = future_months.copy()
            Xf["avg_price"] = new_price
            q_pred = model.predict(Xf[["month_num", "year", "avg_price"]].values)
            q_pred = np.maximum(q_pred, 0.0)
            revenue = q_pred * new_price
            for m, rev in zip(Xf["month"], revenue):
                rows.append({"product_id": pid, "month": m, "revenue": float(rev)})

        out = pd.DataFrame(rows)
        if out.empty:
            return pd.DataFrame({"month": future_months["month"], "revenue": [0.0] * len(future_months)})
        agg = out.groupby("month", as_index=False)["revenue"].sum()
        return agg


