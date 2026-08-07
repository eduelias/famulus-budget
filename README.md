# famulus-budget

Family budget plugin for [famulus](https://github.com/eduelias/famulus).

- WhatsApp an ABN AMRO statement PDF (`mutov*_DDMMYYYY-DDMMYYYY.pdf`) to the
  bot: transactions are imported idempotently, the workbook is rebuilt, and
  the bot replies with the weekly budget report.
- Categorization is **deterministic** (merchant rules). The LLM never guesses
  a category. Unrecognized merchants are listed in the report; teach new
  rules with the gated `add_budget_rule` tool.
- Tools: `budget_status`, `send_spreadsheet`, `add_budget_rule` (gated).

## Deploy

- Requires `poppler-utils` (pdftotext) in the image.
- Mount a data dir at `/budget` (or set `BUDGET_DIR`) containing
  `pnl_rows.json`; statements and the xlsx live there too.
- Needs famulus with document-handler dispatch (branch
  `feature/document-handlers` / >= the commit adding
  `Registry.document_handlers`).
