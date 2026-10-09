import { render,screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach,describe,expect,it,vi } from 'vitest'

vi.mock('../api/client',()=>({api:{get:vi.fn(),post:vi.fn()}}))

import { api } from '../api/client'
import { FailureLabPage } from '../pages/EvidencePages'

describe('Failure Lab trader guidance',()=>{
  beforeEach(()=>{
    vi.clearAllMocks()
    vi.stubGlobal('confirm',vi.fn(()=>true))
  })

  it('renders the failure lab scenarios and header',async()=>{
    api.get.mockResolvedValue({scenarios:['partial']})
    render(<FailureLabPage/> )
    expect(await screen.findByText('Partial order fill')).toBeInTheDocument()
    expect(screen.getByText('What would you like to test?')).toBeInTheDocument()
  })

  it('shows an honest running state and a plain-language result',async()=>{
    const user=userEvent.setup()
    let finish
    api.get.mockResolvedValue({scenarios:['partial']})
    api.post.mockReturnValue(new Promise(resolve=>{finish=resolve}))
    render(<FailureLabPage/> )
    await user.click(await screen.findByRole('button',{name:'Run Partial order fill mock test'}))
    expect(screen.getByRole('status')).toHaveTextContent('Waiting for verified backend evidence')
    finish({scenario:'partial',status:'PASS',duration_ms:18.7,decisions:[{reason_code:'ALLOWED'}],state:{gate:'STOPPED',health:'HEALTHY'},evidence:{filled:40}})
    expect(await screen.findByText('Protection worked as expected')).toBeInTheDocument()
    expect(screen.getByText(/unfilled quantity did not become a position/i)).toBeInTheDocument()
    expect(screen.getByText('Trading is stopped; review the result before resuming.')).toBeInTheDocument()
    expect(screen.getByText('Order passed the risk checks.')).toBeInTheDocument()
    expect(screen.getByText('View technical evidence')).toBeInTheDocument()
  })
})
