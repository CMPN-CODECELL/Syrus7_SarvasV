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
    const financialPosition=subscription.financial_position??positions.get(
      positionKey(subscription.account, subscription.id, subscription.symbol),
    )
    return {
      ...subscription,
      financial_position:financialPosition,
    }
  })
}
