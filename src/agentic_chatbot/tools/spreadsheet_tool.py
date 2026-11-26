"""Agent tools for the user's spreadsheets: see the tables, then compute with read-only SQL."""

from __future__ import annotations

from langchain_core.tools import tool

from agentic_chatbot.services.spreadsheets import describe, run_query


@tool
def describe_spreadsheets() -> str:
    """List the user's uploaded spreadsheets (Excel/CSV) as SQL tables: table names, columns with types,
    row counts and example values. Call this before query_spreadsheet if you don't know the column names."""
    return describe()


@tool(response_format="content_and_artifact")
def query_spreadsheet(sql: str) -> tuple[str, list[dict]]:
    """Run one read-only DuckDB SQL SELECT over the user's spreadsheets and get the result as a table.
    Use it for anything numeric: totals, averages, counts, filters, top-N, group by month or party.
    Table and column names are the snake_case names from describe_spreadsheets.
    Examples: SELECT SUM(refund_amount) FROM t; SELECT party_name, SUM(igst) AS igst FROM t GROUP BY 1 ORDER BY 2 DESC;
    SELECT strftime(invoice_date, '%Y-%m') AS month, SUM(taxable_value) FROM t GROUP BY 1 ORDER BY 1."""
    try:
        result, files = run_query(sql)
    except Exception as exc:  # show the error so the model can fix its SQL
        return f"SQL error: {exc}\n\nAvailable tables:\n{describe(max_chars=2500)}", []
    return result, [{"kind": "doc", "title": f, "snippet": "Calculated from this spreadsheet"} for f in files]
