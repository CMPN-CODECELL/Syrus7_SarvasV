import { useOutletContext } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../api/client'
import { Card, DataTable, Money, Page, Status } from '../components/UI'

export function OrdersPage() {
  const {snapshot:s,refresh}=useOutletContext()
  const [pending,setPending]=useState('')
  const [error,setError]=useState('')
  const [query,setQuery]=useState('')
  const [displayLimit,setDisplayLimit]=useState(25)
  const cancel=async order=>{
    if(pending||!confirm(`Cancel order ${order.id}?`))return
    setPending(order.id);setError('')
    try{await api.post(`/api/orders/${order.id}/cancel`);await refresh()}
    catch(e){setError(e.message||'Order cancellation failed.')}
    finally{setPending('')}
  }
  const matches=row=>!query.trim()||[row.id,row.strategy,row.symbol,row.status,row.side].filter(Boolean).some(value=>String(value).toLowerCase().includes(query.trim().toLowerCase()))
  const orders=(s?.orders||[]).filter(matches).slice(0,displayLimit)
  const fills=(s?.fills||[]).filter(matches).slice(0,displayLimit)
  return <Page eyebrow="Execution" title="Orders and fills" description="Orders are requests. Only broker fills move positions and financial truth.">
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="filter-row" aria-label="Order filters"><label>Search orders and fills<input aria-label="Search orders and fills" placeholder="Filter by symbol, status, or strategy" value={query} onChange={event=>setQuery(event.target.value)}/></label><label>Show rows<input aria-label="Order rows to display" type="number" min="1" max="200" value={displayLimit} onChange={event=>setDisplayLimit(Math.max(1,Math.min(200,Number(event.target.value)||1)))}/></label></div>
    <Card title="Orders" meta={`${orders.length} shown`}><DataTable rows={orders} columns={[
      {key:'id',label:'Order ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'side',label:'Side'},
      {key:'quantity',label:'Executed / requested',render:r=>`${r.filled??'Unknown'} / ${r.quantity??'Unknown'}`},
      {key:'status',label:'Status',render:r=><Status value={r.status}/>},
      {key:'actions',label:'Actions',render:r=>['OPEN','PARTIALLY_FILLED'].includes(r.status)?<button type="button" disabled={!!pending} onClick={()=>cancel(r)}>{pending===r.id?'Cancelling…':'Cancel'}</button>:<span className="muted">—</span>},
    ]}/></Card>
    <Card title="Fill evidence" meta={`${fills.length} shown`}><DataTable rows={fills} columns={[
      {key:'id',label:'Fill ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'quantity',label:'Qty'},
      {key:'price',label:'Price',render:r=><Money value={r.price}/>},
      {key:'charges',label:'Charges',render:r=><Money value={r.charges}/>},
    ]}/></Card>
  </Page>
}
