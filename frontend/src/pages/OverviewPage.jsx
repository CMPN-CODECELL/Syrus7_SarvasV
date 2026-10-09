import { useOutletContext } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import { Card, DataTable, Empty, Money, Page, Readiness, Status } from '../components/UI'
import { strategyRows } from '../domain/snapshot'
import { CandleChart } from '../components/CandleChart'

const actionLabels={
  '/api/demo':'Run replay',
  '/api/reconcile':'Reconcile',
  '/api/resume':'Resume',
  '/api/kill/reset':'Reset kill latch',
}

export function OverviewPage(){
  const {snapshot:s,refresh,accountId}=useOutletContext()
  const {user,refresh:refreshAuth}=useAuth()||{}
  const isOperator=Boolean(user?.is_operator)
  const [pending,setPending]=useState('')
  const [error,setError]=useState('')
  if(!s)return <Empty>Waiting for authenticated backend state…</Empty>
  const proof=s.safety_proof||{}
  const rows=strategyRows(s)
  const positions=s.positions||[]
  const portfolioPnl=positions.reduce((total,row)=>total+Number(row.net_pnl??row.financial_position?.net_pnl??0),0)
  const openQuantity=positions.reduce((total,row)=>total+Math.abs(Number(row.net_quantity??row.financial_position?.net_quantity??0)),0)
  const activePositions=positions.filter(row=>Number(row.net_quantity??row.financial_position?.net_quantity??0)!==0).length
  const activeStocks=new Set((s.subscriptions||[]).filter(item=>item.enabled).map(item=>item.symbol)).size
  const isKillLatched=Boolean(s.safety?.kill_latched||s.gate==='KILLED')
  const readiness=s.provider_readiness||{}
  const quotes=s.market_data?.latest_quotes||[]
  const blockReason=readiness.blocking_reason_codes?.[0]||s.safety?.reconciliation?.reason||'RECONCILIATION_REQUIRED'
  const run=async(path)=>{
    if(pending||!isOperator)return
    setPending(path);setError('')
    try{await api.post(path);await refresh()}
    catch(actionError){
      if(actionError?.status===403){await refreshAuth?.()}
      setError(actionError.message||'Action failed.')
    }
    finally{setPending('')}
  }
  const actionButton=(path,className='')=><button disabled={!!pending||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={()=>run(path)} className={className}>{pending===path?'Working…':actionLabels[path]}</button>
  // Older/test snapshots may omit the capability field; only an explicit
  // backend false disables replay. Persistent/live backends send false.
  const replayAction=s.demo_enabled!==false?actionButton('/api/demo','primary'):null
  return <Page className="overview-page" eyebrow="Control plane" title="Account operations" description="Market evidence, execution readiness, and attributed account state." actions={<>{!isOperator&&<span className="muted" style={{fontSize:'0.85rem',alignSelf:'center'}}>Operator required</span>}{replayAction}{actionButton('/api/reconcile')}{isKillLatched&&actionButton('/api/kill/reset')}{actionButton('/api/resume')}</>}>
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="grid overview-market">
      <Card title="Market chart" meta={s.market_data?.source||s.market_data?.label||'Source unavailable'}>
        <CandleChart key={accountId} accountId={accountId} candles={s.candles||[]} formingCandles={s.market_data?.forming_candles||[]} latestQuotes={quotes} marketData={s.market_data||{}} symbols={(s.market_data?.canonical_symbols||s.market_data?.symbols||[])} />
      </Card>
      <Card title="Trading readiness" meta="Market display remains available while trading is gated">
        <div className="readiness-list">
          <div><span>Market feed</span><Status value={s.market_data?.feed_status||'UNKNOWN'}/></div>
          <div><span>Broker connection</span><Status value={readiness.connectivity?.broker?.status||'UNKNOWN'}/></div>
          <div><span>Reconciliation</span><Status value={readiness.reconciliation?.status||'UNKNOWN'}/></div>
          <div><span>Trading gate</span><Status value={s.gate||'UNKNOWN'}/></div>
        </div>
        {s.gate!=='RUNNING'&&<p className="gate-explanation">New exposure is blocked: {String(blockReason).replaceAll('_',' ').toLowerCase()}. Reconciliation and explicit operator resume are required when broker evidence is available.</p>}
        <p className="muted">{s.market_data?.accepted_ticks??0} accepted · {s.market_data?.duplicate_ticks??0} duplicate · {s.market_data?.rejected_observations??0} rejected. Feed age: {s.market_data?.feed_age_seconds==null?'unavailable':`${Math.floor(s.market_data.feed_age_seconds)}s`}.</p>
      </Card>
    </div>
    <div className="stat-grid">
      <Card title="Trading gate"><Status value={s.gate}/><p>{isKillLatched?'Kill switch is latched. Reconcile, then use the verified operator reset.':'New exposure follows the global gate.'}</p></Card>
      <Card title="Reconciliation"><Status value={s.health}/><p>{s.safety?.reconciliation?.reason||'No report'}</p></Card>
      <Card title="Execution evidence"><strong>{s.counts?.orders??0} · {s.counts?.fills??0}</strong><p>orders · unique fills</p></Card>
      <Card title="Market data"><strong>{s.market_data?.accepted_ticks??0}</strong><p>{s.market_data?.duplicate_ticks??0} duplicate · {s.market_data?.late_ticks??0} late</p></Card>
      <Card title="Active stocks"><strong>{activeStocks}</strong><p>unique enabled symbols</p></Card>
      <Card title="Strategy instances"><strong>{s.subscriptions?.length??0}</strong><p>independent symbol-level ledgers</p></Card>
    </div>
    <Card title="Portfolio overview" meta="Derived from authenticated strategy positions"><div className="stat-grid"><div><span className="muted">Open positions</span><strong>{activePositions}</strong></div><div><span className="muted">Gross quantity</span><strong>{openQuantity}</strong></div><div><span className="muted">Net P&amp;L</span><Money value={portfolioPnl}/></div></div><p className="muted">Funds, margin, holdings, IPO and GTT balances require provider endpoints that are not part of the documented 021 developer API.</p></Card>
    <div className="grid two">
      <Card title="Subscribed strategies" meta={`${s.subscriptions?.length||0} configured`}>
        <DataTable rows={rows} columns={[
          {key:'id',label:'Strategy'},
          {key:'state',label:'State',render:r=><Status value={r.state}/>},
          {key:'readiness',label:'Readiness',render:r=><Readiness value={r.readiness}/>},
          {key:'net_quantity',label:'Position',render:r=>r.financial_position?.net_quantity??'—'},
          {key:'net_pnl',label:'Net P&L',render:r=><Money value={r.financial_position?.net_pnl}/>},
          {key:'charges',label:'Charges',render:r=><Money value={r.financial_position?.charges}/>},
        ]}/>
      </Card>
      <Card title="Safety proof" meta={proof.generated_at??'Not generated'}>
        <div className="proof"><Status value={proof.verdict}/><p>{Array.isArray(proof.invariants)?`${proof.invariants.length} backend invariant results.`:'Invariant evidence unavailable.'}</p></div>
      </Card>
    </div>
  </Page>
}
