import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Card, CompactEvidence, Empty, EvidenceView, Page, Status } from '../components/UI'

const labelFor = value => String(value).replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())

export function StrategyBudgets({ budgets = [] }) {
  if (!budgets.length) return <Empty>No strategy budget evidence is available yet.</Empty>
  return <div className="budget-list">{budgets.map((budget, index) => {
    const groups = Object.entries(budget).filter(([, value]) => value && typeof value === 'object')
    return <article className="budget-item" key={budget.strategy_instance_id || index}>
      <header className="budget-head">
        <div><h3>{budget.strategy_instance_id}</h3><p>{budget.symbol} · {budget.account_id}</p></div>
        <Status value={budget.state}/>
      </header>
      <div className="budget-groups">{groups.map(([name, values]) => <section className="budget-group" key={name}>
        <h4>{labelFor(name)}</h4>
        <CompactEvidence value={values}/>
      </section>)}</div>
    </article>
  })}</div>
}

export function RiskPage() {
  const { snapshot: state } = useOutletContext()
  const [policy, setPolicy] = useState(null)
  useEffect(() => { api.get('/api/risk/account-policy').then(setPolicy).catch(() => {}) }, [])
  return <Page eyebrow="Risk gateway" title="Non-bypassable controls" description="Projected exposure, rate, loss, and price checks are decided by the backend.">
    <div className="grid two">
      <Card title="Account policy">{policy ? <EvidenceView value={policy}/> : <Empty/>}</Card>
      <Card title="Latest decision">{state?.risk_decisions?.[0] ? <EvidenceView value={state.risk_decisions[0]}/> : <Empty>No risk decision has been recorded.</Empty>}</Card>
    </div>
    <Card title="Strategy budgets" className="budget-card"><StrategyBudgets budgets={state?.risk_budgets}/></Card>
  </Page>
}
