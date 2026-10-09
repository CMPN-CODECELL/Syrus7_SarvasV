import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Card, DataTable, Money, Page, Readiness, Status } from '../components/UI'
import { strategyRows } from '../domain/snapshot'

export const MAX_BATCH_SYMBOLS=20
export const DEMO_STOCK_PRESETS=['RELIANCE','TCS','INFY','HDFCBANK','ICICIBANK','SBIN']
const displayName=value=>String(value).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())
export const normalizeSymbols=values=>[...new Set(values.flatMap(value=>String(value).split(/[,\n]/)).map(value=>value.trim().toUpperCase()).filter(Boolean))]
export const idFragment=value=>String(value).trim().toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')

export function StrategiesPage(){
  const {snapshot:s,refresh}=useOutletContext()
  const [strategies,setStrategies]=useState([])
  const [kind,setKind]=useState('')
  const [prefix,setPrefix]=useState('')
  const [symbolInput,setSymbolInput]=useState('')
  const [stockChoice,setStockChoice]=useState('')
  const [symbols,setSymbols]=useState([])
  const [pending,setPending]=useState('')
  const [error,setError]=useState('')
  const [success,setSuccess]=useState(null)
  const [filters,setFilters]=useState({kind:'',symbol:'',state:''})

  useEffect(()=>{
    let active=true
    api.get('/api/strategies').then(items=>{
      if(!active)return
      const available=Array.isArray(items)?items:[]
      setStrategies(available)
      if(available.length){setKind(current=>current||available[0].kind);setPrefix(current=>current||available[0].kind)}
    }).catch(loadError=>{if(active){setStrategies([]);setError(loadError.message||'Unable to load strategy types.')}})
    return()=>{active=false}
  },[])

  const addSymbols=(rawValue=symbolInput,{clearInput=false}={})=>{
    setError('');setSuccess(null)
    const next=normalizeSymbols([...symbols,...normalizeSymbols([rawValue])])
    if(next.length>MAX_BATCH_SYMBOLS){setError(`Choose no more than ${MAX_BATCH_SYMBOLS} unique symbols.`);return}
    setSymbols(next)
    if(clearInput)setSymbolInput('')
  }
  const removeSymbol=symbol=>setSymbols(current=>current.filter(item=>item!==symbol))
  const selectKind=next=>{setKind(next);setPrefix(current=>!current||current===kind?next:current)}

  const runControl=async row=>{
    if(pending)return
    const key=`control:${row.id}`
    setPending(key);setError('');setSuccess(null)
    try{await api.post(`/api/subscriptions/${row.id}/${row.enabled?'stop':'start'}`);await refresh()}
    catch(actionError){setError(actionError.message||'Strategy action failed.')}
    finally{setPending('')}
  }

  const submit=async event=>{
    event.preventDefault()
    if(pending||!symbols.length)return
    setPending('batch');setError('');setSuccess(null)
    try{
      const result=await api.post('/api/subscriptions/batch',{kind,symbols,instance_prefix:prefix})
      await refresh()
      setSuccess({count:result.count,symbols:result.symbols})
      setSymbols([]);setSymbolInput('')
    }catch(actionError){
      if(actionError.status===409&&actionError.detail?.code==='SUBSCRIPTION_BATCH_CONFLICT')setError(`Could not create the set. Already exists: ${actionError.detail.existing.join(', ')}. Nothing was created.`)
      else setError(actionError.message||'Strategy creation failed. Nothing was created.')
    }finally{setPending('')}
  }

  const rows=strategyRows(s)
  const visibleRows=useMemo(()=>rows.filter(row=>(!filters.kind||row.kind===filters.kind)&&(!filters.symbol||row.symbol===filters.symbol)&&(!filters.state||row.state===filters.state)),[rows,filters])
  const knownSymbols=[...new Set(rows.map(row=>row.symbol))].sort()
  const observedSymbols=[...new Set([...(s?.candles||[]).map(item=>item.symbol),...knownSymbols])].filter(Boolean).sort()
  const presetSymbols=DEMO_STOCK_PRESETS.filter(symbol=>!observedSymbols.includes(symbol))
  const knownStates=[...new Set(rows.map(row=>row.state))].sort()
  const previewPrefix=idFragment(prefix||kind)

  return <Page eyebrow="Subscriptions" title="Run one strategy across many stocks" description="Independent strategy ledgers keep each stock isolated. Choose a strategy and stocks once; failures, positions, risk, and P&L stay independent.">
    {error&&<div className="error" role="alert">{error}</div>}
    {success&&<div className="success" role="status"><b>Created {success.count} strategy {success.count===1?'instance':'instances'}.</b><span>{success.symbols.join(', ')}</span></div>}
    <div className="grid strategy-grid">
      <Card title="Strategy instances" meta={`${visibleRows.length} shown · ${rows.length} total`}>
        <div className="filter-row" aria-label="Strategy filters">
          <label>Kind<select aria-label="Filter by kind" value={filters.kind} onChange={event=>setFilters({...filters,kind:event.target.value})}><option value="">All kinds</option>{[...new Set(rows.map(row=>row.kind))].sort().map(value=><option key={value}>{value}</option>)}</select></label>
          <label>Symbol<select aria-label="Filter by symbol" value={filters.symbol} onChange={event=>setFilters({...filters,symbol:event.target.value})}><option value="">All symbols</option>{knownSymbols.map(value=><option key={value}>{value}</option>)}</select></label>
          <label>State<select aria-label="Filter by state" value={filters.state} onChange={event=>setFilters({...filters,state:event.target.value})}><option value="">All states</option>{knownStates.map(value=><option key={value}>{value}</option>)}</select></label>
        </div>
        <DataTable rows={visibleRows} columns={[
          {key:'id',label:'Strategy'},
          {key:'kind',label:'Kind'},
          {key:'symbol',label:'Symbol'},
          {key:'state',label:'State',render:r=><Status value={r.state}/>},
          {key:'readiness',label:'Readiness',render:r=><Readiness value={r.readiness}/>},
          {key:'net_quantity',label:'Position',render:r=>r.financial_position?.net_quantity??'—'},
          {key:'net_pnl',label:'Net P&L',render:r=><Money value={r.financial_position?.net_pnl}/>},
          {key:'charges',label:'Charges',render:r=><Money value={r.financial_position?.charges}/>},
          {key:'control',label:'Control',render:r=>{const key=`control:${r.id}`;return <button disabled={!!pending} onClick={()=>runControl(r)}>{pending===key?'Working…':r.enabled?'Stop':'Start'}</button>}},
        ]}/>
      </Card>
      <Card title="Create strategy set" meta="Uses your signed-in account">
        <p className="muted">This creates independent instances atomically: either every selected stock is added, or none are.</p>
        <form onSubmit={submit}>
          <label>Strategy<select required value={kind} onChange={event=>selectKind(event.target.value)}>{strategies.map(strategy=><option value={strategy.kind} key={strategy.kind}>{strategy.description||displayName(strategy.kind)}</option>)}</select></label>
          <label>Instance prefix<input required maxLength="48" placeholder="momentum" value={prefix} onChange={event=>setPrefix(event.target.value)}/><small>Used only to name each instance.</small></label>
          <label>Quick select stock<select aria-label="Quick select stock" value={stockChoice} disabled={symbols.length>=MAX_BATCH_SYMBOLS} onChange={event=>{const value=event.target.value;setStockChoice('');if(value)addSymbols(value)}}><option value="">Choose a stock…</option>{observedSymbols.length>0&&<optgroup label="Observed by backend">{observedSymbols.map(symbol=><option value={symbol} key={`observed-${symbol}`} disabled={symbols.includes(symbol)}>{symbol}</option>)}</optgroup>}{presetSymbols.length>0&&<optgroup label="Demo shortcuts">{presetSymbols.map(symbol=><option value={symbol} key={`preset-${symbol}`} disabled={symbols.includes(symbol)}>{symbol}</option>)}</optgroup>}</select><small>Demo shortcuts are conveniences, not confirmation of live-feed availability.</small></label>
          <label>Or enter stocks<div className="input-action"><input aria-label="Stocks" placeholder="RELIANCE, TCS, INFY" value={symbolInput} onChange={event=>setSymbolInput(event.target.value.toUpperCase())} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();addSymbols(symbolInput,{clearInput:true})}}}/><button type="button" onClick={()=>addSymbols(symbolInput,{clearInput:true})} disabled={!symbolInput.trim()||symbols.length>=MAX_BATCH_SYMBOLS}>Add</button></div><small>Paste comma-separated symbols or add one at a time. Maximum {MAX_BATCH_SYMBOLS}.</small></label>
          <div className="chips" aria-label="Selected stocks">{symbols.map(symbol=><button type="button" className="chip" key={symbol} onClick={()=>removeSymbol(symbol)} aria-label={`Remove ${symbol}`}>{symbol} ×</button>)}</div>
          {symbols.length>0&&<div className="instance-preview"><b>Instances to create</b>{symbols.map(symbol=><code key={symbol}>{previewPrefix}-{idFragment(symbol)} <span>→ {symbol}</span></code>)}</div>}
          <button className="primary" disabled={!strategies.length||!symbols.length||!!pending}>{pending==='batch'?`Creating ${symbols.length} strategy ${symbols.length===1?'instance':'instances'}…`:symbols.length===1?'Create strategy':`Run on ${symbols.length} stocks`}</button>
        </form>
      </Card>
    </div>
    <Card title="Emitted signals" meta="Backend candle evidence; interval and timestamp in seconds">
      <DataTable rows={s?.signals} columns={[
        {key:'strategy',label:'Strategy'}, {key:'symbol',label:'Symbol'},
        {key:'side',label:'Side'}, {key:'interval',label:'Interval (seconds)'},
        {key:'reason',label:'Reason'}, {key:'candle_start',label:'Candle start (UTC epoch)'},
      ]}/>
    </Card>
  </Page>
}
