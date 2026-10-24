"""Session-local CSV ingestion, constrained SQL execution, and SQL export."""
from io import BytesIO
from datetime import date, datetime
import re
import csv
import threading
import duckdb
import pandas as pd

MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 10_000


def identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def read_csv(content):
    if len(content) > MAX_BYTES:
        raise ValueError("Choose a CSV smaller than 25 MB.")
    if not content.strip():
        raise ValueError("This file is empty. Choose a CSV with a header and data rows.")
    try:
        decoded = content.decode("utf-8-sig")
        try:
            delimiter = csv.Sniffer().sniff(decoded[:65536], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig", sep=delimiter)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        raise ValueError("Could not read this file. Use a UTF-8 CSV with a consistent delimiter.") from exc
    if frame.empty:
        raise ValueError("The CSV needs at least one data row.")
    # DuckDB identifiers are case-insensitive; normalize collisions predictably.
    used = set()
    columns = []
    for original in frame.columns:
        base = str(original).strip() or "column"
        name, index = base, 2
        while name.casefold() in used:
            name = f"{base}_{index}"
            index += 1
        used.add(name.casefold())
        columns.append(name)
    frame.columns = columns
    return frame


class Workspace:
    def __init__(self, frame, table="dataset"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Table names must start with a letter or underscore and contain only letters, numbers, and underscores.")
        self.table = table
        self.frame = frame.copy()
        self.connection = duckdb.connect(config={"enable_external_access": False, "memory_limit": "512MB", "threads": 2})
        self.connection.register("_upload", frame)
        self.connection.execute(f"CREATE TABLE {identifier(table)} AS SELECT * FROM _upload")
        self.connection.unregister("_upload")
        self.schema = self.connection.execute(f"DESCRIBE {identifier(table)}").fetchdf()

    def query(self, sql):
        statements = self.connection.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise ValueError("Run one SELECT query at a time. WITH queries are supported; table changes are disabled.")
        clean = statements[0].query
        timer = threading.Timer(10, self.connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            result = self.connection.sql(clean).limit(MAX_ROWS + 1).df()
        finally:
            timer.cancel()
        return result.iloc[:MAX_ROWS], len(result) > MAX_ROWS

    def sql_export(self):
        columns = ",\n  ".join(f"{identifier(row.column_name)} {row.column_type}" for row in self.schema.itertuples())
        yield f"CREATE TABLE {identifier(self.table)} (\n  {columns}\n);\n\n"
        names = ", ".join(identifier(c) for c in self.frame.columns)
        for row in self.frame.itertuples(index=False, name=None):
            values = ", ".join(literal(v) for v in row)
            yield f"INSERT INTO {identifier(self.table)} ({names}) VALUES ({values});\n"

    def close(self):
        self.connection.close()


def literal(value):
    if pd.isna(value):
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


def sample_data():
    rows = []
    regions = ["Europe", "North America", "Asia Pacific", "Latin America"]
    products = ["Analytics", "Automation", "Storage"]
    for month in range(1, 7):
        for r, region in enumerate(regions):
            for p, product in enumerate(products):
                units = 18 + month * 4 + r * 3 + p * 7
                rows.append({"month": f"2026-{month:02d}-01", "region": region, "product": product, "units": units, "revenue": units * (75 + p * 45)})
    return pd.DataFrame(rows)
