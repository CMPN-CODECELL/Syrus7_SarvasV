import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks=vi.hoisted(()=>({apiGet:vi.fn(),auth:{user:{username:'a',account_id:'acc_a'}}}))
vi.mock('../api/client',()=>({api:{get:mocks.apiGet}}))
vi.mock('../auth/AuthContext',()=>({useAuth:()=>mocks.auth}))

import { TelemetryProvider, useTelemetry } from '../telemetry/TelemetryContext'

class FakeWebSocket{
  static instances=[]
  constructor(url){
    this.url=url
    this.closed=false
    FakeWebSocket.instances.push(this)
  }
  close(){this.closed=true}
  open(){this.onopen?.({})}
  message(data){this.onmessage?.({data:JSON.stringify(data)})}
  closeFromServer(code=1006){this.onclose?.({code})}
}

function Probe(){
  const {snapshot,status}=useTelemetry()
  return <><span data-testid="status">{status}</span><span data-testid="account">{snapshot?.account??'none'}</span></>
}

const flush=async()=>{await act(async()=>{await Promise.resolve();await Promise.resolve()})}

beforeEach(()=>{
  vi.useFakeTimers()
  mocks.apiGet.mockReset()
  mocks.auth.user={username:'a',account_id:'acc_a'}
  FakeWebSocket.instances=[]
  vi.stubGlobal('WebSocket',FakeWebSocket)
})

afterEach(()=>{
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('TelemetryProvider recovery and session boundaries',()=>{
  it('retries a transient initial state failure with capped scheduling and opens one socket',async()=>{
    mocks.apiGet.mockRejectedValueOnce(Object.assign(new Error('temporary'),{status:503})).mockResolvedValueOnce({account:'acc_a'})
    render(<TelemetryProvider><Probe/></TelemetryProvider>)
    await flush()
    expect(screen.getByTestId('status')).toHaveTextContent('disconnected')
    expect(FakeWebSocket.instances).toHaveLength(0)

    await act(async()=>{vi.advanceTimersByTime(500)})
    await flush()
    expect(mocks.apiGet).toHaveBeenCalledTimes(2)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(screen.getByTestId('account')).toHaveTextContent('acc_a')
    act(()=>FakeWebSocket.instances[0].open())
    expect(screen.getByTestId('status')).toHaveTextContent('live')
  })

  it('clears old-account state and closes stale sockets on account change and logout',async()=>{
    mocks.apiGet.mockResolvedValueOnce({account:'acc_a'}).mockResolvedValueOnce({account:'acc_b'})
    const view=render(<TelemetryProvider><Probe/></TelemetryProvider>)
    await flush()
    const oldSocket=FakeWebSocket.instances[0]
    act(()=>{oldSocket.open();oldSocket.message({account:'acc_a'})})
    expect(screen.getByTestId('account')).toHaveTextContent('acc_a')

    mocks.auth.user={username:'b',account_id:'acc_b'}
    view.rerender(<TelemetryProvider><Probe/></TelemetryProvider>)
    expect(screen.getByTestId('account')).toHaveTextContent('none')
    expect(oldSocket.closed).toBe(true)
    await flush()
    expect(FakeWebSocket.instances).toHaveLength(2)
    act(()=>{FakeWebSocket.instances[1].open();FakeWebSocket.instances[1].message({account:'acc_b'})})
    expect(screen.getByTestId('account')).toHaveTextContent('acc_b')

    mocks.auth.user=null
    view.rerender(<TelemetryProvider><Probe/></TelemetryProvider>)
    expect(screen.getByTestId('account')).toHaveTextContent('none')
    expect(screen.getByTestId('status')).toHaveTextContent('offline')
    expect(FakeWebSocket.instances[1].closed).toBe(true)
    act(()=>vi.runOnlyPendingTimers())
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('invalidates on WS 1008 and never schedules a reconnect',async()=>{
    const unauthorized=vi.fn()
    window.addEventListener('algoshield:unauthorized',unauthorized)
    mocks.apiGet.mockResolvedValue({account:'acc_a'})
    render(<TelemetryProvider><Probe/></TelemetryProvider>)
    await flush()
    const socket=FakeWebSocket.instances[0]
    act(()=>{socket.open();socket.closeFromServer(1008)})
    expect(unauthorized).toHaveBeenCalledOnce()
    expect(screen.getByTestId('account')).toHaveTextContent('none')
    expect(screen.getByTestId('status')).toHaveTextContent('offline')
    act(()=>vi.runOnlyPendingTimers())
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
    window.removeEventListener('algoshield:unauthorized',unauthorized)
  })

  it('does not retry an initial HTTP 401',async()=>{
    const unauthorized=vi.fn()
    window.addEventListener('algoshield:unauthorized',unauthorized)
    mocks.apiGet.mockRejectedValue(Object.assign(new Error('expired'),{status:401}))
    render(<TelemetryProvider><Probe/></TelemetryProvider>)
    await flush()
    expect(screen.getByTestId('status')).toHaveTextContent('offline')
    act(()=>vi.runOnlyPendingTimers())
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(unauthorized).toHaveBeenCalledOnce()
    window.removeEventListener('algoshield:unauthorized',unauthorized)
  })
})
