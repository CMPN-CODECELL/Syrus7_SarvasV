function positionKey(accountId, strategyInstanceId, symbol) {
  if (!accountId || !strategyInstanceId || !symbol) return null
  return `${accountId}\u0000${strategyInstanceId}\u0000${symbol}`
}

export function strategyRows(snapshot) {
  const positions = new Map()
  for (const position of snapshot?.positions ?? []) {
    const key = positionKey(
      position.account_id,
      position.strategy_instance_id,
      position.symbol,
    )
    if (key) positions.set(key, position)
  }
  return (snapshot?.subscriptions ?? []).map(subscription => {
    const financialPosition=positions.get(
      positionKey(subscription.account, subscription.id, subscription.symbol),
    )
    return {
      ...subscription,
      financial_position:financialPosition??{
        strategy_instance_id:subscription.id,
        symbol:subscription.symbol,
        net_quantity:0,
        net_pnl:'0',
        charges:'0',
        has_fill_evidence:false,
      },
    }
  })
}
