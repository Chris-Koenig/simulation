import React, { useEffect, useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, ReferenceLine } from 'recharts'

type ProductsResponse = { products: string[] }

type ForecastPoint = { month: string; revenue: number }

type ForecastResponse = { points: ForecastPoint[]; total_revenue: number }

type HistoryPoint = { month: string; revenue: number }
type HistoryResponse = { points: HistoryPoint[] }

// Vite puts env vars on import.meta.env; provide fallback typing and value
const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

export const App: React.FC = () => {
	const [products, setProducts] = useState<string[]>([])
	const [priceMultipliers, setPriceMultipliers] = useState<Record<string, number>>({})
	const [horizon, setHorizon] = useState<number>(12)
	const [forecast, setForecast] = useState<ForecastPoint[] | null>(null)
	const [history, setHistory] = useState<HistoryPoint[] | null>(null)
	const [historyValue, setHistoryValue] = useState<number>(12)
	const [historyUnit, setHistoryUnit] = useState<'months' | 'years'>('months')
	const [uploading, setUploading] = useState(false)
	const [loading, setLoading] = useState(false)
	const [error, setError] = useState<string | null>(null)

	useEffect(() => {
		// attempt to fetch products to see if data exists
		fetch(`${API_BASE}/products`).then(async (r) => {
			if (!r.ok) return
			const data: ProductsResponse = await r.json()
			setProducts(data.products)
			setPriceMultipliers(Object.fromEntries(data.products.map((p) => [p, 1])))
		}).catch(() => {})
	}, [])

	const historyMonths = useMemo(() => (historyUnit === 'years' ? historyValue * 12 : historyValue), [historyUnit, historyValue])

	useEffect(() => {
		// fetch history whenever data exists and the window changes
		if (products.length === 0) return
		const controller = new AbortController()
		fetch(`${API_BASE}/history?months=${historyMonths}`, { signal: controller.signal })
			.then(async (r) => {
				if (!r.ok) throw new Error(await r.text())
				const data: HistoryResponse = await r.json()
				setHistory(data.points)
			})
			.catch(() => {})
		return () => controller.abort()
	}, [products.length, historyMonths])

	const onUpload = async (file: File) => {
		setUploading(true)
		setError(null)
		try {
			const form = new FormData()
			form.append('file', file)
			const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })
			if (!res.ok) throw new Error(await res.text())
			// refresh products
			const prodRes = await fetch(`${API_BASE}/products`)
			const data: ProductsResponse = await prodRes.json()
			setProducts(data.products)
			setPriceMultipliers(Object.fromEntries(data.products.map((p) => [p, 1])))
		} catch (e: any) {
			setError(e?.message ?? 'Upload failed')
		} finally {
			setUploading(false)
		}
	}

	const doForecast = async () => {
		setLoading(true)
		setError(null)
		try {
			const res = await fetch(`${API_BASE}/forecast`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ price_multipliers: priceMultipliers, horizon_months: horizon }),
			})
			if (!res.ok) throw new Error(await res.text())
			const data: ForecastResponse = await res.json()
			setForecast(data.points)
		} catch (e: any) {
			setError(e?.message ?? 'Forecast failed')
		} finally {
			setLoading(false)
		}
	}

	const combinedData = useMemo(() => {
		if (!history && !forecast) return [] as Array<{ month: string; history?: number; forecast?: number }>
		const map = new Map<string, { month: string; history?: number; forecast?: number }>()
		if (history) {
			for (const p of history) {
				map.set(p.month, { month: p.month, history: p.revenue })
			}
		}
		if (forecast) {
			for (const p of forecast) {
				const prev = map.get(p.month) || { month: p.month }
				prev.forecast = p.revenue
				map.set(p.month, prev)
			}
		}
		return Array.from(map.values()).sort((a, b) => (a.month < b.month ? -1 : a.month > b.month ? 1 : 0))
	}, [history, forecast])

	const forecastStart = useMemo(() => (forecast && forecast.length > 0 ? forecast[0].month : null), [forecast])

	return (
		<>
			<header className="app-header">
				<div className="app-header__inner">
					<div className="brand">
						<div className="brand-badge" />
						<div>
							<div className="brand-title">Revenue Simulator</div>
							<div className="brand-sub">Forecast impact of pricing adjustments</div>
						</div>
					</div>
					<div className="muted">v0.1</div>
				</div>
			</header>
			<div className="app-shell">
				<div className="panel">
					<div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
						<input type="file" accept=".csv,text/csv" onChange={(e) => e.target.files && onUpload(e.target.files[0])} />
						{uploading && <span className="muted">Uploading…</span>}
					</div>
				</div>

				{products.length > 0 && (
					<div className="panel-grid">
						{products.map((p) => (
							<div key={p} className="panel">
								<div style={{ display: 'flex', justifyContent: 'space-between' }}>
									<h3>Product {p}</h3>
									<span>{(priceMultipliers[p] ?? 1).toFixed(2)}x</span>
								</div>
								<input
									type="range"
									min={0.5}
									max={1.5}
									step={0.01}
									value={priceMultipliers[p] ?? 1}
									onChange={(e) => setPriceMultipliers((s) => ({ ...s, [p]: Number(e.target.value) }))}
								/>
							</div>
						))}
						<div className="panel">
							<h3>Forecast</h3>
							<label>
								<strong>Horizon (months): {horizon}</strong>
								<input type="range" min={3} max={36} step={1} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
							</label>
							<button onClick={doForecast} disabled={loading} className="btn" style={{ marginLeft: 12 }}>
								{loading ? 'Running…' : 'Run forecast'}
							</button>
						</div>
						<div className="panel">
							<h3>History window</h3>
							<div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
								<strong>Show past:</strong>
								<input
									type="number"
									min={1}
									max={120}
									step={1}
									value={historyValue}
									onChange={(e) => setHistoryValue(Math.max(1, Number(e.target.value)))}
									style={{ width: 80 }}
								/>
								<select value={historyUnit} onChange={(e) => setHistoryUnit(e.target.value as 'months' | 'years')}>
									<option value="months">months</option>
									<option value="years">years</option>
								</select>
							</div>
							<div className="chart-legend">Past is shown in blue. Forecast in green.</div>
						</div>
					</div>
				)}

				{error && (
					<div className="panel" style={{ color: '#b00020' }}>{error}</div>
				)}

				{(history || forecast) && (
					<div className="panel chart-card">
						<ResponsiveContainer width="100%" height="100%">
							<LineChart data={combinedData}>
								<CartesianGrid strokeDasharray="3 3" />
								<XAxis dataKey="month" />
								<YAxis />
								<Tooltip />
								{forecastStart && (
									<ReferenceLine x={forecastStart} stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 4" label={{ value: 'Forecast', position: 'top', fill: '#475569', fontSize: 12 }} />
								)}
								<Line type="monotone" dataKey="history" name="History" stroke="#2563eb" strokeWidth={2} dot={false} />
								<Line type="monotone" dataKey="forecast" name="Forecast" stroke="#16a34a" strokeWidth={2} dot={false} />
							</LineChart>
						</ResponsiveContainer>
					</div>
				)}
			</div>
		</>
	)
}
