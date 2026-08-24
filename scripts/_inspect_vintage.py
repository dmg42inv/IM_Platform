import sqlite3

c = sqlite3.connect(r".\data\portfolio\portfolio.sqlite")
# earliest month we have
first_m = c.execute(
    "SELECT month_id FROM tracker_months WHERE parsed_ok=1 ORDER BY month_id ASC LIMIT 1"
).fetchone()[0]
print("earliest month in series:", first_m)

# distinct vintage values
vints = [r[0] for r in c.execute(
    "SELECT DISTINCT vintage FROM monthly_positions WHERE vintage!='' ORDER BY vintage"
).fetchall()]
print("distinct vintages:", vints)

# per-deal: vintage, tab, earliest-observed carrying + invested (across all months)
rows = c.execute(
    """
    SELECT deal_name,
           MIN(vintage) vintage,
           MAX(tab) tab,
           (SELECT carrying_value FROM monthly_positions p2
             WHERE p2.deal_name=p1.deal_name AND p2.carrying_value IS NOT NULL
             ORDER BY month_id ASC LIMIT 1) first_cv,
           (SELECT invested FROM monthly_positions p2
             WHERE p2.deal_name=p1.deal_name AND p2.invested IS NOT NULL
             ORDER BY month_id ASC LIMIT 1) first_inv
    FROM monthly_positions p1
    GROUP BY deal_name
    ORDER BY vintage
    """
).fetchall()
print(f"\n{len(rows)} distinct deals (vintage | tab | first_cv | first_inv):")
for r in rows:
    print(f"  {str(r[1]):8} {str(r[2]):7} cv={str(r[3])[:10]:12} inv={str(r[4])[:10]:12} {r[0][:32]}")
