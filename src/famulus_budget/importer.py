#!/usr/bin/env python3
"""Import an ABN AMRO statement PDF into pnl_rows.json (idempotent).
Usage: python3 import_statement.py <statement.pdf>
Filename must be mutovXXXX_DDMMYYYY-DDMMYYYY.pdf (ABN default)."""
import json, os, re, subprocess, sys

HERE = os.environ.get('BUDGET_DIR', '/budget')
ROWS = os.path.join(HERE, 'pnl_rows.json')

INCOME_RULES = [
 ('Salary (Schuberg Philis)', r'SCHUBERG'),
 ('Child benefit (SVB)', r'Sociale Verzekeringsbank'),
 ('Tax refunds', r'BELASTINGDIENST'),
 ('Other income', r'.'),
]
EXP_RULES = [
 ('Work (reimbursed)', r"Burger 'n Shake|NYX\*VendingWork|Q-Park|Takeaway via MultiSafepay.*EREF/\d\d-\d\d-\d{4} 1[123]:"),
 ('Mortgage', r'ABN AMRO BANK NV.*(hy\s?potheek|Termijnbetaling|oh verhoging)'),
 ('Renovation (one-off)', r'Stroomgroep'),
 ('Energy & water', r'NextEnergy|Vattenfall|VITENS|GBLT|ENGIE'),
 ('Taxes (municipal & national)', r'Gemeente Almere|Belastingdienst|GBLT|BNG\*GEMEENTE'),
 ('Insurance', r'NN VERZEKEREN|NATIONALE-NED|Nationale-\s?Nederlanden|CHUBB|ONVZ'),
 ('Car & transport', r'ATHLON|Shell|CJIB|Dancar|PARK MOBILE|Kwik-Fit|parkeer|Parkeer|TinQ|Esso|OV-\s?Chipka|TLS BV|NS GROEP|GVB|Viggo'),
 ('Groceries', r'Vomar|VOMAR|Albert Heijn|AH Almere|Lidl|ALDI|Jumbo|Makro|Kema Vlees|Visboer|Sabores|Koopman|CARREFOUR|DEKAMARKT|DIRK|KARSEMEIJER|KDA|Kwaliteitsvishande|MM Almere|Finalmente|Amazing|Turkuaz|1-Minute'),
 ('Household & drugstore', r'Kruidvat|ETOS|Action|Wibra|HEMA|Blokker|NORMAL|IKEA|Gamma|123inkt|Big Bazar|Miniso|pipoos'),
 ('Childcare (GO)', r'STICHTING GO|ouderportaal'),
 ('Kids lessons (ballet & piano)', r'Balletschool|Musiqskool|Stichting Prisma'),
 ('Health & medical', r'INFOMEDICS|Flevoziekenhuis|Infomedics|apotheek|Apotheek|tandarts'),
 ('Telecom & internet', r'KPN|ODIDO'),
 ('Subscriptions & digital', r'Spotify|hbomax|APPLE\.COM|GOOGLE\*|MICROSOFT|PATREON|SQSP|Amazon Prime|STEAM|Netflix|Disney'),
 ('Entertainment & eating out', r"McDonalds|KFC|SUBWAY|IJssalon|Kinepolis|Burger|Thuisbezorgd|Subway|Starbucks|La Place|Febo|Snackbar|MOJO|Arena 81|Pathe|UBER \*EATS|Costes|Chillie|Beach Club|Pizzeria|Trattoria|Butcher Social|Albron|NEMO|Center Parcs|Restaurant|NYX\*|Kiddy|BACKWERK|Grill|Sushi|Pannenkoeken"),
 ('Clothing & personal', r'PRIMARK|Vinted|Zara|ZARA|C&A|Daily Style|BALTONA|Bershka|New Yorker|Zeeman|shein|SHEIN|H&M|Uniqlo|BARBERSHOP|Decathlon|Glaspunt|Pearle|vanHaren|Scapino|adidas'),
 ('Online shopping', r'Temu|TEMU|Amazon|AMZN|AliExpress|ALIBABA|bol\.com|BOL\.COM|eBay|ZOOLOX|FULLBO|PDFAID|DigiKey|Kiwi Electronics'),
 ('Transfers & Tikkie', r'Tikkie|Betaalverzoek|Wise|Geldmaat'),
 ('Services & other', r'.'),
]

def norm(d): return re.sub(r'\s+', ' ', d)

def _custom_rules():
    p = os.path.join(HERE, 'custom_rules.json')
    try:
        return [tuple(r) for r in json.load(open(p))]
    except Exception:
        return []

def classify(desc, rules):
    d = norm(desc)
    for pat, name in _custom_rules():
        if re.search(pat, d, re.IGNORECASE): return name
    for name, pat in rules:
        if re.search(pat, d): return name
    return rules[-1][0]

def merchant(desc):
    d = norm(desc)
    m = re.search(r'/NAME/(.*?)\s*/(?:MARF|EREF|REMI|CSID)', d)
    if m: return m.group(1).strip()[:40]
    m = re.search(r'Naam:\s*(.*?)(?:\s+Machtiging|\s+Omschrijving|\s+Kenmerk|IBAN)', d)
    if m: return m.group(1).strip()[:40]
    m = re.match(r'\d{2}-\d{2}-\d{4}\s+(?:BEA, |GEA, |eCom, )?(?:Betaalpas|Apple Pay|Google Pay|iDEAL)?\s*(.*)', d)
    return (m.group(1) if m else d)[:40]

SKIP = [r'Account Balance', r'Bij- en afschrijvingen', r'Account holder name', r'Rekeninghouder',
        r'Mevrouw V\.', r'Buitenhof', r'1354 GT', r'Private Account With', r'^\s*Overdraft\s*$',
        r'Date interval', r'^Periode', r'transactions\s*$', r'schrijvingen\s*$', r'Number of debit',
        r'Aantal afschrijvingen', r'^\s*Balance \d', r'^Saldo \d', r'Total amount', r'Totaal ',
        r'^\s*Date\s+Description', r'^\s*Datum\s+Omschrijving', r'Page \d+ of', r'Pagina \d+ van',
        r'^\s*€ [\d\.,-]+\s*€ [\d\.,]+\s*$', r'^\s*\d+\s+\d+\s*$']

def parse_pdf(pdf):
    txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True).stdout
    clean = [l for l in txt.split('\n') if not any(re.search(p, l) for p in SKIP)]
    datere = re.compile(r'^(\d{2}-\d{2}-\d{4})\s+(.*)$')
    amtre = re.compile(r'([\d\.]*\d,\d{2})\s*$')
    txns, cur = [], None
    for l in clean:
        m = datere.match(l)
        if m:
            if cur: txns.append(cur)
            cur = {'date': m.group(1), 'lines': [l]}
        elif cur is not None and l.strip():
            cur['lines'].append(l)
    if cur: txns.append(cur)
    recs = []
    for t in txns:
        m = amtre.search(t['lines'][0])
        if not m: continue
        amt = float(m.group(1).replace('.', '').replace(',', '.'))
        side = 'debit' if m.start(1) < 78 else 'credit'
        recs.append({'date': t['date'], 'amount': amt, 'side': side,
                     'desc': ' '.join(x.strip() for x in t['lines'])})
    return recs

def import_pdf(pdf):
    m = re.search(r'_(\d{8})-(\d{8})\.pdf$', os.path.basename(pdf))
    if not m:
        sys.exit('filename must end _DDMMYYYY-DDMMYYYY.pdf')
    def iso(s): return f"{s[4:8]}-{s[2:4]}-{s[0:2]}"
    start, end = iso(m.group(1)), iso(m.group(2))
    rows = json.load(open(ROWS))
    # idempotency: drop Bank rows inside period and Planned rows that occurred in period
    rows = [r for r in rows if not (
        (r[2] == 'Bank' and start <= r[0] <= end) or
        (r[2] == 'Planned' and start <= r[0] <= end))]
    added = 0
    for r in parse_pdf(pdf):
        dd, mm, yy = r['date'].split('-')
        d_iso = f"{yy}-{mm}-{dd}"
        if not (start <= d_iso <= end): continue
        desc = norm(r['desc'])
        if r['side'] == 'credit':
            cat = 'Renovation depot (one-off)' if 'Depotbetaling' in desc else classify(desc, INCOME_RULES)
            rows.append([d_iso, d_iso[:7], 'Bank', merchant(r['desc']), cat, round(r['amount'], 2)])
        else:
            if 'INT CARD' in desc: continue  # card detail imported separately
            rows.append([d_iso, d_iso[:7], 'Bank', merchant(r['desc']),
                         classify(desc, EXP_RULES), -round(r['amount'], 2)])
        added += 1
    rows.sort(key=lambda x: x[0])
    json.dump(rows, open(ROWS, 'w'))
    return f"imported {added} rows for {start}..{end}"

if __name__ == '__main__':
    import_pdf(sys.argv[1])
