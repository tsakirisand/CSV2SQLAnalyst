import pandas as pd
import pytest

from cvs2sqlanalyst.analysis import clean_frame, profile_columns


def test_quality_profile_counts_missing_and_distinct_values():
    frame = pd.DataFrame({'name': ['A', 'A', None], 'amount': [1, None, 3]})
    profile = profile_columns(frame).set_index('Column')
    assert profile.loc['name', 'Missing'] == 1
    assert profile.loc['name', 'Missing %'] == 33.3
    assert profile.loc['name', 'Distinct values'] == 1
    assert profile.loc['amount', 'Distinct values'] == 2


def test_combined_cleaning_order_and_original_preservation():
    frame = pd.DataFrame({'name': [' A ', 'A', ' ', 'B'], 'amount': [1., 1., None, None]})
    original = frame.copy(deep=True)
    cleaned = clean_frame(
        frame, trim=True, drop_empty=True, deduplicate=True,
        fill_column='amount', fill_strategy='Mean',
    )
    assert cleaned.to_dict('records') == [{'name': 'A', 'amount': 1.}, {'name': 'B', 'amount': 1.}]
    pd.testing.assert_frame_equal(frame, original)


def test_mean_can_fill_nullable_integer_with_fraction():
    frame = pd.DataFrame({'value': pd.Series([1, 2, None], dtype='Int64')})
    assert clean_frame(frame, fill_column='value', fill_strategy='Mean').value.tolist() == [1., 2., 1.5]


def test_zero_and_mode_filling():
    frame = pd.DataFrame({'label': ['A', None, 'A'], 'value': [1., None, 3.]})
    assert clean_frame(frame, fill_column='label', fill_strategy='Most frequent').label.tolist() == ['A', 'A', 'A']
    assert clean_frame(frame, fill_column='value', fill_strategy='Zero').value.tolist() == [1., 0., 3.]


def test_invalid_cleaning_keeps_input_unchanged():
    frame = pd.DataFrame({'name': ['A', None]})
    with pytest.raises(ValueError, match='numeric column'):
        clean_frame(frame, fill_column='name', fill_strategy='Median')
    with pytest.raises(ValueError, match='every row'):
        clean_frame(pd.DataFrame({'name': [None]}), drop_empty=True)
    with pytest.raises(ValueError, match='no non-missing'):
        clean_frame(pd.DataFrame({'name': [None]}), fill_column='name', fill_strategy='Most frequent')
    assert frame.name.isna().sum() == 1
