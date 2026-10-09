import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Card, CompactEvidence, DataTable, Empty, EvidenceView, Page, Status } from '../components/UI'

function RemotePage({endpoint,eyebrow,title,description,render}){
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    let active=true
    setData(null);setError('')
    api.get(endpoint).then(value=>{if(active)setData(value)}).catch(loadError=>{
      if(active)setError(loadError.status===404?'No completed evidence yet.':loadError.message)
    })
    return()=>{active=false}
  },[endpoint])
  return <Page eyebrow={eyebrow} title={title} description={description}>{error?<Empty>{error}</Empty>:data?render(data):<Empty>Loading backend evidence…</Empty>}</Page>
}

const reconciliationLabel=value=>String(value).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())
const hasReconciliationDetails=value=>value&&typeof value==='object'&&(Array.isArray(value)?value.length>0:Object.keys(value).length>0)
const reconciliationSections=value=>({summary:Object.fromEntries(Object.entries(value||{}).filter(([,item])=>!item||typeof item!=='object')),details:Object.entries(value||{}).filter(([,item])=>hasReconciliationDetails(item))})

export function ReconciliationView({data}){
  const report=data.report||{}
  const reportSections=reconciliationSections(report)
  const comparisonSections=reconciliationSections(data.position_comparison)
  const events=(data.events||[]).map(event=>({...event,payload:auditEvidence(event.payload)}))
  return <>
    <div className="reconciliation-summary">
      <Card title="Verification"><Status value={report.verified?'VERIFIED':'FAILED'}/></Card>
      <Card title="Reason"><strong>{report.reason||'UNKNOWN'}</strong></Card>
      <Card title="Unknown orders"><strong>{data.unknown_orders?.length||0}</strong></Card>
    </div>
    <div className="reconciliation-stack">
      <Card title="Position comparison">
        <CompactEvidence value={comparisonSections.summary}/>
        {comparisonSections.details.length>0?<div className="reconciliation-details">{comparisonSections.details.map(([name,value])=><section key={name}><h3>{reconciliationLabel(name)}</h3><EvidenceView value={value} name={name}/></section>)}</div>:<p className="reconciliation-clear">No broker or virtual position differences reported.</p>}
      </Card>
      <Card title="Broker evidence"><CompactEvidence value={data.broker}/></Card>
      <Card title="Recovery report">
        <CompactEvidence value={reportSections.summary}/>
        {reportSections.details.length>0&&<div className="reconciliation-details">{reportSections.details.map(([name,value])=><section key={name}><h3>{reconciliationLabel(name)}</h3><EvidenceView value={value} name={name}/></section>)}</div>}
      </Card>
      {events.length>0&&<Card title="Recent reconciliation events"><EvidenceView value={events} name="events"/></Card>}
    </div>
  </>
}

export function ReconciliationPage() {
  return <RemotePage endpoint="/api/reconciliation" eyebrow="Recovery" title="Reconciliation center" description="Expected local state compared with observed broker truth." render={data => <ReconciliationView data={data} />} />
}

export function TracesPage(){
  return <RemotePage endpoint="/api/traces" eyebrow="Causality" title="Execution traces" description="Server-built timelines connect intent, risk, order, fill, and reconciliation evidence." render={data=><Card title="Recent traces"><DataTable rows={Array.isArray(data)?data:data.traces||[]} columns={[
    {key:'trace_id',label:'Trace'},
    {key:'strategy_instance_id',label:'Strategy'},
    {key:'account_id',label:'Account'},
    {key:'events',label:'Events',render:row=>Array.isArray(row.events)?row.events.length:'—'},
    {key:'recorded_at',label:'First recorded',render:row=>row.events?.[0]?.recorded_at??'—'},
  ]}/></Card>}/>
}

export function FailureLabPage(){
  const [scenarios,setScenarios]=useState([])
  const [result,setResult]=useState(null)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  useEffect(()=>{
    let active=true
    api.get('/api/failure-lab/scenarios').then(data=>{
      if(!Array.isArray(data?.scenarios))throw new Error('Invalid Failure Lab scenario response')
      if(active)setScenarios(data.scenarios)
    }).catch(loadError=>{if(active){setScenarios([]);setError(loadError.message)}})
    return()=>{active=false}
  },[])
  const run=async scenario=>{
    if(busy||!confirm(`Run ${scenario.replaceAll('_',' ')}? This mutates the current mock platform and may change its safety, order, fill, or position state.`))return
    setBusy(scenario);setError('')
    try{setResult(await api.post(`/api/failure-lab/${scenario}`))}
    catch(actionError){setError(actionError.message||'Failure Lab scenario failed.')}
    finally{setBusy('')}
  }
  return <Page eyebrow="Controlled faults" title="Failure Lab" description="Local mock-only scenarios mutate the current mock platform and expose the resulting fail-closed evidence.">
    <p className="muted">Run only when you accept changes to the current mock platform state.</p>
    {error&&<div className="error" role="alert">{error}</div>}
    {scenarios.length?<div className="scenario-grid">{scenarios.map(scenario=><button disabled={!!busy} onClick={()=>run(scenario)} key={scenario}><b>{scenario.replaceAll('_',' ')}</b><span>{busy===scenario?'Running…':'Run on current mock platform'}</span></button>)}</div>:!error&&<Empty>No failure scenarios are available from the backend.</Empty>}
    {result&&<Card title="Scenario evidence"><EvidenceView value={result}/></Card>}
  </Page>
}

export function SafetyBenchPage(){
  const [data,setData]=useState(null)
  const [busy,setBusy]=useState(false)
  const [iterations,setIterations]=useState(25)
  const [error,setError]=useState('')
  useEffect(()=>{
    let active=true
    api.get('/api/safety-bench/latest').then(value=>{if(active)setData(value)}).catch(loadError=>{if(active&&loadError.status!==404)setError(loadError.message)})
    return()=>{active=false}
  },[])
  const run=async()=>{
    if(busy)return
    setBusy(true);setError('')
    try{setData(await api.post('/api/safety-bench/run',{iterations}))}
    catch(actionError){setError(actionError.message||'SafetyBench run failed.')}
    finally{setBusy(false)}
  }
  return <Page eyebrow="Isolated benchmark" title="SafetyBench" description="Bounded reliability tests run on separate in-memory platform instances." actions={<div className="bench-control"><label>Iterations<input type="number" min="1" max="100" value={iterations} onChange={event=>setIterations(Number(event.target.value))}/></label><button className="primary" disabled={busy} onClick={run}>{busy?'Running…':'Run benchmark'}</button></div>}>
    {error&&<div className="error" role="alert">{error}</div>}
    {data?<Card title="Latest completed run"><EvidenceView value={data}/></Card>:<Empty>No completed benchmark run.</Empty>}
  </Page>
}

export function MetricsPage() {
  return <RemotePage endpoint="/api/metrics" eyebrow="Process diagnostics" title="Operational metrics" description="Bounded runtime counters—not financial truth." render={data => <div className="grid two"><Card title="Counters"><EvidenceView value={data.counters || data} /></Card><Card title="Latency observations"><EvidenceView value={data.observations || {}} /></Card></div>} />
}

export function MarketDataPage(){
  const {snapshot:s}=useOutletContext()
  const source=s?.market_data?.label||s?.market_data?.provider||'Unavailable'
  const eventTime=s?.market_data?.last_event_timestamp
  const receivedTime=s?.market_data?.last_received_at
  const asUtc=value=>{
    const numeric=Number(value)
    return value===null||value===undefined||!Number.isFinite(numeric)?'—':new Date(numeric*1000).toISOString()
  }
  return <Page eyebrow="Market ingestion" title="Market data" description="One- and five-minute candles built from normalized updates. Yahoo candles are sampled quote-derived evidence, not complete exchange ticks.">
    <div className="stat-grid">
      <Card title="Source"><strong>{source}</strong><p>{s?.market_data?.connected?'Connected':'Not connected'} · Volume {s?.market_data?.volume_available===false?'unavailable':'available'}</p></Card>
      <Card title="Safety gate"><Status value={s?.gate}/></Card>
      <Card title="Last quote event"><strong>{asUtc(eventTime)}</strong><p>Raw: {s?.market_data?.last_raw_event_timestamp??'—'}</p></Card>
      <Card title="Last received"><strong>{asUtc(receivedTime)}</strong><p>{s?.market_data?.received_messages??'—'} received · {s?.market_data?.accepted_updates??'—'} accepted</p></Card>
      <Card title="Session"><Status value={s?.market_session?.status}/></Card>
      <Card title="Accepted ticks"><strong>{s?.market_data?.accepted_ticks??'—'}</strong></Card>
      <Card title="Duplicates"><strong>{s?.market_data?.duplicate_ticks??'—'}</strong></Card>
      <Card title="Late ticks"><strong>{s?.market_data?.late_ticks??'—'}</strong></Card>
    </div>
    {s?.market_data?.errors?.length?<Card title="Provider lifecycle errors"><EvidenceView value={s.market_data.errors}/></Card>:null}
    <Card title="Closed candles"><DataTable rows={s?.candles} columns={[{key:'symbol',label:'Symbol'},{key:'interval',label:'Interval'},{key:'open',label:'Open'},{key:'high',label:'High'},{key:'low',label:'Low'},{key:'close',label:'Close'},{key:'volume',label:'Volume',render:row=>row.volume_available===false?'Unavailable':String(row.volume??'—')},{key:'data_source',label:'Source'}]}/></Card>
  </Page>
}

function auditEvidence(payload){if(typeof payload!=='string')return payload;try{return JSON.parse(payload)}catch{return payload}}

export function AuditPage(){const {snapshot:s}=useOutletContext();return <Page eyebrow="Durable timeline" title="Audit evidence" description="Monotonic backend events for operational review."><Card title="Recent audit"><DataTable rows={s?.audit} columns={[{key:'sequence',label:'#'},{key:'type',label:'Event'},{key:'recorded_at',label:'Recorded'},{key:'payload',label:'Evidence',render:row=><EvidenceView value={auditEvidence(row.payload)} name="audit evidence"/>}]}/></Card></Page>}
export function NotFoundPage(){return <main className="center"><div><span className="eyebrow">404</span><h1>Route not found</h1><a href="/">Return to overview</a></div></main>}
