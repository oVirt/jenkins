#!/usr/bin/env python
"""object_utils - Various utilities to enhance capabilities of objects and
classes
"""
import operator


class object_with_defaults(object):
    """A class that allows setting default values for attributes so that those
    attributes appear to be available on instances even if they are not
    explicitly set in the instance.

    To define a default value for an attribute 'attr' one must simply define
    the attribute 'default_attr'. For attributes with a leading underscore such
    as '_attr' the default must have a leading underscore as well e.g.
    '_default_attr'.    """
    def __getattr__(self, name):
        if name.startswith('_'):
            name_no_unders = name[1:]
            unders = '_'
        else:
            unders = ''
            name_no_unders = name
        if name_no_unders.startswith('default_'):
            # Fall back on superclass behaviour for defaults to prevent
            # infinite recursion
            return super(object_with_defaults, self).__getattribute__(name)
        default_name = unders + 'default_' + name_no_unders
        try:
            return getattr(self, default_name)
        except AttributeError:
            # If retrieving the default attribute fails, simulate failure on
            # accessing the originally requested attribute
            return super(object_with_defaults, self).__getattribute__(name)


class object_with_cast_attrs(object):
    """A class that allows intercepting of attribute value fetches and
    manipulating the value before it reaches the requester. This is useful when
    we want to make setting the attribute optional but still make the values it
    contains of deterministic type.
    To intercept access to attribute 'attr', define a method called
    '_cast_attr' that accepts the value returned from the attribute and returns
    the manipulated value.
    """
    def __getattribute__(self, name):
        try:
            value = super(object_with_cast_attrs, self).__getattribute__(name)
        except AttributeError:
            value = super(object_with_cast_attrs, self).__getattr__(name)
        try:
            cast_method = getattr(self, '_cast_' + name)
        except AttributeError:
            return value
        return cast_method(value)


class object_witp_opt_attrs(object_with_cast_attrs, object_with_defaults):
    """A class ob objects with optional attributes, which is to say attributes
    that have default values and are also cast to the right types if they are
    set. This is essentially a convenience shorthand for combining
    object_with_defaults and object_with_cast_attrs in the right way.
    """


class object_proxy(object):
    """An object that proxies and internal object passing all calls into it
    """
    __slots__ = ["_obj", "__weakref__"]

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    # proxying (special cases)
    def __getattribute__(self, name):
        try:
            return super(object_proxy, self).__getattribute__(name)
        except AttributeError:
            return getattr(object.__getattribute__(self, "_obj"), name)

    def __delattr__(self, name):
        delattr(object.__getattribute__(self, "_obj"), name)

    def __setattr__(self, name, value):
        try:
            object.__getattribute__(self, name)
        except AttributeError:
            setattr(object.__getattribute__(self, "_obj"), name, value)
            return
        super(object_proxy, self).__setattr__(name, value)

    def __nonzero__(self):
        return bool(object.__getattribute__(self, "_obj"))

    def __str__(self):
        return str(object.__getattribute__(self, "_obj"))

    def __repr__(self):
        return repr(object.__getattribute__(self, "_obj"))

    def __hash__(self):
        return hash(object.__getattribute__(self, "_obj"))

    # Some operators need to be dealt with in a special way, otherwise proxying
    # built-in types leads to strange results
    _operators = ['lt', 'le', 'eq', 'ge', 'gt', 'ne']
    # factories
    _special_names = [
        '__abs__', '__add__', '__and__', '__call__', '__cmp__', '__coerce__',
        '__contains__', '__delitem__', '__delslice__', '__div__', '__divmod__',
        '__float__', '__floordiv__', '__getitem__', '__getslice__', '__hex__',
        '__iadd__', '__iand__', '__idiv__', '__idivmod__', '__ifloordiv__',
        '__ilshift__', '__imod__', '__imul__', '__int__', '__invert__',
        '__ior__', '__ipow__', '__irshift__', '__isub__', '__iter__',
        '__itruediv__', '__ixor__', '__len__', '__long__', '__lshift__',
        '__mod__', '__mul__', '__neg__', '__oct__', '__or__', '__pos__',
        '__pow__', '__radd__', '__rand__', '__rdiv__', '__rdivmod__',
        '__reduce__', '__reduce_ex__', '__repr__', '__reversed__',
        '__rfloorfiv__', '__rlshift__', '__rmod__', '__rmul__', '__ror__',
        '__rpow__', '__rrshift__', '__rshift__', '__rsub__', '__rtruediv__',
        '__rxor__', '__setitem__', '__setslice__', '__sub__', '__truediv__',
        '__xor__', 'next',
    ]

    @classmethod
    def _create_class_proxy(cls, theclass):
        """creates a proxy for the given class"""

        def make_op_method(name):
            def method(self, *args, **kw):
                return getattr(operator, name)(
                    object.__getattribute__(self, "_obj"), *args, **kw
                )
            return method

        def make_method(name):
            def method(self, *args, **kw):
                return getattr(object.__getattribute__(self, "_obj"), name)(
                    *args, **kw
                )
            return method

        ns = {}
        for name in cls._operators:
            met_name = '__{0}__' .format(name)
            if hasattr(theclass, met_name):
                ns[met_name] = make_op_method(name)
        for name in cls._special_names:
            if hasattr(theclass, name):
                ns[name] = make_method(name)
        return type("%s(%s)" % (cls.__name__, theclass.__name__), (cls,), ns)

    def __new__(cls, obj, *args, **kwargs):
        """
        creates an proxy instance referencing `obj`. (obj, *args, **kwargs) are
        passed to this class' __init__, so deriving classes can define an
        __init__ method of their own.
        note: _class_proxy_cache is unique per deriving class (each deriving
        class must hold its own cache)
        """
        try:
            cache = cls.__dict__["_class_proxy_cache"]
        except KeyError:
            cls._class_proxy_cache = cache = {}
        try:
            theclass = cache[obj.__class__]
        except KeyError:
            cache[obj.__class__] = theclass = \
                cls._create_class_proxy(obj.__class__)
        ins = object.__new__(theclass)
        return ins
