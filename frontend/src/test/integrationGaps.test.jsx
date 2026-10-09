import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks=vi.hoisted(()=>({
  get:vi.fn(),
  post:vi.fn(),
  auth:{user:{username:'tester',account_id:'acc_a'},logout:vi.fn()},
  telemetry:{snapshot:{},status:'live',refresh:vi.fn()},
}))
vi.mock('../api/client',()=>({api:{get:mocks.get,post:mocks.post}}))
vi.mock('../auth/AuthContext',()=>({useAuth:()=>mocks.auth}))
vi.mock('../telemetry/TelemetryContext',()=>({useTelemetry:()=>mocks.telemetry}))

import { Money } from '../components/UI'
import { AppShell } from '../components/AppShell'
import { FailureLabPage, MarketDataPage, SafetyBenchPage, TracesPage } from '../pages/EvidencePages'
import { OverviewPage } from '../pages/OverviewPage'
import { StrategiesPage } from '../pages/StrategiesPage'

const snapshot={
  gate:'STOPPED',
  health:'DEGRADED',
  safety:{reconciliation:{reason:'STALE_BROKER_STATE'}},
  safety_proof:{
    verdict:'UNKNOWN',
    generated_at:1700000000,
    invariants:[
      {id:'I1',status:'VERIFIED'},
      {id:'I8',status:'UNKNOWN'},
    ],
  },
  counts:{orders:2,fills:1},
  market_data:{accepted_ticks:12,duplicate_ticks:1,late_ticks:0},
  subscriptions:[
    {id:'alpha',account:'acc_a',kind:'momentum',symbol:'TCS',enabled:1,state:'RUNNING',readiness:{samples:5,warmup:5,ready:true}},
    {id:'zero',account:'acc_a',kind:'mean_reversion',symbol:'INFY',enabled:0,state:'STOPPED',readiness:{samples:0,warmup:5,ready:false}},
    {id:'missing',account:'acc_a',kind:'breakout',symbol:'RELIANCE',enabled:1,state:'READY',readiness:{samples:1,warmup:1,ready:true}},
  ],
  positions:[
    {account_id:'acc_a',strategy_instance_id:'alpha',symbol:'TCS',net_quantity:7,net_pnl:'123.4500',charges:'1.25'},
    {account_id:'acc_a',strategy_instance_id:'zero',symbol:'INFY',net_quantity:0,net_pnl:'0',charges:'0.00'},
    {account_id:'acc_other',strategy_instance_id:'missing',symbol:'RELIANCE',net_quantity:99,net_pnl:'999',charges:'9'},
  ],
}

function renderOutlet(element,context={snapshot,refresh:vi.fn()}){
  return render(<MemoryRouter><Routes><Route element={<Outlet context={context}/> }><Route index element={element}/></Route></Routes></MemoryRouter>)
}

beforeEach(()=>{
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.auth.logout.mockReset()
  mocks.telemetry.refresh.mockReset()
  mocks.telemetry.snapshot={}
  mocks.telemetry.status='live'
  vi.unstubAllGlobals()
})

describe('backend-shaped React projections',()=>{
  it('labels Yahoo quote evidence and unavailable candle volume honestly',()=>{
    renderOutlet(<MarketDataPage/>,{snapshot:{...snapshot,gate:'UNCERTAIN',market_session:{status:'OPEN'},market_data:{...snapshot.market_data,label:'YAHOO EXTERNAL QUOTES / MOCK EXECUTION',connected:true,volume_available:false,last_event_timestamp:1791521395,last_raw_event_timestamp:'1791521395000',last_received_at:1791521397,received_messages:12,accepted_updates:11,errors:['initial subscription deadline exceeded']},candles:[{symbol:'TCS',interval:60,open:'100',high:'101',low:'100',close:'101',volume:0,volume_available:false,data_source:'YAHOO_EXTERNAL_QUOTES'}]}})
    expect(screen.getByText('YAHOO EXTERNAL QUOTES / MOCK EXECUTION')).toBeInTheDocument()
    expect(screen.getByText('Connected · Volume unavailable')).toBeInTheDocument()
    expect(screen.getByText('2026-10-09T04:49:55.000Z')).toBeInTheDocument()
    expect(screen.getByText('Raw: 1791521395000')).toBeInTheDocument()
    expect(screen.getByText('12 received · 11 accepted')).toBeInTheDocument()
    expect(screen.getByText('UNCERTAIN')).toBeInTheDocument()
    expect(screen.getByText('initial subscription deadline exceeded')).toBeInTheDocument()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByText('YAHOO_EXTERNAL_QUOTES')).toBeInTheDocument()
  })

  it('shows configured Yahoo stocks and current quotes without strategy subscriptions',()=>{
    renderOutlet(<MarketDataPage/>,{snapshot:{
      ...snapshot,
      subscriptions:[],
      candles:[],
      market_session:{status:'OPEN'},
      market_data:{
        label:'YAHOO EXTERNAL QUOTES / MOCK EXECUTION',
        connected:true,
        volume_available:false,
        canonical_symbols:['TCS','INFY'],
        latest_quotes:[
          {symbol:'TCS',provider_symbol:'TCS.NS',price:'2190.80',event_timestamp:1791521395,raw_event_timestamp:'1791521395000',received_at:1791521397,volume_available:false,data_source:'YAHOO_EXTERNAL_QUOTES'},
          {symbol:'INFY',provider_symbol:'INFY.NS',price:null,event_timestamp:null,raw_event_timestamp:null,received_at:null,volume_available:false,data_source:'YAHOO_EXTERNAL_QUOTES'},
        ],
      },
    }})
    const selector=screen.getByRole('combobox',{name:'Filter market data by symbol'})
    expect(within(selector).getByRole('option',{name:'TCS'})).toBeInTheDocument()
    expect(within(selector).getByRole('option',{name:'INFY'})).toBeInTheDocument()
    expect(screen.getByText('TCS.NS')).toBeInTheDocument()
    expect(screen.getByText('2190.80')).toBeInTheDocument()
    expect(screen.getByText('INFY.NS')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable')).toHaveLength(2)
  })

  it('uses gate, health, Safety Proof verdict, readiness, and canonical financial joins',()=>{
    renderOutlet(<OverviewPage/>)
    const gateCard=screen.getByText('Trading gate').closest('section')
    expect(within(gateCard).getByText('STOPPED')).toBeInTheDocument()
    expect(screen.getByText('DEGRADED')).toBeInTheDocument()
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
    expect(screen.getByText('2 backend invariant results.')).toBeInTheDocument()

    const alpha=screen.getByText('alpha').closest('tr')
    expect(within(alpha).getByText('7')).toBeInTheDocument()
    expect(within(alpha).getByText('₹123.4500')).toBeInTheDocument()
    expect(within(alpha).getByText('₹1.25')).toBeInTheDocument()
    expect(within(alpha).getByText(/5 \/ 5/)).toBeInTheDocument()
    expect(within(alpha).getByText('READY')).toBeInTheDocument()

    const zero=screen.getByText('zero').closest('tr')
    expect(within(zero).getByText('0')).toBeInTheDocument()
    expect(within(zero).getAllByText('₹0.00')).toHaveLength(2)
    expect(within(zero).getByText(/0 \/ 5/)).toBeInTheDocument()
    expect(within(zero).getByText('WARMING')).toBeInTheDocument()

    const missing=screen.getByText('missing').closest('tr')
    expect(within(missing).getAllByText('—')).toHaveLength(3)
    expect(within(missing).queryByText('99')).not.toBeInTheDocument()
  })

  it('keeps missing, invalid, zero, and exact decimal money distinct',()=>{
    const {rerender}=render(<Money value={undefined}/>)
    expect(screen.getByText('—')).toBeInTheDocument()
    rerender(<Money value="not-a-decimal"/>);expect(screen.getByText('Unavailable')).toBeInTheDocument()
    rerender(<Money value="0"/>);expect(screen.getByText('₹0.00')).toBeInTheDocument()
    rerender(<Money value="-12.345600"/>);expect(screen.getByText('−₹12.345600')).toBeInTheDocument()
  })

  it('renders actual trace fields instead of nonexistent status and started_at',async()=>{
    mocks.get.mockResolvedValue([{trace_id:'order-1',strategy_instance_id:'alpha',account_id:'acc_a',events:[{sequence:4,type:'ORDER_SUBMITTED',recorded_at:1700000001,payload:{}}]}])
    render(<MemoryRouter><TracesPage/></MemoryRouter>)
    const row=(await screen.findByText('order-1')).closest('tr')
    expect(within(row).getByText('alpha')).toBeInTheDocument()
    expect(within(row).getByText('acc_a')).toBeInTheDocument()
    expect(within(row).getByText('1')).toBeInTheDocument()
    expect(within(row).getByText('1700000001')).toBeInTheDocument()
    expect(within(row).queryByText('UNKNOWN')).not.toBeInTheDocument()
  })
})

describe('rejected and mutating actions',()=>{
  it.each([
    ['Run replay','/api/demo'],
    ['Reconcile','/api/reconcile'],
    ['Resume','/api/resume'],
  ])('reports a rejected %s action and reenables controls',async(label,path)=>{
    const user=userEvent.setup()
    mocks.post.mockRejectedValueOnce(new Error(`${label} denied`))
    renderOutlet(<OverviewPage/>)
    await user.click(screen.getByRole('button',{name:label}))
    expect(await screen.findByRole('alert')).toHaveTextContent(`${label} denied`)
    expect(mocks.post).toHaveBeenCalledWith(path)
    expect(screen.getByRole('button',{name:label})).toBeEnabled()
  })

  it('shows subscription errors and prevents duplicate control submissions',async()=>{
    const user=userEvent.setup()
    mocks.get.mockResolvedValue([{kind:'momentum',description:'Momentum'}])
    let rejectAction
    mocks.post.mockImplementation(()=>new Promise((_,reject)=>{rejectAction=reject}))
    renderOutlet(<StrategiesPage/>)
    const alphaRow=screen.getByText('alpha').closest('tr')
    await user.click(within(alphaRow).getByRole('button',{name:'Stop'}))
    expect(screen.getByRole('button',{name:'Working…'})).toBeDisabled()
    await user.click(screen.getByRole('button',{name:'Working…'}))
    expect(mocks.post).toHaveBeenCalledTimes(1)
    rejectAction(new Error('Subscription denied'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Subscription denied')
  })

  it('requires confirmation and truthfully labels Failure Lab current-platform impact',async()=>{
    const user=userEvent.setup()
    mocks.get.mockResolvedValue({scenarios:['partial']})
    vi.stubGlobal('confirm',vi.fn(()=>false))
    render(<MemoryRouter><FailureLabPage/></MemoryRouter>)
    expect(await screen.findByText('Run on current mock platform')).toBeInTheDocument()
    expect(screen.getByText(/mutate the current mock platform/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button',{name:/partial/i}))
    expect(confirm).toHaveBeenCalledOnce()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('reports SafetyBench failures and restores its action',async()=>{
    const user=userEvent.setup()
    mocks.get.mockRejectedValue(Object.assign(new Error('none'),{status:404}))
    mocks.post.mockRejectedValue(new Error('Benchmark unavailable'))
    render(<MemoryRouter><SafetyBenchPage/></MemoryRouter>)
    await user.click(screen.getByRole('button',{name:'Run benchmark'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Benchmark unavailable')
    expect(screen.getByRole('button',{name:'Run benchmark'})).toBeEnabled()
  })
})

describe('kill action',()=>{
  it('preserves confirmation and reports a rejected kill',async()=>{
    const user=userEvent.setup()
    vi.stubGlobal('confirm',vi.fn(()=>true))
    mocks.post.mockRejectedValue(new Error('Kill refused'))
    render(<MemoryRouter><Routes><Route element={<AppShell/>}><Route index element={<div>Overview</div>}/></Route></Routes></MemoryRouter>)
    await user.click(screen.getByRole('button',{name:'Kill all strategies'}))
    expect(confirm).toHaveBeenCalledOnce()
    expect(await screen.findByRole('alert')).toHaveTextContent('Kill refused')
    expect(screen.getByRole('button',{name:'Kill all strategies'})).toBeEnabled()
  })
})
