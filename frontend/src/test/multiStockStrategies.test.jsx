import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('../api/client',()=>({api:{get:mocks.get,post:mocks.post}}))

import { StrategiesPage } from '../pages/StrategiesPage'

function renderPage(refresh=vi.fn()){
  const context={snapshot:{subscriptions:[],positions:[]},refresh}
  return render(<MemoryRouter><Routes><Route element={<Outlet context={context}/> }><Route index element={<StrategiesPage/>}/></Route></Routes></MemoryRouter>)
}

beforeEach(()=>{
  mocks.get.mockReset().mockResolvedValue([{kind:'momentum',description:'Momentum'}])
  mocks.post.mockReset()
})

describe('multi-stock strategy creation',()=>{
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
