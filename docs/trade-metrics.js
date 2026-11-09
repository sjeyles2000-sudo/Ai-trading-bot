"use strict";
/* Read-only reconstruction of completed paper trade round trips.
   CSV quantities/prices/fees are rounded: results are estimates, not audited P&L.
   Excludes unrealised P&L from still-open virtual positions.
   No network, accounts, wallet access, trading, or credentials. */
const PaperTradeStats = (() => {
  function summarize(rows, market) {
    let open = null, closed = 0, wins = 0;
    let net = 0, fees = 0, positive = 0, negative = 0, transactions = 0;
    for (const row of rows) {
      if (row.market !== market) continue;
      transactions += 1;
      const side = (row.side || "").trim();
      const fields = [row.quantity_btc, row.virtual_price_usd, row.virtual_fee_usd];
      if (fields.some(value => typeof value !== "string" || !value.trim())) {
        throw new Error("Missing paper trade amount");
      }
      const [quantity, price, fee] = fields.map(Number);
      if (![quantity, price, fee].every(Number.isFinite) ||
          quantity <= 0 || price <= 0 || fee < 0) {
        throw new Error("Invalid paper trade amount");
      }
      fees += fee;
      if (side === "BUY") {
        if (open !== null) throw new Error("Overlapping paper entries");
        open = {quantity, cost: quantity * price + fee};
      } else if (side.endsWith("SELL")) {
        if (open === null) throw new Error("Unmatched paper exit");
        // The present ledger uses one full exit, not partial fills.
        const tolerance = Math.max(2e-8, open.quantity * 1e-5);
        if (Math.abs(quantity - open.quantity) > tolerance) {
          throw new Error("Paper exit quantity mismatch");
        }
        const realised = quantity * price - fee - open.cost;
        closed += 1;
        net += realised;
        if (realised > 0) {
          wins += 1;
          positive += realised;
        } else if (realised < 0) {
          negative -= realised;
        }
        open = null;
      } else {
        throw new Error("Unrecognised paper transaction");
      }
    }
    return {
      transactions, closed, wins, net, fees, hasOpenPosition: open !== null,
      winRate: closed ? 100 * wins / closed : null,
      profitFactor: negative ? positive / negative : null,
    };
  }
  return {summarize};
})();
if (typeof module !== "undefined" && module.exports) module.exports = PaperTradeStats;
if (typeof window !== "undefined") window.PaperTradeStats = PaperTradeStats;
