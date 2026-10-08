import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Card, DataTable, Money, Page, Readiness, Status } from '../components/UI'
import { strategyRows } from '../domain/snapshot'

const displayName=value=>String(value).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())

export function StrategiesPage(){
  const {snapshot:s,refresh}=useOutletContext()
  const [strategies,setStrategies]=useState([])
  const [form,setForm]=useState({strategy_instance_id:'',kind:'',symbol:''})
  const [pending,setPending]=useState('')
  const [error,setError]=useState('')

  useEffect(()=>{
    let active=true
    api.get('/api/strategies').then(items=>{
      if(!active)return
      const available=Array.isArray(items)?items:[]
      setStrategies(available)
      if(available.length)setForm(current=>({...current,kind:current.kind||available[0].kind}))
    }).catch(loadError=>{if(active){setStrategies([]);setError(loadError.message||'Unable to load strategy types.')}})
    return()=>{active=false}
  },[])

  const mutate=async(path,body,key=path)=>{
    if(pending)return
    setPending(key);setError('')
    try{await api.post(path,body);await refresh()}
    catch(actionError){setError(actionError.message||'Strategy action failed.')}
    finally{setPending('')}
  }

  const rows=strategyRows(s)
  return <Page eyebrow="Subscriptions" title="Independent strategy ledgers" description="Each strategy keeps its own attributed position and P&L, even on the same symbol.">
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="grid strategy-grid">
      <Card title="Subscribed strategies">
        <DataTable rows={rows} columns={[
          {key:'id',label:'Strategy'},
          {key:'kind',label:'Kind'},
          {key:'symbol',label:'Symbol'},
          {key:'state',label:'State',render:r=><Status value={r.state}/>},
          {key:'readiness',label:'Readiness',render:r=><Readiness value={r.readiness}/>},
          {key:'net_quantity',label:'Position',render:r=>r.financial_position?.net_quantity??'—'},
          {key:'net_pnl',label:'Net P&L',render:r=><Money value={r.financial_position?.net_pnl}/>},
          {key:'charges',label:'Charges',render:r=><Money value={r.financial_position?.charges}/>},
          {key:'control',label:'Control',render:r=>{
            const key=`control:${r.id}`
            return <button disabled={!!pending} onClick={()=>mutate(`/api/subscriptions/${r.id}/${r.enabled?'stop':'start'}`,undefined,key)}>{pending===key?'Working…':r.enabled?'Stop':'Start'}</button>
          }},
        ]}/>
      </Card>
      <Card title="Add strategy" meta="Uses signed-in account">
        <form onSubmit={event=>{event.preventDefault();mutate('/api/subscriptions',form,'subscribe')}}>
          <label>Strategy instance ID<input required placeholder="Unique strategy name" value={form.strategy_instance_id} onChange={event=>setForm({...form,strategy_instance_id:event.target.value})}/></label>
          <div className="form-row">
            <label>Strategy<select required value={form.kind} onChange={event=>setForm({...form,kind:event.target.value})}>{strategies.map(strategy=><option value={strategy.kind} key={strategy.kind}>{strategy.description||displayName(strategy.kind)}</option>)}</select></label>
            <label>Symbol<input required placeholder="Trading symbol" value={form.symbol} onChange={event=>setForm({...form,symbol:event.target.value.toUpperCase()})}/></label>
          </div>
          <button className="primary" disabled={!strategies.length||!!pending}>{pending==='subscribe'?'Subscribing…':'Subscribe strategy'}</button>
        </form>
      </Card>
    </div>
  </Page>
}
