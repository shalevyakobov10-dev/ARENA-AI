# PERPS live execution and fill accounting

## Safety contract

A PERPS fill is recorded only when the exchange confirms a positive executed quantity, an actual average fill price, and an exchange order identifier.

- OKX: place the market order, query order details, and use cumulative filled contracts (accFillSz) and average fill price (avgPx). Any resting remainder is canceled and the final state is queried again.
- Binance USDⓈ-M Futures: request newOrderRespType=RESULT; use executedQty, avgPrice (or cumQuote / executedQty), and orderId. A zero-execution terminal response is not a fill.
- Hyperliquid: accept only the per-order filled object in response.data.statuses, using totalSz, avgPx, and oid. An explicit error is not a fill; an unexpected resting result triggers a cancel attempt and a fail-closed halt.

Exchange-specific response fields are documented by the venues:
- OKX order details include accFillSz, avgPx, and state values such as filled, partially_filled, and canceled: https://www.okx.com/docs-v5/en/
- Binance's RESULT response for a MARKET order is intended to return final order information, including execution data: https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin/api/rest-api/trade
- The Hyperliquid Python SDK market-order example reads fills from response.data.statuses[].filled (totalSz, avgPx, oid): https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_market_order.py

## Partial closes

A partial close reduces the local position only by the confirmed filled amount. Remaining size, margin, accumulated opening fees, and accrued funding remain attached to the residual open position. A close request returning no fill never produces a synthetic fill and never closes the local position.

## Unknown execution outcome

A transport timeout or server-side error after order submission can mean the exchange accepted the order even though the client did not receive the response. In that case the bot writes state/halt.json with source execution_uncertain, raises PerpsExecutionUncertain, and blocks subsequent automatic PERPS closes/entries until an operator reconciles the real exchange account and clears the halt. Do not clear this flag until the venue order history and current position have been checked.

## Test scope

The regression suite uses mocked HTTP/SDK responses only. It does not connect to an exchange, place orders, require credentials, or enable live trading.
