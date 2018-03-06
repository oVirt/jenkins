#!/bin/env python
"""nested_config.py - Parser for automation config DSL.

This is the core logic to parse automation config.
We split the configurations in the config into 2 groups: Categories and Options
Categories are related to the jobs that should be created. They hold
information such as stage and distro.
Options are there to configure functionality of a given job. They hold
information such as repositores needed, packages, runtime_requirements, ...
We use DFS to traverse the config and yield vectors. Vectors are actually
tuples of the following form:
    (cat 1 value, cat 2 value, ..., cat N value, {options})
The product of this module is an iterator over a list of such vectors.

In order to support nested configurations, the input data must follow the
following structure (nesting is optional):
    (Note that the categories and options in the specific example are just a
     proposal and the naming is not bounded to those values)

          ABSTRACT EXAMPLE       |  SPECIFIC EXAMPLE
    =============================|====================
    category 1: category 1 value | stage: check-patch
    category 2:                  | distro:
      - category 2 value 1       |   - fc25
      - category 2 value 2       |   - fc26
    category 3:                  | arch:
      - category 3 value 1:      |   - x86_64:
          category 3 option 1    |       packages:
            - option 1 value 1   |         - package A
            - option 2 value 2   |         - package B
"""

import logging
from numbers import Number
from collections import Mapping
from itertools import permutations
from six import iteritems, string_types
from six.moves import zip, xrange


logger = logging.getLogger(__name__)


def gen_vectors(data_in, merge_options, categories, normalize=None):
    """Generate list of vectors from the given data

    :param Mapping data_in:        Nested config data to parse.
    :param function merge_options: Function that knows how to merge options
                                   (Different projects may use different merge
                                    methods)
    :param tuple categories:       Tuple of all availalbe categories. Note that
                                   the order the categories appear in this
                                   tuple is the actual order that the
                                   categories will be ordered by in the output
                                   vectors
    :param function normalize:     (optional) Function that normalizes every
                                   data in the nested config.
                                   For example, it can be used to ignore cases
                                   in the nested config.
                                   Defaults to the identity function.

    :rtype: list
    :returns: List of vectors generated from the input data
    """
    logger.info('beginning to parse config %s', data_in)
    return _aggregate(
        _dfs(data_in, categories, merge_options, normalize), merge_options
    )


def _dfs(
    data, categories, merge_options, normalize=None, seen_categories=None,
):
    """Perform a dfs on the given data and yield vectors that were found.

    This method extracts categories and options metadata from a given data.

    :param dict data:              Input data, should be in the form of
                                   automation
    :param tuple categories:       All available categories to search for.
                                   Everything that is NOT a category, will be
                                   treated as an option: (packages, repos, ...)
    :param function merge_options: Function that knows how to merge options
                                   field between two vectors.
    :param function normalize:     (optional) Function that normalizes every
                                   data in the nested config.
                                   For example, it can be used to ignore cases
                                   in the nested config.
                                   Defaults to the identity function.
    :param set seen_categories:    Keep track of visited categories when
                                   deepening in the dfs tree.
    """
    if not normalize:
        # If unset, set normalize to be identity function
        normalize = lambda x: x
    if not isinstance(data, Mapping):
        raise SyntaxError(
            'Config section must be Mapping not {0}'.format(type(data))
        )
    logger.debug('parsing data: %s', data)
    if not seen_categories:
        seen_categories = set()
    normalized_data = dict((normalize(k), v) for (k, v) in iteritems(data))
    options = dict(
        (k, v) for (k, v) in iteritems(normalized_data) if k not in categories
    )
    logger.debug('options found: %s', options)
    # If we didn't find any category in the current level, than the current
    # level may include only options. In this case we yield an empty vector
    # with options (if any)
    category_found = False
    for i, category in enumerate(categories):
        if category not in normalized_data or category in seen_categories:
            # Skip options and visited nodes
            continue
        category_found = True
        logger.debug('category found: %s', category)
        category_values = normalized_data[category]
        # Convert edge cases to lists
        if isinstance(category_values, Mapping):
            category_values = [category_values]
        elif isinstance(category_values, string_types):
            category_values = [str(category_values)]
        elif isinstance(category_values, Number):
            category_values = [str(category_values)]

        logger.debug('optional category values: %s', category_values)
        for cv in category_values:
            if isinstance(cv, Mapping):
                # cv is a Mapping where the keys are values for the level
                # category and the values are potentially nested categories
                cur_cat_val, next_node = next(iteritems(cv))
                next_level = _dfs(
                    next_node, categories, merge_options, normalize,
                    seen_categories | set([category])
                )
                for depth_vector in _aggregate(next_level, merge_options):
                    yield _compose_vector(
                        from_template=depth_vector,
                        with_options=merge_options(options, depth_vector[-1]),
                        at=i, set_=cur_cat_val,
                    )
            else:
                # cv is the value for current category, but it may be a number
                # or anything other than string so we use str() to ensure
                # we yield a string
                yield _compose_vector(
                    with_categories=categories,
                    with_options=options,
                    at=i, set_=cv,
                )
    if not category_found:
        yield _compose_vector(with_categories=categories, with_options=options)


def _compose_vector(
    with_options=None, at=None, set_=None,
    from_template=None, with_categories=None,
):
    """Given vector template or available categories, compose a new vector

    :param tuple from_template:   Template to compose the vector from.
    :param tuple with_categories: Available categories to compose the vector
                                  from.
                                  If provided, will create a template from the
                                  form: (None, None, ..., None) with the lenght
                                  of the available categories.
                                  If 'with_categories' specified,
                                  'from_template' will be ignored.
    :param str set:               (optional) Value to append to the new vector
    :param int at:                (optional) Index to where to append the given
                                             value. Default is 0
    :param dict with_options:     (optional) Options to compose the new vector
                                             with. Default is an empty dict.

    :rtype: tuple
    :returns: New composed vector
    """
    if with_categories is not None:
        template = (None,) * len(with_categories)
    else:
        template = from_template[:-1]
    if at is None:
        at = 0
    if set_ is not None:
        set_ = str(set_)
    if with_options is None:
        with_options = {}
    return template[:at] + (set_,) + template[at+1:] + (with_options,)


def _aggregate(vectors, merge_options):
    """Aggregate a list of given vectors: do cartesian multiplication on all
    the vectors in the list and _dedup the list.

    :param function merge_options: Function that knows how to merge options
                                   field between two vectors.
    :param list vectors:           A list of vectors to _aggregate
    """
    was_changed = True
    while was_changed:
        logger.debug('list of vectors was changed. aggregating')
        was_changed, vectors = \
            _cartesian_multiplication(vectors, merge_options)
        vectors = _dedup(
            sorted(vectors, key=lambda x: hash(x[:-1])),
            merge_options
        )
    logger.debug('aggregation finished. vectors were sucessfuly deduped')
    return vectors


def _cartesian_multiplication(vectors, merge_options):
    """Do cartesian multiplication between all permutations of vectors
    eventually yielding a sorted list of merged vectors and vectors that
    were not merged with any other vectors.

    :param Iterable vectors:   Iterable over vectors to try to merge.
    :param func merge_options: Function that knows how to merge options
                               fields between two vectors.

    :rtype: list
    :returns: New sorted list with merged (multiplied) vectors.
              Vectors that were not multiplied will remain on the list.
    """
    merged_vectors = []
    vectors = [[v, False] for v in vectors]
    for a, b in permutations(vectors, 2):
        logger.debug('Attempting merge: %s :: %s', a[0], b[0])
        merged = _merge(a[0], b[0], merge_options)
        if merged:
            logger.debug('Merged: %s', merged)
            a[1] = b[1] = True
            merged_vectors.append(merged)
    any_merged = bool(merged_vectors)
    unmerged_vectors = [v[0] for v in vectors if not v[1]]
    merged_vectors = merged_vectors + unmerged_vectors
    merged_vectors.sort(key=lambda v: hash(v[:-1]))
    return any_merged, merged_vectors


def _dedup(vectors, merge_options):
    """Remove duplicated vectors from a given list of vectors while merging
    option fields between duplicated vectors.

    :param vectors: Sorted list of vectors
    :param function merge_options: Function that knows how to merge options
                                   fields between two vectors.
    """
    it_lead = iter(vectors)
    # it_lead will never be empty. Even if the config given to _dfs was empty,
    # _dfs will yield at least one empty vector.
    last_v = next(it_lead)
    for vlead in it_lead:
        # we use hash(x[:-1]) because we want to group similar vectors together
        # and the last member of the vector is a mapping
        if hash(last_v[:-1]) == hash(vlead[:-1]):
            last_v = last_v[:-1] + (merge_options(last_v[-1], vlead[-1]),)
            continue
        yield last_v
        last_v = vlead
    yield last_v


def _merge(vector1, vector2, merge_options):
    """Try to merge two vectors.

    Merging two vectors means applying fields from one vector to another if
    this field is None on one of them.
    For example:
    merging (cat 1, None) with (None, cat 2) will result (cat 1, cat 2).
    However, we can't merge two vectors where in both the same category holds
    different values.
    For example:
    merging (cat 1, None) and (cat 2, None) will return None.

    :param tuple vector1:          First vector to merge
    :param tuple vector2:          Second vector to merge
    :param function merge_options: Function that knows how to merge option

    :rtype: tuple
    :returns: New merged vector. None if vectors can't be merged.
    """
    new_vector = []
    vlen = len(vector1)
    for i, s1, s2 in zip(xrange(1, vlen + 1), vector1, vector2):
        if i == vlen:
            new_vector.append(merge_options(s1, s2))
        else:
            if s1 is None and s2 is not None:
                new_vector.append(s2)
            elif s2 is None and s1 is not None:
                new_vector.append(s1)
            elif s1 == s2:
                new_vector.append(s1)
            else:
                return None
    return tuple(new_vector)
