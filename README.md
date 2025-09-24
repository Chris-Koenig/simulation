## Revenue Forecast Web App

### Prerequisites
- Python 3.10+
- Node 18+

### Backend setupbr

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

By default, the frontend expects the backend at `http://localhost:8000`. You can set `VITE_API_BASE` in an `.env` file in `frontend/` to override.

### Usage flow
1. Start backend and frontend.
2. In the UI, upload a CSV with columns: `customer_id,date,product_id,quantity,price`.
3. Adjust per-product price multipliers (0.5x–1.5x) and horizon.
4. Run forecast to view projected monthly revenue.
