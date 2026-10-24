"""Regression checks for Streamlit callbacks and session state across reruns."""
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def start(with_sample=True):
    app = AppTest.from_file(APP).run(timeout=20)
    assert not app.exception
    if with_sample:
        click(app, 'Load sample data')
    return app


def click(app, label):
    next(button for button in app.button if button.label == label).click().run(timeout=20)
    assert not app.exception


def query(app, sql):
    app.text_area(key='sql').set_value(sql)
    click(app, 'Run query')


def test_queries_charts_and_failed_query_preserve_results():
    app = start()
    try:
        assert app.metric[0].value == '72'
        assert len(app.session_state.result) == 4
        query(app, 'SELECT product, SUM(revenue) AS sales FROM dataset GROUP BY product')
        expected = app.session_state.result.copy()
        app.selectbox(key='chart_type').select('Line chart').run()
        assert not app.exception
        pd.testing.assert_frame_equal(app.session_state.result, expected)
        assert app.session_state.result_sql.startswith('SELECT product')
        query(app, 'DROP TABLE dataset')
        assert app.error
        pd.testing.assert_frame_equal(app.session_state.result, expected)
        click(app, 'Count rows')
        assert app.session_state.result.iloc[0, 0] == 72
        click(app, 'Load sample data')
        assert len(app.session_state.result) == 4
        assert app.text_area(key='sql').value == app.session_state.result_sql
    finally:
        app.session_state.workspace.close()


def test_empty_text_only_and_capped_results():
    app = start()
    try:
        query(app, 'SELECT region FROM dataset LIMIT 2')
        assert app.selectbox(key='y').value is None
        assert app.selectbox(key='y').disabled
        query(app, 'SELECT revenue FROM dataset WHERE FALSE')
        assert app.session_state.result.empty
        query(app, 'SELECT * FROM range(12000)')
        assert len(app.session_state.result) == 10000
        assert app.warning
    finally:
        app.session_state.workspace.close()


def test_browser_sessions_have_separate_workspaces():
    first, second = start(), start()
    try:
        assert first.session_state.workspace is not second.session_state.workspace
        query(first, 'SELECT 42 AS answer')
        assert list(second.session_state.result.columns) == ['region', 'total_revenue']
    finally:
        first.session_state.workspace.close()
        second.session_state.workspace.close()


def test_import_validation_and_sample_reset():
    app = start()
    try:
        click(app, 'Import CSV')
        assert app.error
        app.file_uploader(key='upload').upload(
            'sales.csv', b'category,amount\nCoffee,10\nCoffee,15\nBooks,30\n', 'text/csv'
        )
        app.text_input(key='table_name').set_value('sales')
        click(app, 'Import CSV')
        assert app.metric[0].value == '3'
        assert app.session_state.workspace.table == 'sales'
        assert app.text_area(key='sql').value == 'SELECT * FROM "sales" LIMIT 100;'
        click(app, 'Group & summarize')
        assert app.session_state.result.to_dict('records') == [
            {'category': 'Books', 'total': 30}, {'category': 'Coffee', 'total': 25},
        ]
        app.selectbox(key='chart_type').select('Scatter plot').run()
        assert not app.exception
        assert app.session_state.workspace.table == 'sales'
        app.text_input(key='table_name').set_value('bad name')
        click(app, 'Import CSV')
        assert app.error
        assert app.session_state.workspace.table == 'sales'
        app.file_uploader(key='upload').upload('empty.csv', b'', 'text/csv')
        click(app, 'Import CSV')
        assert app.error
        assert app.metric[0].value == '3'
        click(app, 'Load sample data')
        assert app.metric[0].value == '72'
        assert app.session_state.workspace.table == 'dataset'
    finally:
        app.session_state.workspace.close()


def test_download_payloads_match_displayed_data(monkeypatch):
    from io import StringIO
    import duckdb
    import streamlit as st

    downloads = {}
    original = st.download_button

    def capture(label, data, *args, **kwargs):
        downloads[label] = data
        return original(label, data, *args, **kwargs)

    monkeypatch.setattr(st, 'download_button', capture)
    app = start()
    other = duckdb.connect()
    try:
        query(app, 'SELECT COUNT(*) AS n FROM dataset')
        assert pd.read_csv(StringIO(downloads['Export results CSV'])).iloc[0, 0] == 72
        html = downloads['Download chart HTML']
        assert 'Plotly.newPlot' in html and '<html>' in html
        other.execute(downloads['Download SQL table']())
        assert other.execute('SELECT COUNT(*) FROM dataset').fetchone()[0] == 72
    finally:
        app.session_state.workspace.close()
        other.close()


def test_empty_startup_and_first_import():
    app = start(with_sample=False)
    assert app.session_state.workspace is None
    assert app.session_state.result is None
    assert [tab.label for tab in app.tabs] == ['Overview', 'SQL Lab', 'Visualize', 'Data Quality', 'Exports']
    assert not app.metric
    assert not app.dataframe
    assert not app.get('plotly_chart')
    click(app, 'Import CSV')
    assert app.error
    assert app.session_state.workspace is None
    app.file_uploader(key='upload').upload('own.csv', b'name,amount\nAlice,7\n', 'text/csv')
    click(app, 'Import CSV')
    try:
        assert app.metric[0].value == '1'
        assert app.session_state.result.to_dict('records') == [{'name': 'Alice', 'amount': 7}]
    finally:
        app.session_state.workspace.close()


def test_tabs_quality_cleaning_restore_and_new_upload(monkeypatch):
    import streamlit as st
    from io import StringIO
    import duckdb

    downloads = {}
    original = st.download_button

    def capture(label, data, *args, **kwargs):
        downloads[label] = data
        return original(label, data, *args, **kwargs)

    monkeypatch.setattr(st, 'download_button', capture)
    app = start(with_sample=False)
    app.file_uploader(key='upload').upload(
        'messy.csv', b'name,amount\n A ,10\nA,10\nB,\n,\n', 'text/csv',
    )
    click(app, 'Import CSV')
    try:
        assert [tab.label for tab in app.tabs] == ['Overview', 'SQL Lab', 'Visualize', 'Data Quality', 'Exports']
        original_frame = app.session_state.workspace.frame.copy()
        app.selectbox(key='profile_column').select('amount').run()
        app.checkbox(key='clean_trim').check()
        app.checkbox(key='clean_empty').check()
        app.checkbox(key='clean_duplicates').check()
        app.selectbox(key='fill_column').select('amount')
        app.selectbox(key='fill_strategy').select('Mean').run()
        assert not app.exception
        # The live workspace is untouched until Apply is clicked.
        pd.testing.assert_frame_equal(app.session_state.workspace.frame, original_frame)
        click(app, 'Apply cleaning')
        expected = [{'name': 'A', 'amount': 10.}, {'name': 'B', 'amount': 10.}]
        assert app.session_state.workspace.frame.to_dict('records') == expected
        assert app.session_state.result.to_dict('records') == expected
        assert 'cleaned' in app.session_state.data_name
        csv = pd.read_csv(StringIO(downloads['Download full dataset CSV']()))
        assert csv.to_dict('records') == expected
        quality = pd.read_csv(StringIO(downloads['Download quality report CSV']))
        assert quality['Missing'].sum() == 0
        connection = duckdb.connect()
        try:
            connection.execute(downloads['Download SQL table']())
            assert connection.execute('SELECT COUNT(*) FROM dataset').fetchone()[0] == 2
        finally:
            connection.close()
        click(app, 'Restore original dataset')
        pd.testing.assert_frame_equal(app.session_state.workspace.frame, original_frame)
        # A different import must replace the restore snapshot too.
        app.file_uploader(key='upload').upload('new.csv', b'city,n\nAthens,7\n', 'text/csv')
        click(app, 'Import CSV')
        assert app.session_state.original_frame.to_dict('records') == [{'city': 'Athens', 'n': 7}]
        assert app.selectbox(key='fill_strategy').value == 'Leave missing'
        assert not app.checkbox(key='clean_duplicates').value
        assert not app.exception
    finally:
        app.session_state.workspace.close()


def test_invalid_cleaning_preview_cannot_change_dataset():
    app = start(with_sample=False)
    app.file_uploader(key='upload').upload('nulls.csv', b'name,value\nA,\nB,\n', 'text/csv')
    click(app, 'Import CSV')
    try:
        before = app.session_state.workspace.frame.copy()
        app.selectbox(key='profile_column').select('value').run()
        assert not app.exception
        app.selectbox(key='fill_column').select('name')
        app.selectbox(key='fill_strategy').select('Mean').run()
        assert app.warning
        assert next(button for button in app.button if button.label == 'Apply cleaning').disabled
        pd.testing.assert_frame_equal(app.session_state.workspace.frame, before)
        app.selectbox(key='fill_column').select('value').run()
        assert app.warning
        assert not app.exception
        pd.testing.assert_frame_equal(app.session_state.workspace.frame, before)
    finally:
        app.session_state.workspace.close()
