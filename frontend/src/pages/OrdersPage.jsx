import { useOutletContext } from 'react-router-dom'
import { Card, DataTable, Money, Page, Status } from '../components/UI'

export function OrdersPage() {
  const {snapshot:s}=useOutletContext()
  return <Page eyebrow="Execution" title="Orders and fills" description="Orders are requests. Only broker fills move positions and financial truth.">
    <Card title="Orders"><DataTable rows={s?.orders} columns={[
      {key:'id',label:'Order ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'side',label:'Side'},
      {key:'quantity',label:'Executed / requested',render:r=>`${r.filled??'Unknown'} / ${r.quantity??'Unknown'}`},
      {key:'status',label:'Status',render:r=><Status value={r.status}/>},
    ]}/></Card>
    <Card title="Fill evidence"><DataTable rows={s?.fills} columns={[
      {key:'id',label:'Fill ID'}, {key:'strategy',label:'Strategy'},
      {key:'symbol',label:'Symbol'}, {key:'quantity',label:'Qty'},
      {key:'price',label:'Price',render:r=><Money value={r.price}/>},
      {key:'charges',label:'Charges',render:r=><Money value={r.charges}/>},
    ]}/></Card>
  </Page>
}
