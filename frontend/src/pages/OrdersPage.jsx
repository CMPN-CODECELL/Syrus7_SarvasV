import { useOutletContext } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../api/client'
import { Card, DataTable, Money, Page, Status } from '../components/UI'

export function OrdersPage() {
  const {snapshot:s,refresh}=useOutletContext()
  const [pending,setPending]=useState('')
  const [error,setError]=useState('')
  const cancel=async order=>{
    if(pending||!confirm(`Cancel order ${order.id}?`))return
    setPending(order.id);setError('')
    try{await api.post(`/api/orders/${order.id}/cancel`);await refresh()}
    catch(e){setError(e.message||'Order cancellation failed.')}
    finally{setPending('')}
  }
  return <Page eyebrow="Execution" title="Orders and fills" description="Orders are requests. Only broker fills move positions and financial truth.">
    {error&&<div className="error" role="alert">{error}</div>}
    <Card title="Orders"><DataTable rows={s?.orders} columns={[
      {key:'id',label:'Order ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'side',label:'Side'},
      {key:'quantity',label:'Executed / requested',render:r=>`${r.filled??'Unknown'} / ${r.quantity??'Unknown'}`},
      {key:'status',label:'Status',render:r=><Status value={r.status}/>},
      {key:'actions',label:'Actions',render:r=>['OPEN','PARTIALLY_FILLED'].includes(r.status)?<button type="button" disabled={!!pending} onClick={()=>cancel(r)}>{pending===r.id?'Cancelling…':'Cancel'}</button>:<span className="muted">—</span>},
    ]}/></Card>
    <Card title="Fill evidence"><DataTable rows={s?.fills} columns={[
      {key:'id',label:'Fill ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'quantity',label:'Qty'},
      {key:'price',label:'Price',render:r=><Money value={r.price}/>},
      {key:'charges',label:'Charges',render:r=><Money value={r.charges}/>},
    ]}/></Card>
  </Page>
}
