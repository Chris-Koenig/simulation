from __future__ import annotations
import pandas as pd
from typing import Optional


class DataStore:
	_trans_df: Optional[pd.DataFrame] = None

	@classmethod
	def set_transactions(cls, df: pd.DataFrame) -> None:
		# keep only needed columns in a copy to avoid accidental mutation
		cls._trans_df = df[["customer_id", "date", "product_id", "quantity", "price"]].copy()

	@classmethod
	def get_transactions(cls) -> Optional[pd.DataFrame]:
		return cls._trans_df
