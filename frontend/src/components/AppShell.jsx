import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useTelemetry } from '../telemetry/TelemetryContext'
import { api } from '../api/client'

const groups = [
  ['Operate', [['/', 'Overview'], ['/strategies', 'Strategies'], ['/orders', 'Orders'], ['/risk', 'Risk Center'], ['/reconciliation', 'Reconciliation']]],
  ['Prove', [['/traces', 'Execution Traces'], ['/failure-lab', 'Failure Lab'], ['/safety-bench', 'SafetyBench']]],
  ['Observe', [['/metrics', 'Metrics'], ['/market-data', 'Market Data'], ['/audit', 'Audit']]],
]

export function AppShell() {
  const { user, logout, refresh: refreshAuth } = useAuth()
  const { snapshot, status, refresh } = useTelemetry()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [killPending, setKillPending] = useState(false)
  const [killError, setKillError] = useState('')
  const isOperator = Boolean(user?.is_operator)

  useEffect(() => setMenuOpen(false), [location.pathname])
  useEffect(() => {
    if (!menuOpen) return undefined
    const closeOnEscape = event => { if (event.key === 'Escape') setMenuOpen(false) }
    document.body.classList.add('menu-open')
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.classList.remove('menu-open')
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [menuOpen])

  const kill = async () => {
    if (killPending || !isOperator) return
    if (!confirm('Close the global gate and begin verified flattening?')) return
    setKillPending(true)
    setKillError('')
    try {
      await api.post('/api/kill')
      await refresh()
    } catch (error) {
      if (error?.status === 403) {
        await refreshAuth?.()
      }
      setKillError(error.message || 'Kill request failed.')
    } finally {
      setKillPending(false)
    }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-head">
        <NavLink className="brand" to="/"><b>AS</b><span>AlgoShield<small>Strategy safety control</small></span></NavLink>
        <button className="menu-toggle" type="button" aria-label="Open navigation" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(true)}><span/><span/><span/></button>
      </div>
      <button className={`menu-backdrop ${menuOpen ? 'open' : ''}`} type="button" aria-label="Close navigation" onClick={() => setMenuOpen(false)}/>
      <div className={`nav-drawer ${menuOpen ? 'open' : ''}`}>
        <div className="drawer-head"><span>Navigation</span><button type="button" aria-label="Close navigation" onClick={() => setMenuOpen(false)}>Close</button></div>
        <nav id="primary-navigation" aria-label="Primary navigation">
          {groups.map(([label, items]) => <div className="nav-group" key={label}>
            <span>{label}</span>
            {items.map(([to, text]) => <NavLink end={to === '/'} to={to} key={to}>{text}</NavLink>)}
          </div>)}
        </nav>
        <button
          className="kill"
          disabled={killPending || !isOperator}
          title={!isOperator ? 'Operator authority required' : undefined}
          onClick={kill}
        >
          {killPending ? 'Kill in progress…' : !isOperator ? 'Kill all strategies (Operator required)' : 'Kill all strategies'}
        </button>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <div className="connection"><i className={status}/><span>{status === 'live' ? 'Live backend evidence' : status}</span></div>
        <div><span className="user">{user?.username} · {user?.account_id}{isOperator ? ' · Operator' : ''}</span><button className="ghost" onClick={async () => { await logout(); navigate('/login') }}>Sign out</button></div>
      </header>
      {killError && <div className="shell-alert error" role="alert">{killError}</div>}
      <main className="content"><Outlet context={{ snapshot, refresh }}/></main>
    </div>
  </div>
}
