import { useMemo } from 'react'
import './CandleChart.css'

function number(value){
  const parsed=Number(value)
  return Number.isFinite(parsed)?parsed:null
}

export function CandleChart({candles=[],symbol}){
  const points=useMemo(()=>candles.filter(item=>!symbol||item.symbol===symbol).filter(item=>['open','high','low','close'].every(key=>number(item[key])!==null)).slice(-40),[candles,symbol])
  if(!points.length)return <div className="empty">No closed candles are available from the authenticated backend yet.</div>
  const high=Math.max(...points.map(item=>number(item.high))),low=Math.min(...points.map(item=>number(item.low))),span=high-low||1
  const x=index=>12+(index*(376/(Math.max(points.length-1,1)))), y=value=>12+((high-value)/span)*176
  return <div className="candle-chart" role="img" aria-label={`${symbol||'Market'} closed candle chart`}>
    <svg viewBox="0 0 400 200" preserveAspectRatio="none"><line x1="12" x2="388" y1="188" y2="188" className="chart-axis"/>
      {points.map((item,index)=>{const open=number(item.open),close=number(item.close),top=y(Math.max(open,close)),bottom=y(Math.min(open,close)),up=close>=open;return <g key={`${item.start_time}-${index}`} className={up?'candle up':'candle down'}><line x1={x(index)} x2={x(index)} y1={y(number(item.high))} y2={y(number(item.low))}/><rect x={x(index)-3} y={top} width="6" height={Math.max(bottom-top,2)}/></g>})}
    </svg><div className="chart-caption"><span>{points[0].symbol} · {points.length} closed candles</span><span>{points.at(-1).data_source||'UNKNOWN SOURCE'}</span></div>
  </div>
}
