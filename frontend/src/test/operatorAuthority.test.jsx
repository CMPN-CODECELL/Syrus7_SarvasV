import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  auth: {
    user: { username: 'ordinary_trader', account_id: 'acc_ord', is_operator: 0 },
    logout: vi.fn(),
    refresh: vi.fn(),
  },
  telemetry: { snapshot: {}, status: 'live', refresh: vi.fn() },
}))

vi.mock('../api/client', () => ({ api: { get: mocks.get, post: mocks.post } }))
vi.mock('../auth/AuthContext', () => ({ useAuth: () => mocks.auth }))
vi.mock('../telemetry/TelemetryContext', () => ({ useTelemetry: () => mocks.telemetry }))

import { AppShell } from '../components/AppShell'
import { OverviewPage } from '../pages/OverviewPage'
import { OrdersPage } from '../pages/OrdersPage'
import { StrategiesPage } from '../pages/StrategiesPage'
import {
  FailureLabPage,
  MarketDataPage,
  ReconciliationPage,
  SafetyBenchPage,
} from '../pages/EvidencePages'

const sampleSnapshot = {
  gate: 'RUNNING',
  health: 'HEALTHY',
  demo_enabled: true,
  safety: {
    kill_latched: false,
    reconciliation: { reason: 'ALL_MATCHED' },
  },
  subscriptions: [
    {
      id: 'strat_alpha',
      account: 'acc_ord',
      kind: 'momentum',
      symbol: 'TCS',
      enabled: 1,
      state: 'RUNNING',
      readiness: { samples: 5, warmup: 5, ready: true },
    },
  ],
  orders: [
    {
      id: 'ord_1',
      strategy: 'strat_alpha',
      symbol: 'TCS',
      side: 'BUY',
      quantity: 10,
      filled: 0,
      status: 'OPEN',
    },
  ],
  fills: [],
  market_data: {
    connected: true,
    latest_quotes: [{ symbol: 'TCS', price: '3450.00' }],
  },
  market_session: { status: 'OPEN' },
}

function renderOutlet(element, context = { snapshot: sampleSnapshot, refresh: vi.fn() }) {
  return render(
    <MemoryRouter>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route index element={element} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Operator authority and account control boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.telemetry.snapshot = sampleSnapshot
    mocks.telemetry.status = 'live'
    mocks.auth.logout = vi.fn()
    mocks.auth.refresh = vi.fn()
  })

  it('ordinary users cannot invoke operator actions across UI surfaces and no protected action request occurs', async () => {
    const user = userEvent.setup()
    mocks.auth.user = { username: 'ordinary_trader', account_id: 'acc_ord', is_operator: 0 }

    // 1. AppShell: Kill button is disabled with explanatory label
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    const killBtn = screen.getByRole('button', { name: /Kill all strategies \(Operator required\)/i })
    expect(killBtn).toBeDisabled()
    expect(killBtn).toHaveAttribute('title', 'Operator authority required')
    await user.click(killBtn)
    expect(mocks.post).not.toHaveBeenCalled()

    // 2. OverviewPage: Replay, Reconcile, Resume are disabled and marked operator required
    const { unmount: unmountOverview } = renderOutlet(<OverviewPage />)
    expect(screen.getByText('Operator required')).toBeInTheDocument()
    const replayBtn = screen.getByRole('button', { name: 'Run replay' })
    const reconcileBtn = screen.getByRole('button', { name: 'Reconcile' })
    const resumeBtn = screen.getByRole('button', { name: 'Resume' })
    expect(replayBtn).toBeDisabled()
    expect(reconcileBtn).toBeDisabled()
    expect(resumeBtn).toBeDisabled()
    await user.click(replayBtn)
    await user.click(reconcileBtn)
    await user.click(resumeBtn)
    expect(mocks.post).not.toHaveBeenCalled()
    unmountOverview()

    // 3. ReconciliationPage: broker action buttons are disabled
    mocks.get.mockResolvedValueOnce({
      status: 'DISCONNECTED',
      connected: false,
      divergences: [],
    })
    const { unmount: unmountRecon } = renderOutlet(<ReconciliationPage />)
    const syncBtn = await screen.findByRole('button', { name: 'Sync broker updates' })
    const reconnectBtn = screen.getByRole('button', { name: 'Reconnect and reconcile' })
    const disconnectBtn = screen.getByRole('button', { name: 'Disconnect broker' })
    expect(syncBtn).toBeDisabled()
    expect(reconnectBtn).toBeDisabled()
    expect(disconnectBtn).toBeDisabled()
    await user.click(syncBtn)
    await user.click(reconnectBtn)
    await user.click(disconnectBtn)
    expect(mocks.post).not.toHaveBeenCalled()
    unmountRecon()

    // 4. FailureLabPage: scenario run button is disabled with operator required label
    mocks.get.mockResolvedValueOnce({ scenarios: ['partial'] })
    const { unmount: unmountLab } = render(<FailureLabPage />)
    const labRunBtn = await screen.findByRole('button', { name: /Run Partial order fill mock test/i })
    expect(labRunBtn).toBeDisabled()
    expect(labRunBtn).toHaveTextContent('Operator required')
    await user.click(labRunBtn)
    expect(mocks.post).not.toHaveBeenCalled()
    unmountLab()

    // 5. SafetyBenchPage: run benchmark button is disabled with operator required label
    mocks.get.mockResolvedValueOnce(null)
    const { unmount: unmountBench } = render(<SafetyBenchPage />)
    const benchBtn = await screen.findByRole('button', { name: /Run benchmark \(Operator required\)/i })
    expect(benchBtn).toBeDisabled()
    await user.click(benchBtn)
    expect(mocks.post).not.toHaveBeenCalled()
    unmountBench()

    // 5. MarketDataPage: operator session control buttons are disabled
    const { unmount: unmountMarket } = renderOutlet(<MarketDataPage />)
    expect(screen.getByText('Operator required')).toBeInTheDocument()
    const openBtn = screen.getByRole('button', { name: 'Open' })
    const closeBtn = screen.getByRole('button', { name: 'Close' })
    expect(openBtn).toBeDisabled()
    expect(closeBtn).toBeDisabled()
    await user.click(openBtn)
    await user.click(closeBtn)
    expect(mocks.post).not.toHaveBeenCalled()
    unmountMarket()
  })

  it('missing role defaults to non-operator authority', async () => {
    const user = userEvent.setup()
    // User object without is_operator property
    mocks.auth.user = { username: 'unranked_trader', account_id: 'acc_unranked' }

    renderOutlet(<OverviewPage />)
    expect(screen.getByText('Operator required')).toBeInTheDocument()
    const reconcileBtn = screen.getByRole('button', { name: 'Reconcile' })
    expect(reconcileBtn).toBeDisabled()
    expect(reconcileBtn).toHaveAttribute('title', 'Operator authority required')
    await user.click(reconcileBtn)
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('operators retain access, confirmation flow, and error handling', async () => {
    const user = userEvent.setup()
    mocks.auth.user = { username: 'operator_admin', account_id: 'acc_ops', is_operator: 1 }
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    // Operator Kill flow in AppShell
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText(/operator_admin · acc_ops · Operator/i)).toBeInTheDocument()
    const killBtn = screen.getByRole('button', { name: 'Kill all strategies' })
    expect(killBtn).toBeEnabled()
    mocks.post.mockResolvedValueOnce({ gate: 'KILLED' })

    await user.click(killBtn)
    expect(confirmSpy).toHaveBeenCalledOnce()
    expect(mocks.post).toHaveBeenCalledWith('/api/kill')

    // Operator Overview actions
    const { unmount } = renderOutlet(<OverviewPage />)
    expect(screen.queryByText('Operator required')).not.toBeInTheDocument()
    const reconcileBtn = screen.getByRole('button', { name: 'Reconcile' })
    expect(reconcileBtn).toBeEnabled()
    mocks.post.mockResolvedValueOnce({ health: 'HEALTHY' })
    await user.click(reconcileBtn)
    expect(mocks.post).toHaveBeenCalledWith('/api/reconcile')
    unmount()
  })

  it('revoked authority + 403 refreshes identity and removes controls without logging out', async () => {
    const user = userEvent.setup()
    mocks.auth.user = { username: 'formerly_operator', account_id: 'acc_ops', is_operator: 1 }

    // Backend returns 403 Forbidden because grant was revoked on server
    const forbiddenError = Object.assign(new Error('Forbidden: operator authority required'), {
      status: 403,
    })
    mocks.post.mockRejectedValueOnce(forbiddenError)

    // Simulate refreshAuth updating user to is_operator = 0
    mocks.auth.refresh.mockImplementation(async () => {
      mocks.auth.user = { username: 'formerly_operator', account_id: 'acc_ops', is_operator: 0 }
    })

    const { rerender } = renderOutlet(<OverviewPage />)
    const reconcileBtn = screen.getByRole('button', { name: 'Reconcile' })
    expect(reconcileBtn).toBeEnabled()

    await user.click(reconcileBtn)

    // Verify 403 was caught, identity was refreshed, and user was NOT logged out
    expect(mocks.auth.refresh).toHaveBeenCalledOnce()
    expect(mocks.auth.logout).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('Forbidden: operator authority required')

    // Re-render with the updated user identity returned by refreshAuth
    rerender(
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={{ snapshot: sampleSnapshot, refresh: vi.fn() }} />}>
            <Route index element={<OverviewPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    // Operator actions are now disabled and "Operator required" is displayed
    expect(screen.getByText('Operator required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reconcile' })).toBeDisabled()
  })

  it('account-owned controls remain available for ordinary users', async () => {
    const user = userEvent.setup()
    mocks.auth.user = { username: 'ordinary_trader', account_id: 'acc_ord', is_operator: 0 }
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    // 1. OrdersPage: Order cancellation is an account-owned control
    mocks.post.mockResolvedValueOnce({ status: 'CANCELLED' })
    const { unmount: unmountOrders } = renderOutlet(<OrdersPage />)
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' })
    expect(cancelBtn).toBeEnabled()
    await user.click(cancelBtn)
    expect(mocks.post).toHaveBeenCalledWith('/api/orders/ord_1/cancel')
    unmountOrders()

    // 2. StrategiesPage: Subscription stop/start is an account-owned control
    mocks.get.mockResolvedValueOnce([{ kind: 'momentum', description: 'Momentum' }])
    mocks.post.mockResolvedValueOnce({ success: true })
    const { unmount: unmountStrats } = renderOutlet(<StrategiesPage />)
    const stratRow = (await screen.findByText('strat_alpha')).closest('tr')
    const stopBtn = within(stratRow).getByRole('button', { name: 'Stop' })
    expect(stopBtn).toBeEnabled()
    await user.click(stopBtn)
    expect(mocks.post).toHaveBeenCalledWith('/api/subscriptions/strat_alpha/stop')
    unmountStrats()
  })
})
