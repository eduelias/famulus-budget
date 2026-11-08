#!/usr/bin/env python3
"""Virtual mesada ledger: €200/person/month credited since Oct 2026, debits are
joint-account purchases tagged 'Mesada (Vê)' / 'Mesada (Edu)'. Unspent carries over.
Usage: python3 mesadas.py [YYYY-MM]"""
import json, os, sys, collections, datetime as dt

HERE = os.environ.get('BUDGET_DIR', os.path.dirname(os.path.abspath(__file__)))
ROWS = os.path.join(HERE, 'pnl_rows.json')
START = '2026-10'
ALLOWANCE = {'Mesada (Vê)': 200.0, 'Mesada (Edu)': 200.0}

def months(upto):
    y, m = map(int, START.split('-')); out = []
    while f"{y:04d}-{m:02d}" <= upto:
        out.append(f"{y:04d}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out

def ledger(upto=None):
    upto = upto or dt.date.today().strftime('%Y-%m')
    rows = json.load(open(ROWS))
    spent = collections.defaultdict(float)
    for r in rows:
        if r[4] in ALLOWANCE and r[2] != 'Planned' and r[1] <= upto:
            spent[(r[4], r[1])] += r[5]
    out = {}
    for cat, allow in ALLOWANCE.items():
        bal = 0.0; hist = []
        for ym in months(upto):
            s = spent.get((cat, ym), 0.0)
            bal += allow + s
            hist.append((ym, round(-s, 2), round(bal, 2)))
        out[cat] = hist
    return out

def text(upto=None, lang='pt'):
    lines = []
    for cat, hist in ledger(upto).items():
        who = 'Vê' if 'Vê' in cat else 'Edu'
        ym, s, bal = hist[-1]
        lines.append(f"{who}: {'gastou' if lang=='pt' else 'spent'} €{s:.0f} {'em' if lang=='pt' else 'in'} {ym[5:]}/{ym[:4]} · "
                     f"{'saldo' if lang=='pt' else 'balance'} €{bal:.0f}")
    return '\n'.join(lines)

if __name__ == '__main__':
    upto = sys.argv[1] if len(sys.argv) > 1 else None
    for cat, hist in ledger(upto).items():
        print(cat)
        for ym, s, bal in hist:
            print(f"  {ym}  +200  -{s:7.2f}  = {bal:8.2f}")
