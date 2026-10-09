import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Card, DataTable, Money, Page, Readiness, Status } from '../components/UI'
import { strategyRows } from '../domain/snapshot'

export const MAX_BATCH_SYMBOLS=20
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

  const setAutoMode=async enabled=>{
    if(pending)return
    setPending('auto');setError('');setSuccess(null)
    try{await api.post(`/api/auto-mode/${enabled?'start':'stop'}`);await refresh()}
    catch(actionError){setError(actionError.message||'Auto mode action failed.')}
    finally{setPending('')}
  }

  const allRows=strategyRows(s)
  const rows=allRows.filter(row=>!String(row.kind).startsWith('auto_'))
  const visibleRows=useMemo(()=>rows.filter(row=>(!filters.kind||row.kind===filters.kind)&&(!filters.symbol||row.symbol===filters.symbol)&&(!filters.state||row.state===filters.state)),[rows,filters])
  const knownSymbols=[...new Set(rows.map(row=>row.symbol))].sort()
  const providerSymbols=[
    ...(s?.market_data?.canonical_symbols||[]),
    ...(s?.market_data?.symbols||[]),
    ...(s?.market_data?.desired_symbols||[]),
    ...(s?.market_data?.subscribed_symbols||[]),
    ...(s?.market_data?.latest_quotes||[]).map(item=>item.symbol),
  ]
  const observedSymbols=[...new Set([...providerSymbols,...knownSymbols])].filter(Boolean).sort()
  const knownStates=[...new Set(rows.map(row=>row.state))].sort()
  const previewPrefix=idFragment(prefix||kind)
  const warmingRows=rows.filter(row=>row.readiness?.ready!==true)
  const demoRows=rows.filter(row=>String(row.symbol||'').toUpperCase()==='DEMO')
  const live021=String(s?.mode||'').toUpperCase().includes('021')
  const gate=String(s?.gate||'').toUpperCase()
  const activityReasons=[]
  if(live021&&demoRows.length)activityReasons.push(`DEMO is replay-only, so ${demoRows.length} DEMO ${demoRows.length===1?'subscription is':'subscriptions are'} not receiving 021 market ticks. Use a real 021 symbol (for example RELIANCE, TCS, or ICICIBANK).`)
  if(warmingRows.length)activityReasons.push(`${warmingRows.length} ${warmingRows.length===1?'strategy instance is':'strategy instances are'} warming; each must receive its required closed candles before it can emit an intent.`)
  if(gate&&gate!=='RUNNING')activityReasons.push(`New orders are paused because the platform trading gate is ${gate}. Reconcile the broker, then explicitly resume trading when the evidence is healthy.`)
  const activityMessage=activityReasons.length?activityReasons.join(' '):'Strategies do not buy or sell on every tick. They emit an intent only when their indicator condition is met; otherwise no trade is expected.'
  const auto=s?.auto_mode||{enabled:false,candidate_count:0,evaluated_count:0,decisions:[],instances:[],policy:{}}
  const readiness=s?.provider_readiness
  const exposure=readiness?.actions?.new_exposure
  const pct=value=>value===undefined?'—':`${(Number(value)*100).toFixed(2)}%`

  return <Page eyebrow="Subscriptions" title="Run one strategy across many stocks" description="Independent strategy ledgers keep each stock isolated. Choose a strategy and stocks once; failures, positions, risk, and P&L stay independent.">
    {error&&<div className="error" role="alert">{error}</div>}
    {success&&<div className="success" role="status"><b>Created {success.count} strategy {success.count===1?'instance':'instances'}.</b><span>{success.symbols.join(', ')}</span></div>}
    <Card title="Auto mode" meta={auto.enabled?'Scanning provider stocks':'Stopped'}>
      <p>Automatically compares momentum, breakout, and mean-reversion evidence across a bounded set of broker-supported stocks, selects the strongest qualified stock-and-strategy combination, and manages explicit exits. Every order still passes platform risk and broker reconciliation.</p>
      <div className="metric-grid compact">
        <div><span>Stocks scanned</span><b>{auto.candidate_count}</b></div>
        <div><span>Stocks observed</span><b>{auto.evaluated_count}</b></div>
        <div><span>Max positions</span><b>{auto.policy?.max_positions??'—'}</b></div>
        <div><span>Entry / profit / stop</span><b>{pct(auto.policy?.entry_momentum)} / {pct(auto.policy?.take_profit)} / {pct(auto.policy?.stop_loss)}</b></div>
        <div><span>021 order admission</span><b>{exposure?.status||gate||'UNKNOWN'}</b></div>
      </div>
      {exposure?.status==='BLOCKED'&&<div className="error" role="status"><b>021 BUY/SELL is currently blocked.</b> <span>{(readiness?.blocking_reasons||[exposure.reason_code]).join(' · ')}</span></div>}
      <div className="success strategy-explanation"><b>Selected instance</b><span>{auto.selected_strategy_instance_id?`${auto.selected_strategy_instance_id} · ${auto.selected_symbol} · ${displayName(auto.selected_strategy)}`:'Auto creates the selected attribution instance after enough provider stocks are warmed and compared.'}</span></div>
      <div className="warning"><b>Profit is not guaranteed.</b><span>Auto mode can lose money. It stays long-only, holds when evidence is insufficient, and cannot trade while the safety gate is not RUNNING. Stopping auto mode prevents new automatic decisions; it does not sell existing positions.</span></div>
      <button className={auto.enabled?'':'primary'} disabled={!!pending} onClick={()=>setAutoMode(!auto.enabled)}>{pending==='auto'?'Working…':auto.enabled?'Stop auto mode':'Start auto mode'}</button>
      <DataTable rows={auto.decisions} columns={[
        {key:'symbol',label:'Stock'},
        {key:'selected_strategy',label:'Selected strategy',render:r=>r.selected_strategy?displayName(r.selected_strategy):'Still comparing'},
        {key:'action',label:'Decision',render:r=><Status value={r.action}/>},
        {key:'result',label:'Risk result',render:r=>r.result?<Status value={r.result}/>:<span>Not submitted</span>},
        {key:'selected_score',label:'Selected edge',render:r=>r.selected_score===null?'Warming':pct(r.selected_score)},
        {key:'reason',label:'Why'},
        {key:'observed_at',label:'Observed (UTC epoch)'},
      ]}/>
      <DataTable rows={auto.instances||[]} columns={[
        {key:'id',label:'Auto strategy instance'},
        {key:'symbol',label:'Stock'},
        {key:'selected_strategy',label:'Selected policy',render:r=>r.decision?.selected_strategy?displayName(r.decision.selected_strategy):'Comparing'},
        {key:'readiness',label:'Readiness',render:r=><Readiness value={r.readiness}/>},
        {key:'net_quantity',label:'Position',render:r=>r.financial_position?.net_quantity??0},
        {key:'net_pnl',label:'Net P&L',render:r=><Money value={r.financial_position.net_pnl}/>},
        {key:'charges',label:'Charges',render:r=><Money value={r.financial_position.charges}/>},
        {key:'decision',label:'Decision / risk',render:r=><span>{r.decision?.action||'HOLD'} · {r.decision?.result||'NOT SUBMITTED'}</span>},
        {key:'latest_order',label:'Latest order',render:r=>r.latest_order?`${r.latest_order.side} ${r.latest_order.quantity} · ${r.latest_order.status}`:'No broker order'},
      ]}/>
    </Card>
    <div className="grid strategy-grid">
      <Card title="Strategy instances" meta={`${visibleRows.length} shown · ${rows.length} total`}>
        <div className="success strategy-explanation"><b>Why no new trades?</b><span>{activityMessage}</span></div>
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
          <label>Quick select stock<select aria-label="Quick select stock" value={stockChoice} disabled={symbols.length>=MAX_BATCH_SYMBOLS} onChange={event=>{const value=event.target.value;setStockChoice('');if(value)addSymbols(value)}}><option value="">Choose a stock…</option>{observedSymbols.length>0&&<optgroup label="Available from backend/provider">{observedSymbols.map(symbol=><option value={symbol} key={`observed-${symbol}`} disabled={symbols.includes(symbol)}>{symbol}</option>)}</optgroup>}</select><small>This list comes from authenticated backend/provider inventory and observed market evidence.</small></label>
          <label>Or enter stocks<div className="input-action"><input aria-label="Stocks" placeholder="RELIANCE, TCS, INFY" value={symbolInput} onChange={event=>setSymbolInput(event.target.value.toUpperCase())} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();addSymbols(symbolInput,{clearInput:true})}}}/><button type="button" onClick={()=>addSymbols(symbolInput,{clearInput:true})} disabled={!symbolInput.trim()||symbols.length>=MAX_BATCH_SYMBOLS}>Add</button></div><small>Paste comma-separated symbols or add one at a time. Maximum {MAX_BATCH_SYMBOLS}.</small></label>
          <div className="chips" aria-label="Selected stocks">{symbols.map(symbol=><button type="button" className="chip" key={symbol} onClick={()=>removeSymbol(symbol)} aria-label={`Remove ${symbol}`}>{symbol} ×</button>)}</div>
          {symbols.length>0&&<div className="instance-preview"><b>Instances to create</b>{symbols.map(symbol=><code key={symbol}>{previewPrefix}-{idFragment(symbol)} <span>→ {symbol}</span></code>)}</div>}
          <button className="primary" disabled={!strategies.length||!symbols.length||!!pending}>{pending==='batch'?`Creating ${symbols.length} strategy ${symbols.length===1?'instance':'instances'}…`:symbols.length===0?'Select stocks to continue':symbols.length===1?'Create strategy':`Run on ${symbols.length} stocks`}</button>
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
