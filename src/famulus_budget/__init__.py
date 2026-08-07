"""famulus-budget: ABN AMRO statement import, family budgets, weekly reports.

Send the bot an ABN statement PDF (mutov*_DDMMYYYY-DDMMYYYY.pdf) and it
imports the transactions (idempotently), rebuilds the budget workbook and
replies with the weekly report. Deterministic merchant rules do the
categorization; the LLM never guesses categories. Unrecognized merchants are
listed in the report and can be taught via the gated add_rule tool.
"""
import json
import os
import re
import runpy
import subprocess

import httpx
from famulus import config
from famulus.plugins import BasePlugin, spec

from .importer import import_pdf
from .report import weekly_report

__version__ = "0.1.0"
__all__ = ["BudgetPlugin"]

GRAPH = "https://graph.facebook.com/v20.0"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILENAME_RE = re.compile(r"^mutov\d+_\d{8}-\d{8}\.pdf$")


def _budget_dir() -> str:
    return os.environ.get("BUDGET_DIR", "/budget")


def _download_media(media_id: str, dest: str) -> None:
    headers = {"Authorization": f"Bearer {config.WA_TOKEN}"}
    with httpx.Client(timeout=60) as client:
        meta = client.get(f"{GRAPH}/{media_id}", headers=headers)
        meta.raise_for_status()
        blob = client.get(meta.json()["url"], headers=headers)
        blob.raise_for_status()
        open(dest, "wb").write(blob.content)


def _rebuild_workbook() -> None:
    script = os.path.join(os.path.dirname(__file__), "workbook_script.py")
    runpy.run_path(script, run_name="__main__")


def _send_spreadsheet(to: str) -> str:
    xlsx = os.path.join(_budget_dir(), "PnL-Budget-2026.xlsx")
    headers = {"Authorization": f"Bearer {config.WA_TOKEN}"}
    with httpx.Client(timeout=120) as client:
        with open(xlsx, "rb") as f:
            up = client.post(f"{GRAPH}/{config.WA_PHONE_ID}/media", headers=headers,
                             data={"messaging_product": "whatsapp"},
                             files={"file": (os.path.basename(xlsx), f, XLSX_MIME)})
        up.raise_for_status()
        r = client.post(f"{GRAPH}/{config.WA_PHONE_ID}/messages", headers=headers,
                        json={"messaging_product": "whatsapp", "to": to,
                              "type": "document",
                              "document": {"id": up.json()["id"],
                                           "filename": os.path.basename(xlsx)}})
        r.raise_for_status()
    return "spreadsheet sent"


def _add_rule(pattern: str, category: str) -> str:
    path = os.path.join(_budget_dir(), "custom_rules.json")
    try:
        rules = json.load(open(path))
    except Exception:
        rules = []
    rules.append([pattern, category])
    json.dump(rules, open(path, "w"), indent=1)
    return f"rule added: {pattern!r} -> {category}"


VALID_CATEGORIES = ["Groceries", "Entertainment & eating out", "Clothing & personal",
                    "Household & drugstore", "Car & transport", "Health & medical",
                    "Kids lessons (ballet & piano)", "Services & other"]


class BudgetPlugin(BasePlugin):
    name = "budget"
    tools = [
        spec("budget_status", "Current weekly/monthly family budget status "
             "(groceries, kids outings, clothing, household).", {}, []),
        spec("send_spreadsheet", "Send the budget workbook (xlsx) to the owner on WhatsApp.",
             {"to": {"type": "string", "description": "recipient number, digits only"}}, ["to"]),
        spec("add_budget_rule", "Teach the budget a new merchant categorization rule.",
             {"pattern": {"type": "string", "description": "merchant text/regex to match"},
              "category": {"type": "string", "enum": VALID_CATEGORIES}},
             ["pattern", "category"]),
    ]
    gated = {"add_budget_rule"}

    # ---- document hook (famulus core dispatches WhatsApp documents here) ----
    def wants_document(self, msg: dict) -> bool:
        return FILENAME_RE.match(msg.get("document", {}).get("filename", "")) is not None

    def handle_document(self, msg: dict) -> str:
        doc = msg["document"]
        dest = os.path.join(_budget_dir(), "statements", doc["filename"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _download_media(doc["id"], dest)
        result = import_pdf(dest)
        try:
            _rebuild_workbook()
        except Exception:
            pass  # workbook is best-effort; the report matters
        return f"{result}\n\n{weekly_report()}"

    # ---- LLM tools ----
    def describe(self, tool: str, args: dict) -> str:
        if tool == "add_budget_rule":
            return (f"Add budget rule: merchants matching {args.get('pattern')!r} "
                    f"will count as {args.get('category')!r} from now on.")
        return f"{tool} {args}"

    def execute(self, tool: str, args: dict) -> object:
        if tool == "budget_status":
            return weekly_report()
        if tool == "send_spreadsheet":
            return _send_spreadsheet(re.sub(r"\D", "", args["to"]))
        if tool == "add_budget_rule":
            return _add_rule(args["pattern"], args["category"])
        raise ValueError(f"unknown tool {tool!r}")
