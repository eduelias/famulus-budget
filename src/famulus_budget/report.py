"""Weekly budget report with an 'unrecognized' section."""
import datetime as dt
import json
import os

BUDGETS = {"Groceries": ("Mercado", 1000), "Entertainment & eating out": ("Passeios", 150),
           "Clothing & personal": ("Roupas", 125), "Household & drugstore": ("Casa e higiene", 250)}
CATCH_ALL = "Services & other"


def weekly_report() -> str:
    here = os.environ.get("BUDGET_DIR", "/budget")
    rows = json.load(open(os.path.join(here, "pnl_rows.json")))
    today = dt.date.today()
    week_start = (today - dt.timedelta(days=today.weekday())).isoformat()
    month = today.strftime("%Y-%m")

    wk, mo, unknown = {}, {}, []
    for iso, mon, src, mer, cat, amt in rows:
        if src != "Bank" or amt >= 0:
            continue
        if cat in BUDGETS:
            if mon == month:
                mo[cat] = mo.get(cat, 0) - amt
            if week_start <= iso <= today.isoformat():
                wk[cat] = wk.get(cat, 0) - amt
        elif cat == CATCH_ALL and week_start <= iso <= today.isoformat():
            unknown.append((mer.strip()[:34], -amt))

    lines = [f"*Status da semana* ({week_start[8:]}/{week_start[5:7]} a "
             f"{today.strftime('%d/%m')})", ""]
    for cat, (pt, budget) in BUDGETS.items():
        guide = budget / 4.33
        w, m = wk.get(cat, 0), mo.get(cat, 0)
        icon = "✅" if w <= guide else "⚠️"
        lines.append(f"{icon} {pt}: €{w:.0f} na semana (guia ~€{guide:.0f}) | mês €{m:.0f}/{budget}")
    if unknown:
        lines += ["", "*Não reconhecidos* (fora dos orçamentos):"]
        lines += [f"  • €{v:.2f} — {m}" for m, v in unknown[:10]]
        lines.append('Responda "MERCHANT = categoria" para eu aprender.')
    return "\n".join(lines)
