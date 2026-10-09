import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import './CandleChart.css'

const number = value => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function CandleChart({
  candles = [],
  formingCandles = [],
  latestQuotes = [],
  marketData = {},
  symbol,
  symbols = [],
  accountId,
}) {
  const [selectedSymbol, setSelectedSymbol] = useState(symbol || symbols[0] || '')
  const [interval, setInterval] = useState(60)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (symbol !== undefined) setSelectedSymbol(symbol)
  }, [symbol])

  useEffect(() => {
    let active = true
    setHistory([])
    setLoading(true)
    setError('')
    const query = new URLSearchParams({ interval: String(interval), limit: '200' })
    if (selectedSymbol) query.set('symbol', selectedSymbol)
    Promise.resolve()
      .then(() => api.get(`/api/candles?${query}`))
      .then(rows => {
        if (active) setHistory(Array.isArray(rows) ? rows : [])
      })
      .catch(requestError => {
        if (active) setError(requestError.message || 'Historical candles unavailable.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [accountId, interval, selectedSymbol])

  const points = useMemo(() => {
    const indexed = new Map()
    for (const item of [...history, ...candles, ...formingCandles]) {
      if ((selectedSymbol && item.symbol !== selectedSymbol) || Number(item.interval) !== interval) continue
      if (!['open', 'high', 'low', 'close'].every(key => number(item[key]) !== null)) continue
      indexed.set(`${item.symbol}:${item.interval}:${item.start_time}`, item)
    }
    return [...indexed.values()].sort((left, right) => left.start_time - right.start_time).slice(-80)
  }, [candles, formingCandles, history, interval, selectedSymbol])

  const availableSymbols = [...new Set([
    ...symbols,
    ...candles.map(item => item.symbol),
    ...formingCandles.map(item => item.symbol),
    ...latestQuotes.map(item => item.symbol),
  ].filter(Boolean))].sort()
  const selectedQuote = latestQuotes
    .filter(item => !selectedSymbol || item.symbol === selectedSymbol)
    .sort((left, right) => Number(right.received_at || 0) - Number(left.received_at || 0))[0]
  const high = points.length ? Math.max(...points.map(item => number(item.high))) : null
  const low = points.length ? Math.min(...points.map(item => number(item.low))) : null
  const span = high === low ? 1 : high - low
  const x = index => 12 + index * (376 / Math.max(points.length - 1, 1))
  const y = value => 12 + ((high - value) / span) * 176

  return <div className="candle-chart">
    <div className="chart-controls">
      <label>Instrument<select aria-label="Chart symbol" value={selectedSymbol} onChange={event => setSelectedSymbol(event.target.value)}>
        <option value="">Latest available</option>
        {availableSymbols.map(item => <option key={item} value={item}>{item}</option>)}
      </select></label>
      <label>Timeframe<select aria-label="Chart timeframe" value={interval} onChange={event => setInterval(Number(event.target.value))}>
        <option value={60}>1 minute</option><option value={300}>5 minutes</option>
      </select></label>
      <span className="muted">{marketData.feed_status || marketData.label || 'Feed status unavailable'}</span>
    </div>
    {selectedQuote&&<div className="chart-quote">
      <strong>{selectedQuote.price}</strong>
      <span>{selectedQuote.symbol}</span>
      <span>{selectedQuote.data_source || marketData.source || 'UNKNOWN SOURCE'}</span>
      <span>{selectedQuote.age_seconds == null ? 'Age unavailable' : `${Math.floor(selectedQuote.age_seconds)}s old`}</span>
      <span>{selectedQuote.stale ? 'STALE QUOTE' : 'Last valid quote'}</span>
    </div>}
    {error&&<p className="chart-error" role="status">Historical request: {error}</p>}
    {!points.length ? <div className="empty" role="status">
      {loading ? 'Loading authenticated candle history…' : selectedQuote ? 'No candle has closed for this selection. Showing the latest valid quote above.' : 'No candle or valid quote is available for this selection.'}
      {marketData.chart_data_reason&&<small>{marketData.chart_data_reason}</small>}
    </div> : <>
      <svg viewBox="0 0 400 200" preserveAspectRatio="none" role="img" aria-label={`${selectedSymbol || 'Market'} ${interval === 60 ? '1-minute' : '5-minute'} candle chart`}>
        <line x1="12" x2="388" y1="188" y2="188" className="chart-axis"/>
        {points.map((item, index) => {
          const open = number(item.open)
          const close = number(item.close)
          const top = y(Math.max(open, close))
          const bottom = y(Math.min(open, close))
          const forming = item.is_closed === false
          const direction = close >= open ? 'up' : 'down'
          return <g key={`${item.symbol}:${item.interval}:${item.start_time}`} className={`candle ${direction}${forming ? ' forming' : ''}`}>
            <line x1={x(index)} x2={x(index)} y1={y(number(item.high))} y2={y(number(item.low))}/>
            <rect x={x(index)-3} y={top} width="6" height={Math.max(bottom-top,2)}/>
          </g>
        })}
      </svg>
      <div className="chart-caption">
        <span>{points.length} bars · {interval === 60 ? '1m' : '5m'} · forming bars are outlined</span>
        <span>{points.at(-1).data_source || 'UNKNOWN SOURCE'}</span>
      </div>
    </>}
  </div>
}
