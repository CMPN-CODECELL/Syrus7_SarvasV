import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('../api/client',()=>({api:{get:mocks.get,post:mocks.post}}))

import { StrategiesPage } from '../pages/StrategiesPage'

function renderPage(refresh=vi.fn(),snapshot={subscriptions:[],positions:[],market_data:{canonical_symbols:['RELIANCE','TCS','INFY']}}){
  const context={snapshot,refresh}
  return render(<MemoryRouter><Routes><Route element={<Outlet context={context}/> }><Route index element={<StrategiesPage/>}/></Route></Routes></MemoryRouter>)
}

beforeEach(()=>{
  mocks.get.mockReset().mockResolvedValue([{kind:'momentum',description:'Momentum'}])
  mocks.post.mockReset()
})

describe('multi-stock strategy creation',()=>{
  it('shows auto-mode policy, honest decisions, and starts it through the backend',async()=>{
    const user=userEvent.setup()
    const refresh=vi.fn().mockResolvedValue()
    mocks.post.mockResolvedValue({enabled:true})
    renderPage(refresh,{
      subscriptions:[{id:'auto-hidden',account:'acc_a',kind:'auto_adaptive',symbol:'TCS',enabled:1,state:'READY',readiness:{samples:0,warmup:1,ready:false}}],positions:[],
      auto_mode:{enabled:false,state:'STOPPED',execution_state:'BLOCKED',blocking_reasons:['NO_EXECUTION_DEMAND'],candidate_count:200,evaluated_count:12,funnel:{observations:12,evaluations:12,ready_evaluations:4,signals:0,risk_admitted:0,orders:0,fills:0},hold_reasons:{'no entry or exit threshold crossed':4},selected_symbol:'TCS',selected_strategy:'mean_reversion',selected_strategy_instance_id:'auto-hidden',policy:{max_positions:3,entry_momentum:'0.003',take_profit:'0.01',stop_loss:'0.005'},decisions:[{symbol:'TCS',selected_strategy:'mean_reversion',action:'HOLD',result:null,momentum:'0.002',reason:'no entry or exit threshold crossed',observed_at:123}],instances:[{id:'auto-hidden',kind:'auto_adaptive',symbol:'TCS',readiness:{samples:5,warmup:5,ready:true},financial_position:{net_quantity:0,net_pnl:'0',charges:'0'},decision:{selected_strategy:'mean_reversion',action:'HOLD',result:null},latest_order:null}]},
      provider_readiness:{actions:{new_exposure:{status:'BLOCKED',reason_code:'READINESS_NOT_VERIFIED'}},blocking_reason_codes:['NO_EXECUTION_DEMAND']},
    })
    expect(screen.getByText('Profit is not guaranteed.')).toBeInTheDocument()
    expect(screen.getAllByText('TCS').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Mean Reversion').length).toBeGreaterThan(0)
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getAllByText(/auto-hidden/).length).toBeGreaterThan(0)
    expect(screen.getByText('No broker order')).toBeInTheDocument()
    expect(screen.getByLabelText('Automatic trading funnel')).toHaveTextContent('Ready Evaluations4')
    expect(screen.getByRole('status')).toHaveTextContent('NO_EXECUTION_DEMAND')
    await user.click(screen.getByRole('button',{name:'Start auto mode'}))
    expect(mocks.post).toHaveBeenCalledWith('/api/auto-mode/start')
    expect(refresh).toHaveBeenCalledOnce()
  })

  it('adds stocks from a clearly labeled quick-select dropdown',async()=>{
    const user=userEvent.setup()
    renderPage()
    const dropdown=await screen.findByRole('combobox',{name:'Quick select stock'})
    await user.selectOptions(dropdown,'RELIANCE')
    expect(screen.getByRole('button',{name:'Remove RELIANCE'})).toBeInTheDocument()
    expect(screen.getByText(/momentum-reliance/)).toBeInTheDocument()
    expect(screen.getByText(/authenticated backend\/provider inventory/i)).toBeInTheDocument()
    expect(within(dropdown).getByRole('option',{name:'RELIANCE'})).toBeDisabled()
  })

  it('normalizes, deduplicates, previews, removes, and sends one atomic request',async()=>{
    const user=userEvent.setup()
    const refresh=vi.fn().mockResolvedValue()
    mocks.post.mockResolvedValue({count:2,symbols:['RELIANCE','ABC.NS'],created:[]})
    renderPage(refresh)

    const input=await screen.findByRole('textbox',{name:'Stocks'})
    await user.type(input,'reliance, RELIANCE, tcs, abc.ns')
    await user.click(screen.getByRole('button',{name:'Add'}))
    expect(screen.getByRole('button',{name:'Remove RELIANCE'})).toBeInTheDocument()
    expect(screen.getByText(/momentum-abc-ns/)).toBeInTheDocument()

    await user.click(screen.getByRole('button',{name:'Remove TCS'}))
    await user.click(screen.getByRole('button',{name:'Run on 2 stocks'}))
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/api/subscriptions/batch',{
      kind:'momentum',
      symbols:['RELIANCE','ABC.NS'],
      instance_prefix:'momentum',
    })
    expect(refresh).toHaveBeenCalledOnce()
    const status=await screen.findByRole('status')
    expect(status).toHaveTextContent('Created 2 strategy instances.')
    expect(status).toHaveTextContent('RELIANCE, ABC.NS')
    expect(screen.queryByRole('button',{name:'Remove RELIANCE'})).not.toBeInTheDocument()
  })

  it('shows atomic conflict detail and preserves the selected set',async()=>{
    const user=userEvent.setup()
    mocks.post.mockRejectedValue(Object.assign(new Error('SUBSCRIPTION_BATCH_CONFLICT'),{
      status:409,
      detail:{code:'SUBSCRIPTION_BATCH_CONFLICT',existing:['momentum-tcs']},
    }))
    renderPage()
    const input=await screen.findByRole('textbox',{name:'Stocks'})
    await user.type(input,'TCS, INFY')
    await user.click(screen.getByRole('button',{name:'Add'}))
    await user.click(screen.getByRole('button',{name:'Run on 2 stocks'}))
    const alert=await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Already exists: momentum-tcs')
    expect(alert).toHaveTextContent('Nothing was created')
    expect(within(screen.getByLabelText('Selected stocks')).getByRole('button',{name:'Remove INFY'})).toBeInTheDocument()
  })

  it('shows the exact in-flight instance count and blocks duplicate submission',async()=>{
    const user=userEvent.setup()
    let resolveRequest
    mocks.post.mockImplementation(()=>new Promise(resolve=>{resolveRequest=resolve}))
    renderPage()
    const input=await screen.findByRole('textbox',{name:'Stocks'})
    await user.type(input,'TCS, INFY')
    await user.click(screen.getByRole('button',{name:'Add'}))
    await user.click(screen.getByRole('button',{name:'Run on 2 stocks'}))
    const pending=screen.getByRole('button',{name:'Creating 2 strategy instances…'})
    expect(pending).toBeDisabled()
    await user.click(pending)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    resolveRequest({count:2,symbols:['TCS','INFY'],created:[]})
    expect(await screen.findByRole('status')).toHaveTextContent('Created 2 strategy instances')
  })

  it('uses the single-stock label and bounds client selection to twenty',async()=>{
    const user=userEvent.setup()
    renderPage()
    const input=await screen.findByRole('textbox',{name:'Stocks'})
    await user.type(input,'TCS')
    await user.click(screen.getByRole('button',{name:'Add'}))
    expect(screen.getByRole('button',{name:'Create strategy'})).toBeEnabled()

    await user.type(input,Array.from({length:20},(_,index)=>`S${index}`).join(','))
    await user.click(screen.getByRole('button',{name:'Add'}))
    expect(screen.getByRole('alert')).toHaveTextContent('no more than 20')
  })
})
