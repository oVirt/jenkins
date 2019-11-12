"""struct_normalizer.py - Normalize data structures to a requested schema

Given a nested data structure `struct` it can be normalized into a specified
form like so:

    result = normalize_value(ctx, struct, as=list_of(
        map_with(
            'field1': fallback_option(mandtory(
                scalar(type=str, else_='Invalud value for field1'),
                else_='Missing configuration field: field1'
            )),
            'field2: scalar(),
            'field3: list_of(scalar(type=int)),
            'field4: list_of(
                map_with(
                    'x': mandatory(scalar(type=int)),
                    'y': mandatory(scalar(type=int)),
                ),
            ),
        ),
    )

The `ctx` variable is an application-specific context. It is passed to all
normalization functions and is mean to make it easier to write custom
normalization functions that accept custom application data.

Normalization functions are simply functions with the following signature:

    def normalizer(ctx, value)

The normalizer functions are meant to return a normalized value or raise an
exception. While this module provides a set of generic normalization functions
it is expected that applications would implement custom functions to perform
more complex data manipulations.
"""
from collections import Mapping, Iterable
from functools import wraps
from six import string_types, iteritems


class DataNormalizationError(Exception):
    pass


def scalar(type=None, else_='Invalid scalar specified'):
    """A normalization function generator for scalar values

    :param function type: Optional conversion function to convert a value to a
                          desired type, if not given, scalar value would be
                          returned as-is
    :param str else_:     Optional error message to raise if value is not a
                          scalar

    :rtype: function
    :returns: A function that accepts a context and a value and returns a
              scalar if the value could be converted into it, or raises the
              given error message in a DataNormalizationError exception.
              If `type` function is given, it is called with the value and the
              result is returned. If it raise a ValueError exception,
              a DataNormalizationError will be raised instead.
    """
    def normalizer(ctx, value):
        if isinstance(value, Iterable) and not isinstance(value, string_types):
            raise DataNormalizationError(else_)
        if type is None:
            return value
        try:
            return type(value)
        except ValueError:
            raise DataNormalizationError(else_)
    return normalizer


def list_of(member_type):
    """A normalization function generator for list values

    :param function member_type: A normalization function for members of the
                                 list
    :rtype: function
    :returns: A function that accepts a context and a value and returns a list
              where each member had been normalized with the given
              normalization function. If the value is not a list, it is
              converted into a list of a single normalized value.
    """
    def normalizer(ctx, value):
        if isinstance(value, string_types) or isinstance(value, Mapping):
            lst = [value]
        elif isinstance(value, Iterable):
            lst = value
        else:
            lst = [value]
        return [normalize_value(ctx, val, to=member_type) for val in lst]
    return normalizer


def map_with(**options):
    """A normalization function generator for mapping values

    Each keyword argument points to a normalization function, so that if that
    keyword appears as key in the input map, it is included in the normalized
    map with the value normalized by the function.

    If a given normalization function has a __default__ attribute, and the
    keyword that points to it is not included in the input, the value of the
    attribute is placed in the output map.

    If a given normalization function has a __mandatory__ attribute, the
    keyword that points to it must be included in the input (Unless is also has
    the __default__ attribute). Otherwise, the value of the __mandatory__
    attribute is used as an error message in a raised DataNormalizationError.

    If the input is not a map, a keyword argument is looked for that point to a
    function that includes the __fallback_option__ attribute. If found, a map
    is generated with the keyword pointing to the value which is then
    normalized with the normalization function the keyword points to. If not
    found a DataNormalizationError exception is raised.

    :rtype: function
    :returns: A normalization function that accepts a context and a value
              and normalizes it according to the rules specified above
    """
    fallback_key = next((
        key for key, norm_func in iteritems(options)
        if hasattr(norm_func, '__fallback_option__')
    ), None)

    def normalizer(ctx, value):
        if isinstance(value, Mapping):
            srcmap = value
        elif fallback_key is None:
            srcmap = {}
        else:
            srcmap = { fallback_key: value }
        dstmap = {}
        for key, norm_func in iteritems(options):
            dstmap.update(normalize_option(ctx, srcmap, key, to=norm_func))
        return dstmap
    return normalizer


def normalize_option(ctx, mp, key, to):
    """Normalize a single option in a map

    :param object ctx:  A context to pass to normalization function
    :param dict mp:     An input map
    :param str key:     The name of the option to normalize
    :param function to: A normalization function used to normalize the value
                        pointed to by `key` in the input map

    The normalization function can be annotated with the __mandatory__ and
    __default__ attributes to define behaviour if the option does not exist in
    the input map, as specified in the docstring for `map_with`.

    :rtype: dict
    :returns: If `key` found in `mp`, then a map with `key` pointing to a
              normalized value, otherwise, may return an empty map, a map
              with a default value or raise an exception according to wither
              __mandatory__ and __default__ are set on the `to` function.
    """
    if key in mp:
        return {key: normalize_value(ctx, mp[key], to)}
    elif hasattr(to, '__mandatory__'):
        if hasattr(to, '__default__'):
            return {key: to.__default__}
        else:
            raise DataNormalizationError(to.__mandatory__)
    else:
        return {}


def mandatory(value_type, default=None, else_='Mandatory option missing'):
    """Annotate a normalization function to indicate a mandatory option

    :param function value_type: A normalization function to annotate
    :param object default:      An optional default value to associate with the
                                function
    :param str else_:           An error message for the case where a mandatory
                                value is missing
    :rtype: function
    :returns: A function that calls `value_type` and has the __mandatory__ and
              optionally __default__ attributes set so it conforms with the
              requirements of the `map_with` and `normalize_option` functions.
    """
    @wraps(value_type)
    def normalizer(*args, **kwargs):
        return value_type(*args, **kwargs)
    normalizer.__mandatory__ = else_
    if default is not None:
        normalizer.__default__ = default
    return normalizer


def fallback_option(value_type):
    """Annotate a normalization function to indicate a fallback option

    :param function value_type: A normalization function to annotate

    :rtype: function
    :returns: A function that calls `value_type` and has the
              __fallback__option__ attribute set so it conforms with the
              requirements of the `map_with` and `normalize_option` functions.
    """
    @wraps(value_type)
    def normalizer(*args, **kwargs):
        return value_type(*args, **kwargs)
    normalizer.__fallback_option__ = True
    return normalizer


def normalize_value(ctx, value, to):
    """Normalize a single value

    :param object ctx:   A context to pass to normalization function
    :param object value: A value to normalize
    :param function to:  A normalization function

    Call the `to` function passing in `ctx` and `value`, and returning the
    result. The is the core of the normalization mini-DSL.

    :rtype: object
    :returns: Whatever the `to` function returns
    """
    return to(ctx, value)


def all_of(*normalizers):
    """Chain normalization functions together

    :param list normalizers: A list of two or more normalization functions
                             that should be a applied to a value
    :rtype: function
    :returns: A normalization function that calls all the given normalization
              functions in a chain, generating a value that is normalized by
              all of them.
    """
    def normalizer(ctx, value):
        for nrmfun in normalizers:
            value = normalize_value(ctx, value, to=nrmfun)
        return value
    for nrmfun in normalizers:
        normalizer = wraps(nrmfun)(normalizer)
    return normalizer
