import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks=vi.hoisted(()=>({get:vi.fn()}))
vi.mock('../api/client',()=>({api:{get:mocks.get}}))

import { CandleChart } from '../components/CandleChart'

describe('authenticated market chart',()=>{
  beforeEach(()=>mocks.get.mockReset().mockResolvedValue([]))

  it('loads selected historical timeframe and renders backend closed and forming bars in order',async()=>{
    mocks.get.mockResolvedValue([
      {symbol:'TCS',interval:60,start_time:120,open:'10',high:'12',low:'9',close:'11',data_source:'MOCK_REPLAY',is_closed:true},
      {symbol:'TCS',interval:60,start_time:60,open:'9',high:'11',low:'8',close:'10',data_source:'MOCK_REPLAY',is_closed:true},
    ])
    const {container}=render(<CandleChart
      accountId="acc_a"
      symbols={['TCS']}
      candles={[]}
      formingCandles={[{symbol:'TCS',interval:60,start_time:180,open:'11',high:'13',low:'10',close:'12',data_source:'MOCK_REPLAY',is_closed:false}]}
      latestQuotes={[{symbol:'TCS',price:'12',received_at:100,event_timestamp:99,data_source:'MOCK_REPLAY',age_seconds:0,stale:false}]}
      marketData={{feed_status:'MOCK_REPLAY',source:'MOCK_REPLAY'}}
    />)
    await waitFor(()=>expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('interval=60')))
    expect(await screen.findByText(/3 bars · 1m/)).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(container.querySelectorAll('.candle')).toHaveLength(3)
    expect(container.querySelector('.candle.forming')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Chart timeframe'),'300')
    await waitFor(()=>expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('interval=300')))
  })

  it('shows the latest valid quote when there is no closed candle',async()=>{
    render(<CandleChart
      symbols={['RELIANCE']}
      latestQuotes={[{symbol:'RELIANCE',price:'2500.50',received_at:100,event_timestamp:99,data_source:'021_LIVE',age_seconds:3,stale:false}]}
      marketData={{feed_status:'LIVE',chart_data_reason:'NO_CLOSED_CANDLE_YET'}}
    />)
    expect(await screen.findByText('2500.50')).toBeInTheDocument()
    expect(screen.getByText('021_LIVE')).toBeInTheDocument()
    expect(screen.getByText(/No candle has closed/)).toBeInTheDocument()
  })
})
