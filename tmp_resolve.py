import sqlite3, os
kb = sqlite3.connect("file:data/legal_kb/legal_kb.sqlite?mode=ro", uri=True); kb.row_factory = sqlite3.Row
au = sqlite3.connect("file:data/evidence/audit.sqlite?mode=ro", uri=True)
by_path = {os.path.normcase(r[0]): r[1] for r in au.execute("select full_path, sha256 from sources")}

LIVE = r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\1. I N V E S T M E N T S  -  Global (Ex China)"
# transaction_id -> the live folder its relative_path values are relative to
CANDIDATE_BASES = [
    os.path.join(LIVE, "1. F U N D - I N V E S T M E N T"),
    os.path.join(LIVE, "0. E Q U I T Y"),
    LIVE,
]
print("Testing whether KB relative_path resolves against the LIVE folders\n")
for tx, folder_hint in (("4_mgx", "4. MGX"), ("1_new_space_capital_fund", "1. New Space Capital Fund"),
                        ("cerebras", "Cerebras"), ("drivenets", "DriveNets")):
    rows = kb.execute("select relative_path, filename from documents where transaction_id=? limit 60",
                      (tx,)).fetchall()
    if not rows:
        print(f"  {tx:<28} no documents"); continue
    best = (0, None)
    for base in CANDIDATE_BASES:
        for probe in (os.path.join(base, folder_hint), base):
            hits = sum(1 for r in rows
                       if os.path.normcase(os.path.join(probe, r["relative_path"])) in by_path)
            if hits > best[0]:
                best = (hits, probe)
    print(f"  {tx:<28} {best[0]:>3}/{len(rows):<3} resolved   base={str(best[1])[-52:] if best[1] else 'none'}")
