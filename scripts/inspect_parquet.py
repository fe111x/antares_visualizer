import pandas as pd
p='data/run_AT/run_20260609_102010_TY2018_WS4_Regional_hourly_mcy4.parquet'
print('Loading',p)
df=pd.read_parquet(p)
cols=['Scenario','Sample','BZ','WS','Property','PEMMDB_TECHNOLOGY']
for c in cols:
    if c in df.columns:
        vals=df[c].dropna().unique()
        print(c,':',len(vals),'examples->',list(vals[:10]))
    else:
        print(c,': MISSING')
print('Columns:',df.columns.tolist())
print('Total rows:', len(df))
