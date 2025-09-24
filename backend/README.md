## Backend (FastAPI)

Run locally:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

CSV format expected for /upload:

- customer_id: string or int
- date: ISO date (e.g. 2022-06-30)
- product_id: string or int
- quantity: number
- price: number (unit price at transaction time)

Endpoints:

- GET /health
- POST /upload (multipart/form-data, file)
- GET /products -> { products: string[] }
- POST /forecast { price_multipliers: { [product_id]: number }, horizon_months?: number }
