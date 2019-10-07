"""test_struct_normalizer.py - Tests for structure normalization library
"""
import pytest
try:
    from unittest.mock import MagicMock, create_autospec, sentinel, call
except ImportError:
    from mock import MagicMock, create_autospec, sentinel, call

from scripts.struct_normalizer import (
    DataNormalizationError, normalize_value, scalar, list_of, map_with,
    normalize_option, mandatory, fallback_option,
)


@pytest.fixture
def a_ctx():
    return sentinel.application_context


class norm(object):
    """ Class that maks value as normalized"""
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return 'norm({})'.format(self.value)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.value == other.value


def fake_norm(ctx, value):
    """Fake normalization function"""
    return norm(value)


@pytest.fixture
def mcwrap():
    """Returns a function that lets you wrap a function with a MagicMock object
    so calls to it can be monitored
    """
    def wrap(fun):
        the_mock = create_autospec(fun, side_effect=fun)
        # Do not mask out our special attributes
        for attr in ('__mandatory__', '__default__', '__fallback_option__'):
            if hasattr(fun, attr):
                setattr(the_mock, attr, getattr(fun, attr))
        return the_mock
    return wrap


@pytest.fixture
def norm_func(mcwrap):
    return mcwrap(fake_norm)


def test_normalize_value(a_ctx, norm_func):
    # We create out own mock here because we want it to mask the return value
    value = sentinel.value
    result = normalize_value(a_ctx, value, to=norm_func)
    # Mark the result so it shows up in MagicMock's calls log
    assert norm_func.mock_calls == [call(a_ctx, value)]
    assert result == norm(value)


@pytest.mark.parametrize('value, typ ,expected', [
    ('scv0', None, 'scv0'),
    (1, None, 1),
    (['scv2', 'scv12', 'scv22'], None, DataNormalizationError),
    ({'scv3': 3, 'scv13': 13}, None, DataNormalizationError),
    ('scv4', str, 'scv4'),
    (5, str, '5'),
    (['scv6', 'scv16', 'scv26'], str, DataNormalizationError),
    ({'scv7': 7, 'scv17': 17}, str, DataNormalizationError),
    ('scv8', int, DataNormalizationError),
    (9, int, 9),
    ('1000', int, 1000),
])
def test_scalar(mcwrap, a_ctx, value, typ, expected):
    errmsg = '__special_error_message__'
    errre = '^' + errmsg + '$'
    if typ is not None:
        typ = mcwrap(typ)
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected, match=errre):
            normalize_value(a_ctx, value, to=scalar(type=typ, else_=errmsg))
    else:
        result =\
            normalize_value(a_ctx, value, to=scalar(type=typ, else_=errmsg))
        assert result == expected


@pytest.mark.parametrize('value, exp_res', [
    ([], []),
    (['lv2', 'lv12', 'lv22'], [norm('lv2'), norm('lv12'), norm('lv22')],),
    ('lv3', [norm('lv3')]),
    (4, [norm(4)]),
    ({'lv5': 15, 'lv25': 35}, [norm({'lv5': 15, 'lv25': 35})]),
    ({}, [norm({})]),
])
def test_list_of(a_ctx, norm_func, value, exp_res):
    result = normalize_value(a_ctx, value, to=list_of(norm_func))
    assert isinstance(result, list)
    assert result == exp_res


def test_mandatory(norm_func):
    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    error_msg = '__nifty_error_message__'
    result = mandatory(norm_func, else_=error_msg)
    assert result != norm_func
    assert result.__mandatory__ == error_msg
    assert not hasattr(result, '__default__')
    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    rout = result('tm1', 'tm11')
    assert rout == norm('tm11')
    norm_func.mock_calls == [call('tm1', 'tm11')]
    norm_func.reset_mock

    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    error_msg = '__spiffy_error_message__'
    def_value = sentinel.cool_default_value
    result = mandatory(norm_func, default=def_value ,else_=error_msg)
    assert result != norm_func
    assert result.__mandatory__ == error_msg
    assert result.__default__ == def_value
    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    rout = result('tm2', 'tm12')
    assert rout == norm('tm12')
    norm_func.mock_calls == [call('tm2', 'tm12')]


def test_fallback_option(norm_func):
    assert not hasattr(norm_func, '__fallback_option__')
    result = fallback_option(norm_func)
    assert result != norm_func
    assert hasattr(result, '__fallback_option__')
    assert not hasattr(norm_func, '__fallback_option__')
    rout = result('f1', 'fov1')
    assert rout == norm('fov1')
    norm_func.mock_calls == [call('f1', 'b1')]


def test_mandatory_and_fallback(norm_func):
    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    assert not hasattr(norm_func, '__fallback_option__')
    error_msg = 'mnf_error1'
    def_value = sentinel.mnf_default_value1
    result = fallback_option(
        mandatory(norm_func, default=def_value, else_=error_msg)
    )
    assert result.__mandatory__ == error_msg
    assert result.__default__ == def_value
    assert hasattr(result, '__fallback_option__')

    assert not hasattr(norm_func, '__mandatory__')
    assert not hasattr(norm_func, '__default__')
    assert not hasattr(norm_func, '__fallback_option__')
    error_msg = 'mnf_error2'
    def_value = sentinel.mnf_default_value2
    result = mandatory(
        fallback_option(norm_func), default=def_value, else_=error_msg
    )
    assert result.__mandatory__ == error_msg
    assert result.__default__ == def_value
    assert hasattr(result, '__fallback_option__')


@pytest.mark.parametrize('mp,key,nrmfunc,ex_out,ex_carg', [
    ({'o1': 11, 'o21': 31}, 'o1', fake_norm, {'o1': norm(11)}, 11),
    ({'o2': 12}, 'o22', fake_norm, {}, None),
    ({}, 'o3', fake_norm, {}, None),
    (
        {}, 'o4', mandatory(fake_norm, else_='o_error4'),
        DataNormalizationError('o_error4'), None
    ),
    (
        {'o5': 15}, 'o25', mandatory(fake_norm, else_='o_error5'),
        DataNormalizationError('o_error5'), None
    ),
    ({}, 'o6', mandatory(fake_norm, default='odef6'), {'o6': 'odef6'}, None),
    (
        {'o7': 17}, 'o27', mandatory(fake_norm, default='odef7'),
        {'o27': 'odef7'}, None
    ),
    (
        {'o8': 18}, 'o8', mandatory(fake_norm, default='odef8'),
        {'o8': norm(18)}, 18
    ),
    ({'o9': 19}, 'o29', fallback_option(fake_norm), {}, None),
    (
        {'oA': 0x1A}, 'o2A',
        fallback_option(mandatory(fake_norm, else_='o_errorA')),
        DataNormalizationError('o_errorA'), None
    ),
    (
        {}, 'oB', fallback_option(mandatory(fake_norm, default='odefB')),
        {'oB': 'odefB'}, None
    ),
    (
        {'oC': 0x1C}, 'o2C',
        fallback_option(mandatory(fake_norm, default='odefC')),
        {'o2C': 'odefC'}, None
    ),
])
def test_normalize_option(mcwrap, a_ctx, mp, key, nrmfunc, ex_out, ex_carg):
    nrmfunc = mcwrap(nrmfunc)
    if isinstance(ex_out, Exception):
        with pytest.raises(ex_out.__class__) as out_exinfo:
            normalize_option(a_ctx, mp, key, to=nrmfunc)
        assert out_exinfo.value.args == ex_out.args
    else:
        output = normalize_option(a_ctx, mp, key, to=nrmfunc)
        assert output == ex_out
    if ex_carg is not None:
        assert nrmfunc.mock_calls == [call(a_ctx, ex_carg)]
    else:
        assert nrmfunc.mock_calls == []


@pytest.mark.parametrize('options,value,expected', [
    (
        {'m1': fake_norm, 'm21': fake_norm},
        {'m1': 11, 'm21': 31, 'm41': 51, 'm61': 71},
        {'m1': norm(11), 'm21': norm(31)},
    ),
    (
        {'m2': fake_norm, 'm22': fake_norm},
        {'m2': 12, 'm42': 52, 'm62': 72},
        {'m2': norm(12)},
    ),
    (
        {'m3': fake_norm, 'm23': mandatory(fake_norm, else_='merr3')},
        {'m3': 13, 'm23': 33, 'm43': 53, 'm63': 73},
        {'m3': norm(13), 'm23': norm(33)},
    ),
    (
        {'m4': fake_norm, 'm24': mandatory(fake_norm, else_='merr4')},
        {'m4': 14, 'm44': 54, 'm64': 74},
        DataNormalizationError('merr4'),
    ),
    (
        {'m5': fake_norm, 'm25': mandatory(fake_norm, default='mdef5')},
        {'m5': 15, 'm45': 55, 'm65': 75},
        {'m5': norm(15), 'm25': 'mdef5'},
    ),
    (
        {'m6': fake_norm, 'm26': fallback_option(fake_norm)},
        {'m6': 16, 'm26': 36, 'm46': 56, 'm66': 76},
        {'m6': norm(16), 'm26': norm(36)},
    ),
    (
        {'m7': fake_norm, 'm27': fallback_option(fake_norm)},
        {'m7': 17, 'm47': 57, 'm67': 77},
        {'m7': norm(17)},
    ),
    (
        {'m8': fake_norm, 'm28': fallback_option(fake_norm)},
        38,
        {'m28': norm(38)},
    ),
    (
        {'m9': fake_norm, 'm29': fallback_option(fake_norm)},
        '39',
        {'m29': norm('39')},
    ),
    (
        {'mA': fake_norm, 'm2A': fallback_option(fake_norm)},
        [0x3A, 0x4A, 0x5A],
        {'m2A': norm([0x3A, 0x4A, 0x5A])},
    ),
    (
        {
            'mB': fake_norm,
            'm2B': mandatory(fallback_option(fake_norm), else_='merrB')
        },
        0x3B,
        {'m2B': norm(0x3B)},
    ),
    (
        {
            'mC': mandatory(fake_norm, else_='merrC'),
            'm2C': fallback_option(fake_norm)
        },
        0x3C,
        DataNormalizationError('merrC'),
    ),
    (
        {'mD': fake_norm, 'm2D': fake_norm},
        0x3D,
        {},
    ),
])
def test_map_with(a_ctx, options, value, expected):
    if isinstance(expected, Exception):
        with pytest.raises(expected.__class__) as out_exinfo:
            normalize_value(a_ctx, value, to=map_with(**options))
        assert out_exinfo.value.args == expected.args
    else:
        output = normalize_value(a_ctx, value, to=map_with(**options))
        assert output == expected
