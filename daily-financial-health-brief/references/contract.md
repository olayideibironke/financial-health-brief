# Contract

Normalized CSV headers, in order:

- transactions.csv: transaction_id,date,account,category,description,amount,currency,status,source,source_version,amount_status
- budget.csv: period,category,budget_amount,currency,owner,review_rule,source,source_version
- revenue.csv: date,source,metric,value,currency,source_version

Runtime inputs are the three source URLs and explicit reporting date, prior business date, and revenue snapshot date. Every run fetches all sources live and records URL, spreadsheet identity, tab identity, fetch timestamp, source version, and fetched row count.

Preserve every recognized row, including unresolved transactions with blank amounts. Report exact signed values for reporting-date posted, pending-confirmed, disputed-confirmed, prior-business-day posted totals, and posted-total change. Compare month-to-date posted spend with the monthly budget. Materiality is strict absolute variance greater than both ten percent of baseline and USD 500. With a zero baseline, apply only the strict USD 500 test.

The interview leaves status mappings, sign conventions, reporting timezone and calendar, revenue metric selection, source completeness markers, and category-without-budget behavior unresolved. Require explicit configuration for these decisions or fail with a clarification error.

Normalized CSV contents and financial calculations are deterministic for identical fetched inputs and reporting parameters. report.md includes the real fetch timestamp and source hashes for provenance, so its bytes can differ between live runs even when the computed values are unchanged.
