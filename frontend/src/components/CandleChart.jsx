import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import './CandleChart.css'

function number(value){
  const parsed=Number(value)
  return Number.isFinite(parsed)?parsed:null
}

export function CandleChart({candles=[],symbol,symbols=[]}){
  const [selectedSymbol,setSelectedSymbol]=useState(symbol||symbols[0]||'')
  const [interval,setInterval]=useState(60)
  const [history,setHistory]=useState([])
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  useEffect(()=>{if(symbol)setSelectedSymbol(symbol)},[symbol])
  useEffect(()=>{let active=true;setLoading(true);const query=new URLSearchParams({interval:String(interval),limit:'200'});if(selectedSymbol)query.set('symbol',selectedSymbol);Promise.resolve().then(()=>api.get(`/api/candles?${query}`)).then(rows=>{if(active)setHistory(Array.isArray(rows)?rows:[])}).catch(err=>{if(active){setHistory([]);setError(err.message||'Historical candles unavailable.')}}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[interval,selectedSymbol])
  const points=useMemo(()=>[...history,...candles].filter(item=>!selectedSymbol||item.symbol===selectedSymbol).filter(item=>Number(item.interval)===interval).filter(item=>['open','high','low','close'].every(key=>number(item[key])!==null)).slice(-40),[candles,history,interval,selectedSymbol])
  const availableSymbols=[...new Set([...symbols,...candles.map(item=>item.symbol).filter(Boolean)])].sort()
  if(loading&&!points.length)return <div className="empty">Loading authenticated candle history…</div>
  if(error&&!points.length)return <div className="empty">{error}</div>
  if(!points.length)return <div className="empty">No closed {interval===60?'1-minute':'5-minute'} candles are available.</div>
  const high=Math.max(...points.map(item=>number(item.high))),low=Math.min(...points.map(item=>number(item.low))),span=high-low||1
  const x=index=>12+(index*(376/(Math.max(points.length-1,1)))), y=value=>12+((high-value)/span)*176
  return <div className="candle-chart"><div className="chart-controls"><label>Symbol<select value={selectedSymbol} onChange={event=>setSelectedSymbol(event.target.value)}><option value="">All symbols</option>{availableSymbols.map(item=><option key={item} value={item}>{item}</option>)}</select></label><button type="button" onClick={()=>setInterval(interval===60?300:60)}>Use {interval===60?'5-minute':'1-minute'} candles</button></div><div role="img" aria-label={`${selectedSymbol||'Market'} closed candle chart`}>
    <svg viewBox="0 0 400 200" preserveAspectRatio="none"><line x1="12" x2="388" y1="188" y2="188" className="chart-axis"/>
      {points.map((item,index)=>{const open=number(item.open),close=number(item.close),top=y(Math.max(open,close)),bottom=y(Math.min(open,close)),up=close>=open;return <g key={`${item.start_time}-${index}`} className={up?'candle up':'candle down'}><line x1={x(index)} x2={x(index)} y1={y(number(item.high))} y2={y(number(item.low))}/><rect x={x(index)-3} y={top} width="6" height={Math.max(bottom-top,2)}/></g>})}
    </svg><div className="chart-caption"><span>{points[0].symbol} · {points.length} closed candles · {interval===60?'1m':'5m'}</span><span>{points.at(-1).data_source||'UNKNOWN SOURCE'}</span></div></div>
  </div>
}
