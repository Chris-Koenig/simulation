from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
import pandas as pd
from .services.datastore import DataStore
from .services.forecast import ForecastService
from .services.model import ModelStore

app = FastAPI(title="Revenue Forecast API", version="0.1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


class ForecastRequest(BaseModel):
	price_multipliers: Dict[str, float]
	horizon_months: int = 12


class ForecastPoint(BaseModel):
	month: str
	revenue: float


class ForecastResponse(BaseModel):
	points: List[ForecastPoint]
	total_revenue: float


class HistoryPoint(BaseModel):
    month: str
    revenue: float

class HistoryResponse(BaseModel):
    points: List[HistoryPoint]


@app.get("/health")
async def health() -> Dict[str, str]:
	return {"status": "ok"}


@app.post("/upload")
async def upload_transactions(file: UploadFile = File(...)) -> Dict[str, str]:
	if not file.filename.endswith((".csv", ".txt")):
		raise HTTPException(status_code=400, detail="Please upload a CSV file")
	contents = await file.read()
	try:
		df = pd.read_csv(pd.io.common.BytesIO(contents))
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}")

	required_columns = {"customer_id", "date", "product_id", "quantity", "price"}
	missing = required_columns - set(df.columns)
	if missing:
		raise HTTPException(status_code=400, detail=f"Missing columns: {sorted(list(missing))}")

	# Normalize types
	df["date"] = pd.to_datetime(df["date"], errors="coerce")
	if df["date"].isna().any():
		raise HTTPException(status_code=400, detail="Invalid date values detected.")
	# enforce dtypes
	df["customer_id"] = df["customer_id"].astype(str)
	df["product_id"] = df["product_id"].astype(str)
	for col in ["quantity", "price"]:
		df[col] = pd.to_numeric(df[col], errors="coerce")
		if df[col].isna().any():
			raise HTTPException(status_code=400, detail=f"Invalid numeric values in {col} column.")

	DataStore.set_transactions(df)
	# Train models automatically after upload (best-effort)
	try:
		ModelStore.train_from_transactions(df)
	except Exception:
		pass
	return {"status": "ok", "rows": str(len(df))}


@app.get("/products")
async def list_products() -> Dict[str, List[str]]:
	df = DataStore.get_transactions()
	if df is None:
		raise HTTPException(status_code=400, detail="No data uploaded yet.")
	products = sorted(df["product_id"].unique().tolist())
	return {"products": products}


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(request: ForecastRequest) -> ForecastResponse:
	df = DataStore.get_transactions()
	if df is None:
		raise HTTPException(status_code=400, detail="No data uploaded yet.")

	# If ML models exist, use them to forecast with exogenous prices; otherwise fall back
	if ModelStore.has_models():
		points_df = ModelStore.predict_future_months(
			df=df,
			horizon_months=request.horizon_months,
			price_multipliers=request.price_multipliers,
		)
	else:
		service = ForecastService(df)
		points_df = service.forecast_revenue(
			price_multipliers=request.price_multipliers,
			horizon_months=request.horizon_months,
			anchor_to_history=True,
		)
	# Ensure month is a string (YYYY-MM) for response model
	if not points_df.empty and not isinstance(points_df["month"].iloc[0], str):
		points_df = points_df.copy()
		try:
			points_df["month"] = points_df["month"].dt.strftime("%Y-%m")
		except Exception:
			points_df["month"] = points_df["month"].astype(str)
	points = [ForecastPoint(month=m, revenue=float(r)) for m, r in zip(points_df["month"], points_df["revenue"])]
	total = float(points_df["revenue"].sum())
	return ForecastResponse(points=points, total_revenue=total)
@app.post("/train")
async def train_models() -> Dict[str, Dict[str, str]]:
	df = DataStore.get_transactions()
	if df is None:
		raise HTTPException(status_code=400, detail="No data uploaded yet.")
	result = ModelStore.train_from_transactions(df)
	return {"models": result}


@app.get("/history", response_model=HistoryResponse)
async def history(months: int = 12) -> HistoryResponse:
    if months <= 0:
        raise HTTPException(status_code=400, detail="months must be > 0")

    df = DataStore.get_transactions()
    if df is None:
        raise HTTPException(status_code=400, detail="No data uploaded yet.")

    work = df.copy()
    work["month"] = work["date"].values.astype("datetime64[M]")
    work["revenue"] = work["quantity"] * work["price"]

    monthly = work.groupby("month", as_index=False)["revenue"].sum().sort_values("month")
    if monthly.empty:
        return HistoryResponse(points=[])

    last_month = pd.Period(monthly["month"].max(), freq="M")
    start_period = last_month - (months - 1)
    idx_periods = [start_period + i for i in range(months)]
    idx_df = pd.DataFrame({
        "month": [p.to_timestamp() for p in idx_periods]
    })
    filled = idx_df.merge(monthly, on="month", how="left").fillna({"revenue": 0.0})
    filled["month"] = filled["month"].dt.strftime("%Y-%m")

    points = [HistoryPoint(month=str(m), revenue=float(r)) for m, r in zip(filled["month"], filled["revenue"])]
    return HistoryResponse(points=points)


if __name__ == "__main__":
	import uvicorn
	uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
