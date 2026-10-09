import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  selectDemoRole: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: { get: mocks.get, selectDemoRole: mocks.selectDemoRole },
}))

import { AuthProvider, useAuth } from '../auth/AuthContext'

function Probe() {
  const { user, loading, error, selectRole } = useAuth()
  return <>
    <span>{loading ? 'loading' : 'ready'}</span>
    <span>{user?.account_id || 'no-role'}</span>
    <span>{error || 'no-error'}</span>
    <button onClick={() => selectRole('operator')}>Operator</button>
  </>
}

const flush = async () => { await act(async () => { await Promise.resolve(); await Promise.resolve() }) }

describe('demo role context', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults an anonymous browser to the database-backed Trader role', async () => {
    mocks.get.mockRejectedValue(Object.assign(new Error('missing'), { status: 401 }))
    mocks.selectDemoRole.mockResolvedValue({ user: { account_id: 'acc_demo_trader', is_operator: 0 } })
    render(<AuthProvider><Probe /></AuthProvider>)
    await flush()
    expect(mocks.selectDemoRole).toHaveBeenCalledWith('trader')
    expect(screen.getByText('acc_demo_trader')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
  })

  it('switches to Operator without username or password input', async () => {
    const user = userEvent.setup()
    mocks.get.mockResolvedValue({ user: { account_id: 'acc_demo_trader', is_operator: 0 } })
    mocks.selectDemoRole.mockResolvedValue({ user: { account_id: 'acc_demo_operator', is_operator: 1 } })
    render(<AuthProvider><Probe /></AuthProvider>)
    await flush()
    await user.click(screen.getByRole('button', { name: 'Operator' }))
    expect(mocks.selectDemoRole).toHaveBeenCalledWith('operator')
    expect(screen.getByText('acc_demo_operator')).toBeInTheDocument()
  })
})
