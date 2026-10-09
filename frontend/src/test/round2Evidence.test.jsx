import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { OrdersPage } from '../pages/OrdersPage'
import { StrategiesPage } from '../pages/StrategiesPage'

vi.mock('../api/client',()=>({api:{get:vi.fn().mockResolvedValue([]),post:vi.fn()}}))

function View({snapshot,children}) {
  return <MemoryRouter><Routes><Route element={<Outlet context={{snapshot,refresh:vi.fn()}}/>}><Route index element={children}/></Route></Routes></MemoryRouter>
}

it('shows backend executed/requested quantities without guessing missing execution',()=>{
  render(<View snapshot={{orders:[
    {id:'partial',filled:40,quantity:100,status:'PARTIALLY_FILLED'},
    {id:'rejected',filled:0,quantity:100,status:'REJECTED'},
    {id:'full',filled:100,quantity:100,status:'FILLED'},
    {id:'cancelled',filled:60,quantity:100,status:'CANCELLED'},
    {id:'unknown',quantity:100,status:'UNKNOWN'},
  ]}}><OrdersPage/></View>)
  for(const value of ['40 / 100','0 / 100','100 / 100','60 / 100','Unknown / 100'])expect(screen.getByText(value)).toBeInTheDocument()
})

it('renders scoped candle-linked signals and clears them on account/session change',()=>{
  const snapshot={subscriptions:[],signals:[{intent_id:'signal-a',strategy:'alpha',symbol:'TCS',side:'BUY',interval:300,reason:'range break',candle_start:1700000100}]}
  const view=render(<View snapshot={snapshot}><StrategiesPage/></View>)
  const signals=screen.getByText('Emitted signals').closest('section')
  for(const value of ['alpha','TCS','BUY','300','range break','1700000100'])expect(within(signals).getByText(value)).toBeInTheDocument()
  view.rerender(<View snapshot={{subscriptions:[],signals:[]}}><StrategiesPage/></View>)
  expect(screen.queryByText('range break')).not.toBeInTheDocument()
  view.rerender(<View snapshot={null}><StrategiesPage/></View>)
  expect(screen.queryByText('alpha')).not.toBeInTheDocument()
})
