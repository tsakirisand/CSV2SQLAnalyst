import duckdb
import pandas as pd
import pytest
from cvs2sqlanalyst.engine import Workspace, read_csv, sample_data, MAX_ROWS


def test_csv_ingestion_and_group_query():
    frame = read_csv(b'region,revenue\nEU,10\nEU,20\nUS,5\n')
    ws = Workspace(frame)
    try:
        result, capped = ws.query('WITH totals AS (SELECT region, sum(revenue) AS total FROM dataset GROUP BY region) SELECT * FROM totals ORDER BY total DESC;')
        assert result.to_dict('records') == [{'region': 'EU', 'total': 30}, {'region': 'US', 'total': 5}]
        assert not capped
    finally:
        ws.close()


@pytest.mark.parametrize('sql', ['DROP TABLE dataset', 'SELECT 1; DELETE FROM dataset', "COPY dataset TO '/tmp/cvs2sqlanalyst.csv'", "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM read_csv('https://example.com/data.csv')"])
def test_mutations_and_external_access_blocked(sql):
    ws = Workspace(sample_data())
    try:
        with pytest.raises((ValueError, duckdb.Error)):
            ws.query(sql)
        assert ws.query('SELECT count(*) AS n FROM dataset')[0].iloc[0, 0] == 72
    finally:
        ws.close()


def test_exports_roundtrip_quotes_nulls_and_identifiers():
    frame = pd.DataFrame({'customer"name': ["O'Brien", None], 'amount': [12.5, float('nan')]})
    ws = Workspace(frame)
    other = duckdb.connect()
    try:
        other.execute(''.join(ws.sql_export()))
        assert other.execute('SELECT * FROM dataset').fetchall() == [("O'Brien", 12.5), (None, None)]
    finally:
        ws.close()
        other.close()


def test_limit_and_session_isolation():
    first = Workspace(sample_data())
    second = Workspace(pd.DataFrame({'secret': [42]}))
    try:
        rows, capped = first.query('SELECT * FROM range(12000)')
        assert len(rows) == MAX_ROWS and capped
        with pytest.raises(duckdb.Error):
            first.query('SELECT secret FROM dataset')
        assert second.query('SELECT secret FROM dataset')[0].iloc[0, 0] == 42
    finally:
        first.close()
        second.close()


def test_case_insensitive_duplicate_columns():
    frame = read_csv(b'A,a,A\n1,2,3\n')
    assert len({name.casefold() for name in frame.columns}) == 3
    ws = Workspace(frame)
    ws.close()


@pytest.mark.parametrize('content', [b'', b'a,b\n', b'\xff\xfe\x00'])
def test_bad_uploads(content):
    with pytest.raises(ValueError):
        read_csv(content)


def test_table_name_validation():
    with pytest.raises(ValueError):
        Workspace(sample_data(), 'bad; DROP TABLE dataset')


def test_single_column_csv_and_semicolon_delimiter():
    assert read_csv(b"name\nAlice\nBob\n").to_dict("list") == {"name": ["Alice", "Bob"]}
    assert read_csv(b"name;amount\nAlice;10\nBob;20\n").amount.sum() == 30


def test_query_trailing_comments():
    ws = Workspace(sample_data())
    try:
        assert ws.query("SELECT count(*) AS n FROM dataset; -- a comment")[0].iloc[0, 0] == 72
    finally:
        ws.close()
