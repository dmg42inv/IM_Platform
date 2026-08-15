import pandas as pd

p = r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.2 Portfolio Management - Monthly\1. Main (monthly report)\2.7 31 Jul 26\1. Portfolio Summary Jul'26 v2.0.xlsx"
xl = pd.ExcelFile(p)

for s in ["CF (Equity, Debt)", "CF (Funds)", "NAV"]:
    df = xl.parse(s, header=None)
    print("=====", s, "shape=", df.shape, "=====")
    print(df.head(6).to_string())
    print("... tail ...")
    print(df.tail(8).to_string())
    print()
