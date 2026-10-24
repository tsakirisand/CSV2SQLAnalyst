"""Dataset profiling and explicit, non-mutating cleaning operations."""
import pandas as pd
from pandas.api.types import is_numeric_dtype, is_bool_dtype


def profile_columns(frame):
    return pd.DataFrame({
        'Column': frame.columns,
        'Type': [str(dtype) for dtype in frame.dtypes],
        'Missing': frame.isna().sum().to_numpy(),
        'Missing %': (frame.isna().mean() * 100).round(1).to_numpy(),
        'Distinct values': frame.nunique(dropna=True).to_numpy(),
    })


def clean_frame(frame, *, trim=False, drop_empty=False, deduplicate=False,
                fill_column=None, fill_strategy='Leave missing'):
    """Return a cleaned copy; reject changes that would remove every data row."""
    cleaned = frame.copy()
    if trim:
        for column in cleaned.select_dtypes(include=['object', 'string']).columns:
            cleaned[column] = cleaned[column].map(
                lambda value: (value.strip() or pd.NA) if isinstance(value, str) else value
            )
    if drop_empty:
        cleaned = cleaned.dropna(how='all')
    if fill_strategy != 'Leave missing':
        if fill_column not in cleaned.columns:
            raise ValueError('Choose a column to fill.')
        series = cleaned[fill_column]
        if fill_strategy == 'Most frequent':
            modes = series.mode(dropna=True)
            if modes.empty:
                raise ValueError('This column has no non-missing value to use for filling.')
            value = modes.iloc[0]
        elif fill_strategy in ('Mean', 'Median', 'Zero'):
            if not is_numeric_dtype(series) or is_bool_dtype(series):
                raise ValueError('Mean, median, and zero filling require a numeric column.')
            value = {'Mean': series.mean, 'Median': series.median, 'Zero': lambda: 0}[fill_strategy]()
            if pd.isna(value):
                raise ValueError('This column has no numeric value to use for filling.')
        else:
            raise ValueError('Choose a supported missing-value strategy.')
        # Nullable integer columns may need fractional values for mean/median.
        if fill_strategy in ('Mean', 'Median') and series.isna().any():
            series = series.astype('float64')
        cleaned[fill_column] = series.fillna(value)
    if deduplicate:
        cleaned = cleaned.drop_duplicates()
    if cleaned.empty:
        raise ValueError('These changes would remove every row. Keep at least one data row.')
    return cleaned.reset_index(drop=True)
