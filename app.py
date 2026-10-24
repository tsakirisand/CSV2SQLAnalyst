"""Streamlit interface for the session-local CVS2SQLAnalyst workbench."""
import time

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cvs2sqlanalyst.analysis import clean_frame, profile_columns
from cvs2sqlanalyst.engine import Workspace, identifier, read_csv, sample_data

TAB_LABELS = ['Overview', 'SQL Lab', 'Visualize', 'Data Quality', 'Exports']

INITIAL_SQL = (
    'SELECT region, SUM(revenue) AS total_revenue\n'
    'FROM dataset\nGROUP BY region\nORDER BY total_revenue DESC;'
)


def run_query(sql=None):
    sql = st.session_state.sql if sql is None else sql
    started = time.perf_counter()
    try:
        result, capped = st.session_state.workspace.query(sql)
        st.session_state.result = result
        st.session_state.result_sql = sql
        st.session_state.truncated = capped
        st.session_state.message = (
            f'{len(result):,} rows · {(time.perf_counter() - started) * 1000:.0f} ms.',
            False,
        )
    except Exception as exc:
        st.session_state.message = (
            f'Query failed: {exc}. Previous successful results remain below.', True
        )


def replace_workspace(frame, name, table, sql=None, *, preserve_original=False):
    new = Workspace(frame, table)
    query = sql or f'SELECT * FROM {identifier(table)} LIMIT 100;'
    try:
        result, capped = new.query(query)
    except Exception:
        new.close()
        raise
    old = st.session_state.get('workspace')
    st.session_state.update(
        workspace=new, data_name=name, result=result, result_sql=query,
        truncated=capped, sql=query,
        message=(f'Imported {len(frame):,} rows into {table}. Ready to query.', False),
    )
    if not preserve_original:
        st.session_state.original_frame = frame.copy()
        st.session_state.original_name = name
        st.session_state.update(
            clean_trim=False, clean_empty=False, clean_duplicates=False,
            fill_column=frame.columns[0], fill_strategy='Leave missing',
            profile_column=frame.columns[0],
        )
    if old is not None:
        old.close()


def import_upload():
    upload = st.session_state.upload
    if upload is None:
        st.session_state.message = ('Choose a CSV before importing.', True)
        return
    try:
        replace_workspace(
            read_csv(upload.getvalue()), upload.name,
            st.session_state.table_name.strip(),
        )
    except Exception as exc:
        st.session_state.message = (f'Import failed: {exc}', True)


def load_sample():
    replace_workspace(sample_data(), 'sample_sales.csv · demo dataset', 'dataset', INITIAL_SQL)
    st.session_state.table_name = 'dataset'


def starter_query(kind):
    ws = st.session_state.workspace
    table = identifier(ws.table)
    if kind == 'preview':
        sql = f'SELECT * FROM {table} LIMIT 100;'
    elif kind == 'count':
        sql = f'SELECT COUNT(*) AS row_count FROM {table};'
    else:
        numeric = ws.frame.select_dtypes(include='number').columns.tolist()
        categories = ws.frame.select_dtypes(exclude='number').columns.tolist()
        if not numeric or not categories:
            st.session_state.message = (
                'Group & summarize needs one text column and one numeric column. '
                'Write a custom query for this dataset.', True,
            )
            return
        category, value = identifier(categories[0]), identifier(numeric[-1])
        sql = (
            f'SELECT {category}, SUM({value}) AS total\nFROM {table}\n'
            f'GROUP BY {category}\nORDER BY total DESC;'
        )
    st.session_state.sql = sql
    run_query(sql)


def cleaning_options():
    return dict(
        trim=st.session_state.get('clean_trim', False),
        drop_empty=st.session_state.get('clean_empty', False),
        deduplicate=st.session_state.get('clean_duplicates', False),
        fill_column=st.session_state.get('fill_column'),
        fill_strategy=st.session_state.get('fill_strategy', 'Leave missing'),
    )


def apply_cleaning():
    ws = st.session_state.workspace
    try:
        frame = clean_frame(ws.frame, **cleaning_options())
        if frame.equals(ws.frame.reset_index(drop=True)):
            st.session_state.message = ('No changes were needed for the selected cleaning options.', False)
            return
        removed = len(ws.frame) - len(frame)
        replace_workspace(
            frame, st.session_state.original_name + ' · cleaned', ws.table,
            preserve_original=True,
        )
        st.session_state.message = (
            f'Cleaning applied. {removed:,} rows removed; '
            f'{int(frame.isna().sum().sum()):,} missing cells remain. SQL results refreshed.', False,
        )
    except Exception as exc:
        st.session_state.message = (f'Cleaning failed: {exc}. Your dataset is unchanged.', True)


def restore_original():
    ws = st.session_state.workspace
    replace_workspace(
        st.session_state.original_frame, st.session_state.original_name, ws.table,
        preserve_original=True,
    )
    st.session_state.message = ('Original dataset restored. SQL results refreshed.', False)


def chart_figure(frame, chart_type, x, y):
    if frame.empty or x is None or y is None:
        fig = go.Figure()
        fig.add_annotation(
            text='Run a query with a numeric column to create a chart.',
            x=.5, y=.5, xref='paper', yref='paper', showarrow=False,
        )
    else:
        plot_frame = frame.head(1000)
        if chart_type == 'Line chart':
            plot_frame = plot_frame.sort_values(x)
        fn = {'Bar chart': px.bar, 'Line chart': px.line, 'Scatter plot': px.scatter}[chart_type]
        fig = fn(plot_frame, x=x, y=y, color_discrete_sequence=['#21856a'])
        if chart_type == 'Bar chart':
            fig.update_traces(marker_line_width=0, marker_cornerradius=5)
        elif chart_type == 'Line chart':
            fig.update_traces(mode='lines+markers', line_width=3)
        fig.update_layout(title=f"{y.replace('_', ' ').title()} by {x.replace('_', ' ').title()}")
    fig.update_layout(
        template='plotly_white', height=380,
        margin=dict(l=40, r=20, t=60, b=40),
        font=dict(color='#40564e', size=12),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor='#edf1ec', zeroline=False)
    return fig


st.set_page_config(page_title='CVS2SQLAnalyst · CSV to insight', page_icon='▥', layout='wide')

if 'workspace' not in st.session_state:
    st.session_state.update(
        workspace=None, table_name='dataset', sql='', result=None,
        result_sql='', truncated=False, data_name='', message=('', False),
    )

ws = st.session_state.workspace
with st.sidebar:
    st.title('▥ CVS2SQLAnalyst')
    st.caption('CSV → SQL → INSIGHT')
    st.subheader('Connect your data')
    with st.form('import_form'):
        st.file_uploader('Upload a CSV', type=['csv'], key='upload')
        st.text_input('Table name', key='table_name')
        st.form_submit_button('Import CSV', on_click=import_upload, width='stretch')
    st.button('Load sample data', on_click=load_sample, width='stretch')
    st.divider()
    st.subheader('Table schema')
    if ws is None:
        st.caption('Import a CSV to see its columns and types.')
    else:
        st.code(ws.table, language=None)
        st.dataframe(
            ws.schema[['column_name', 'column_type']].rename(
                columns={'column_name': 'Column', 'column_type': 'Type'}
            ), hide_index=True, width='stretch',
        )
    st.caption('UTF-8 CSVs up to 25 MB. Data stays in this local app session.')

st.caption('THE DATA WORKBENCH')
st.title('Your data. A clearer picture.')
st.write('Start with a CSV. Find the answer with SQL. Bring it to life.')
if ws is None:
    empty_messages = [
        'Upload a CSV and click Import CSV to begin, or choose Load sample data to try the app.',
        'Import a dataset to run SQL queries, filter rows, and calculate grouped totals.',
        'Import data and run a query to build a bar, line, or scatter chart.',
        'Import data to inspect missing values and duplicates, preview cleaning changes, and restore the original.',
        'Import data to export query results, the full dataset, SQL scripts, charts, and a quality report.',
    ]
    for tab, description in zip(st.tabs(TAB_LABELS), empty_messages):
        with tab:
            st.info(description)
    message, error = st.session_state.message
    if message:
        (st.error if error else st.success)(message)
    st.stop()

# Workspaces from an already-open session may predate the original-data snapshot.
if 'original_frame' not in st.session_state:
    st.session_state.original_frame = ws.frame.copy()
    st.session_state.original_name = st.session_state.data_name

metrics = st.columns(3)
metrics[0].metric('Rows in dataset', f'{len(ws.frame):,}')
metrics[1].metric('Columns', len(ws.frame.columns))
metrics[2].metric('Missing cells', f'{int(ws.frame.isna().sum().sum()):,}')
message, error = st.session_state.message
if message:
    (st.error if error else st.success)(message)

result = st.session_state.result
overview, sql_tab, visualize, quality, exports = st.tabs(TAB_LABELS)

with overview:
    st.subheader('Know your dataset')
    st.caption(st.session_state.data_name)
    st.dataframe(ws.frame.head(100), hide_index=True, width='stretch', height=300)
    st.caption('First 100 rows. Use SQL Lab to filter, sort, and aggregate the full dataset.')
    st.subheader('Column explorer')
    profile_column = st.selectbox('Inspect a column', list(ws.frame.columns), key='profile_column')
    series = ws.frame[profile_column]
    details = st.columns(3)
    details[0].metric('Non-missing values', f'{series.count():,}')
    details[1].metric('Distinct values', f'{series.nunique():,}')
    details[2].metric('Missing %', f'{series.isna().mean() * 100:.1f}%')
    left, right = st.columns(2)
    with left:
        st.markdown('**Summary statistics**')
        # Strings keep mixed numeric/text/date summaries Arrow-compatible.
        summary = series.describe().rename_axis('Statistic').reset_index(name='Value')
        summary['Value'] = summary['Value'].astype(str)
        st.dataframe(summary, hide_index=True, width='stretch')
    with right:
        st.markdown('**Most common values**')
        frequent = series.dropna().value_counts().head(10).rename_axis('Value').reset_index(name='Count')
        frequent['Value'] = frequent['Value'].astype(str)
        st.dataframe(frequent, hide_index=True, width='stretch')
        st.caption('Top 10 non-missing values from the full dataset.')

with sql_tab:
    st.subheader('Query your data')
    st.caption('DuckDB SQL · one SELECT or WITH query at a time')
    with st.form('query_form'):
        st.text_area('SQL editor', key='sql', height=170)
        st.form_submit_button('Run query', type='primary', on_click=run_query)
    actions = st.columns(3)
    for column, label, kind in zip(
        actions, ['Preview rows', 'Count rows', 'Group & summarize'],
        ['preview', 'count', 'summary'],
    ):
        column.button(label, on_click=starter_query, args=(kind,), width='stretch')
    st.subheader('Explore results')
    if st.session_state.truncated:
        st.warning('Results capped at 10,000 rows. CSV exports use these same rows.')
    st.dataframe(result, hide_index=True, width='stretch', height=300)
    st.caption('Download these results in the Exports tab.')

with visualize:
    st.subheader('Find the pattern')
    st.caption('Charts use the current SQL results. Run a query in SQL Lab to change the source data.')
    columns = list(result.columns)
    numeric = list(result.select_dtypes(include='number').columns)
    for key, choices, default in [('x', columns, columns[0] if columns else None),
                                  ('y', numeric, numeric[-1] if numeric else None)]:
        if st.session_state.get(key) not in choices:
            st.session_state[key] = default
    controls = st.columns(3)
    chart_type = controls[0].selectbox(
        'Chart type', ['Bar chart', 'Line chart', 'Scatter plot'], key='chart_type',
    )
    x = controls[1].selectbox('X axis', columns, key='x', disabled=not columns)
    y = controls[2].selectbox('Y axis', numeric, key='y', disabled=not numeric)
    fig = chart_figure(result, chart_type, x, y)
    st.plotly_chart(fig, width='stretch', key='result_chart')
    if len(result) > 1000:
        st.caption('First 1,000 result rows shown. Aggregate in SQL to chart the full dataset.')
    st.caption('Source query')
    st.code(st.session_state.result_sql, language='sql')

with quality:
    st.subheader('Check data quality')
    checks = st.columns(3)
    checks[0].metric('Duplicate rows', f'{int(ws.frame.duplicated().sum()):,}')
    checks[1].metric('Fully empty rows', f'{int(ws.frame.isna().all(axis=1).sum()):,}')
    checks[2].metric('Complete rows', f'{int(ws.frame.notna().all(axis=1).sum()):,}')
    profile = profile_columns(ws.frame)
    st.dataframe(profile, hide_index=True, width='stretch')
    st.subheader('Clean your dataset')
    st.caption('Preview the effect, then apply it to the full table. The original upload remains available to restore.')
    clean_columns = st.columns(3)
    clean_columns[0].checkbox('Trim text & treat blanks as missing', key='clean_trim')
    clean_columns[1].checkbox('Remove fully empty rows', key='clean_empty')
    clean_columns[2].checkbox('Remove duplicate rows', key='clean_duplicates')
    fill_controls = st.columns(2)
    fill_controls[0].selectbox('Column to fill', list(ws.frame.columns), key='fill_column')
    fill_controls[1].selectbox(
        'Missing-value strategy', ['Leave missing', 'Most frequent', 'Mean', 'Median', 'Zero'],
        key='fill_strategy',
    )
    st.caption('Mean, Median, and Zero require a numeric column. Most frequent uses the first mode when values tie. Rows are deduplicated after filling.')
    try:
        preview = clean_frame(ws.frame, **cleaning_options())
        removed = len(ws.frame) - len(preview)
        st.info(
            f'Preview: {len(preview):,} rows after cleaning · {removed:,} rows removed · '
            f'{int(preview.isna().sum().sum()):,} missing cells remaining.'
        )
        with st.expander('Preview cleaned data'):
            st.dataframe(preview.head(100), hide_index=True, width='stretch')
        can_apply = not preview.equals(ws.frame.reset_index(drop=True))
    except (ValueError, TypeError) as exc:
        st.warning(str(exc))
        can_apply = False
    clean_actions = st.columns(2)
    clean_actions[0].button(
        'Apply cleaning', on_click=apply_cleaning, type='primary', disabled=not can_apply,
        width='stretch',
    )
    clean_actions[1].button(
        'Restore original dataset', on_click=restore_original,
        disabled=ws.frame.equals(st.session_state.original_frame), width='stretch',
    )
    st.caption('Applying or restoring data resets the SQL editor and results to a 100-row preview. Charts and exports then use the updated data.')

with exports:
    st.subheader('Take your work with you')
    st.markdown('**Query results**')
    st.caption(f'{len(result):,} rows from the last successful query; capped at 10,000 rows.')
    st.download_button(
        'Export results CSV', result.to_csv(index=False),
        'query-results.csv', 'text/csv', on_click='ignore',
    )
    st.markdown('**Full dataset**')
    st.caption(f'All {len(ws.frame):,} current rows, including any applied cleaning changes.')
    st.download_button(
        'Download full dataset CSV', lambda: ws.frame.to_csv(index=False),
        f'{ws.table}.csv', 'text/csv', on_click='ignore',
    )
    st.download_button(
        'Download SQL table', lambda: ''.join(ws.sql_export()),
        f'{ws.table}.sql', 'application/sql', on_click='ignore',
    )
    st.markdown('**Interactive chart**')
    st.caption('The current chart, packaged for offline viewing.')
    st.download_button(
        'Download chart HTML', fig.to_html(include_plotlyjs=True, full_html=True),
        'cvs2sqlanalyst-chart.html', 'text/html', on_click='ignore',
    )
    st.markdown('**Data quality report**')
    st.download_button(
        'Download quality report CSV', profile.to_csv(index=False),
        f'{ws.table}-quality.csv', 'text/csv', on_click='ignore',
    )
