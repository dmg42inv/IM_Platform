"""Portfolio time-series database package.

Ingests every monthly "Portfolio Summary" tracker (across all FY archive
folders) into a single SQLite database so portfolio metrics (NAV, invested,
distributions, gain, ...) can be queried as a time series - e.g. how the NAV
profile has evolved month by month - independently of the source workbooks.
"""
