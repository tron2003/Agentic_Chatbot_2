"""Spreadsheet calculations (parse, SQL, safety, routing, upload lifecycle) and the report PDF export."""

import asyncio
import datetime
import io

import pytest

from agentic_chatbot.entity.router import Router
from agentic_chatbot.nodes.router_node import apply_sheet_intent
from agentic_chatbot.services import spreadsheets as sp


def _gst_workbook() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Refunds Aug-Oct"
    ws.append(["PRINTRAY ENTERPRISES — GST Refund Calculation"])
    ws.append([])
    ws.append(["Period: Aug 2026 to Oct 2026"])
    ws.append(["Invoice No", "Invoice Date", "Party Name", "Taxable Value", "IGST", "Refund Amount (₹)"])
    ws.append(["INV-001", datetime.datetime(2026, 8, 3), "Acme", 100000, 18000, "1,250.50"])
    ws.append(["INV-002", datetime.datetime(2026, 9, 14), "Beta", 250000.5, 45000, "₹ 2,000"])
    ws.append(["INV-003", datetime.datetime(2026, 10, 1), "Acme", 50000, 9000, "(300)"])
    ws.append(["Total", None, None, 400000.5, 72000, "2,950.50"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def uploaded_sheet(client):
    files = [("files", ("Printray_Refund_Cal_Aug26_to_Oct26.xlsx", _gst_workbook(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    result = client.post("/api/documents", files=files).json()["results"][0]
    assert result["status"] == "ok", result
    return result["document"]["id"]


def test_report_style_sheet_is_parsed_into_a_clean_table(uploaded_sheet):
    tables = sp.load_tables()
    assert len(tables) == 1
    t = tables[0]
    assert list(t.df.columns) == ["invoice_no", "invoice_date", "party_name", "taxable_value", "igst", "refund_amount"]
    assert len(t.df) == 3, "title rows skipped, Total row removed"
    assert t.df["refund_amount"].tolist() == [1250.5, 2000.0, -300.0]
    schema = sp.describe()
    assert "1 total row(s) removed" in schema and 'header "Refund Amount (₹)"' in schema


def test_sql_computes_exact_totals_and_groups(uploaded_sheet):
    t = sp.load_tables()[0].name
    result, files = sp.run_query(f"SELECT party_name, SUM(refund_amount) AS refund FROM {t} GROUP BY 1 ORDER BY 2 DESC")
    assert "| Beta | 2,000.00 |" in result and "| Acme | 950.50 |" in result
    assert files == ["Printray_Refund_Cal_Aug26_to_Oct26.xlsx"]
    by_month, _ = sp.run_query(f"SELECT strftime(invoice_date, '%Y-%m') AS m, SUM(igst) FROM {t} GROUP BY 1 ORDER BY 1")
    assert "2026-09 | 45000" in by_month


@pytest.mark.parametrize("sql", [
    "DROP TABLE x",
    "SELECT 1; SELECT 2",
    "SELECT * FROM read_csv('secrets.csv')",
    "COPY (SELECT 1) TO 'out.csv'",
    "SELECT * FROM glob('*')",
])
def test_only_read_only_queries_on_the_sheets(uploaded_sheet, sql):
    with pytest.raises(ValueError):
        sp.run_query(sql)


def test_sql_cannot_read_files_even_by_path(uploaded_sheet, tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a\n1\n")
    import duckdb

    with pytest.raises((ValueError, duckdb.Error)):
        sp.run_query(f"SELECT * FROM '{secret.as_posix()}'")


def test_tools_and_routing_follow_uploaded_sheets(uploaded_sheet, client):
    from agentic_chatbot.tools.mcp_tools import get_agent_tools
    from agentic_chatbot.tools.spreadsheet_tool import query_spreadsheet

    assert {"describe_spreadsheets", "query_spreadsheet"} <= {t.name for t in get_agent_tools()}
    out = query_spreadsheet.invoke({"type": "tool_call", "id": "1", "name": "query_spreadsheet",
                                    "args": {"sql": f"SELECT SUM(igst) AS igst FROM {sp.load_tables()[0].name}"}})
    assert "72000" in out.content and out.artifact[0]["title"].endswith(".xlsx")
    bad = query_spreadsheet.invoke({"sql": "SELECT nope FROM missing"})
    assert bad.startswith("SQL error") and "Table " in bad

    rag = Router(route="rag", reason="docs")
    assert apply_sheet_intent(rag, "what is the total refund amount per party?", True).route == "agent"
    assert apply_sheet_intent(rag, "summarise the refund sheet", True).route == "rag", "no calculation asked"
    assert apply_sheet_intent(Router(route="chat", reason=""), "total of IGST?", False).route == "chat"

    # Removing the document removes its table and tools.
    assert client.delete(f"/api/documents/{uploaded_sheet}").status_code == 204
    assert sp.load_tables() == [] and not sp.sheets_available()
    assert "query_spreadsheet" not in {t.name for t in get_agent_tools()}


def test_sheet_questions_stay_out_of_web_research(uploaded_sheet, monkeypatch):
    from langchain_core.messages import HumanMessage

    from agentic_chatbot.entity.chat_state import Chatbot
    from agentic_chatbot.nodes import research_nodes

    monkeypatch.setattr(research_nodes, "web_search_available", lambda: True)
    state = Chatbot(messages=[HumanMessage(content="analyse my refund sheet by party")])
    assert asyncio.run(research_nodes.choose_depth(state)) == "quick"


# ── PDF export ─────────────────────────────────────────────────────────────

REPORT = """## Vanguard's largest holdings

**Summary.** NVIDIA leads at 6.7% [2](https://example.com/a) — ₹ and € print fine.

| Rank | Stock | Weight |
|---|---|---|
| 1 | NVIDIA | 6.7% |
| 2 | Apple | 6.1% |

- one
- two
"""


def test_report_pdf_renders_title_tables_and_sources():
    from pypdf import PdfReader

    from agentic_chatbot.services.report_pdf import render_report_pdf, safe_filename

    data = render_report_pdf("chat title", REPORT, [{"index": 1, "title": "Example", "url": "https://example.com/a"}],
                             question="Research Vanguard", model="demo")
    assert data.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(data))
    text = "".join(p.extract_text() for p in reader.pages)
    assert reader.metadata.title == "Vanguard's largest holdings", "the report's own heading becomes the title"
    for expected in ("Summary", "NVIDIA", "Apple", "Sources", "https://example.com/a", "Question: Research Vanguard"):
        assert expected in text
    assert safe_filename("Vanguard: 2026 update!") == "Vanguard-2026-update.pdf"


def test_pdf_endpoint_downloads_a_research_answer(client, stream, monkeypatch):
    from agentic_chatbot.nodes import research_nodes

    async def fake(query):
        return "duckduckgo", None, [{"title": f"About {query}", "url": "https://example.com/x", "content": "facts"}], ""

    monkeypatch.setattr(research_nodes, "search_results", fake)
    monkeypatch.setattr(research_nodes, "web_search_available", lambda: True)
    events = stream({"message": "research solar panels", "mode": "deep_research"})
    done = next(e for e in events if e["type"] == "done")["message"]
    res = client.get(f"/api/conversations/{done['conversation_id']}/messages/{done['id']}/pdf")
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("attachment; filename=") and res.content.startswith(b"%PDF")
    assert client.get(f"/api/conversations/{done['conversation_id']}/messages/nope/pdf").status_code == 404
