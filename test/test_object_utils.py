#!/usr/bin/env python
"""test_object_utils - Tests for object_utils
"""
import pytest
try:
    from unittest.mock import sentinel
except ImportError:
    from mock import sentinel

from scripts.object_utils import object_with_defaults, \
    object_with_cast_attrs, object_witp_opt_attrs, object_proxy


class TestObjectWithDefaults(object):
    class WithDefaults(object_with_defaults):
        default_attr1 = sentinel.attr1_default
        default_attr2 = sentinel.attr2_default
        _default_pattr1 = sentinel.pattr1_default
        _default_pattr2 = sentinel.pattr2_default

        @property
        def default_prop1(self):
            return sentinel.prop1_default

        @property
        def default_prop2(self):
            return sentinel.prop2_default

        default_parent = sentinel.parent_default

        @property
        def default_child1(self):
            return self.parent

        @property
        def default_child2(self):
            return self.parent

    class WithInheritedDefaults(WithDefaults):
        default_attr2 = sentinel.attr2_subclass_default

    def test_simple_defaults(self):
        obj = self.WithDefaults()
        assert obj.attr1 == sentinel.attr1_default
        assert obj.attr2 == sentinel.attr2_default
        obj.attr1 = sentinel.attr1_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert obj.attr2 == sentinel.attr2_default
        with pytest.raises(AttributeError) as e:
            obj.attr3
        assert str(e.value).endswith("'attr3'")

    def test_prop_defaults(self):
        obj = self.WithDefaults()
        assert obj.prop1 == sentinel.prop1_default
        assert obj.prop2 == sentinel.prop2_default
        obj.prop1 = sentinel.prop1_custom
        assert obj.prop1 == sentinel.prop1_custom
        assert obj.prop2 == sentinel.prop2_default
        with pytest.raises(AttributeError) as e:
            obj.prop3
        assert str(e.value).endswith("'prop3'")

    def test_private_defaults(self):
        obj = self.WithDefaults()
        assert obj._pattr1 == sentinel.pattr1_default
        assert obj._pattr2 == sentinel.pattr2_default
        obj._pattr1 = sentinel.pattr1_custom
        assert obj._pattr1 == sentinel.pattr1_custom
        assert obj._pattr2 == sentinel.pattr2_default
        with pytest.raises(AttributeError) as e:
            obj._pattr3
        assert str(e.value).endswith("'_pattr3'")

    def test_cascading_defaults(self):
        obj = self.WithDefaults()
        assert obj.child1 == sentinel.parent_default
        assert obj.child2 == sentinel.parent_default
        obj.parent = sentinel.parent_custom
        assert obj.child1 == sentinel.parent_custom
        assert obj.child2 == sentinel.parent_custom
        obj.child1 = sentinel.child_custom
        assert obj.child1 == sentinel.child_custom
        assert obj.child2 == sentinel.parent_custom
        assert obj.parent == sentinel.parent_custom

    def test_inherited_defaults(self):
        obj = self.WithInheritedDefaults()
        assert obj.attr1 == sentinel.attr1_default
        assert obj.attr2 == sentinel.attr2_subclass_default
        obj.attr1 = sentinel.attr1_custom
        obj.attr2 = sentinel.attr2_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert obj.attr2 == sentinel.attr2_custom


class TestObjectWithCastAttrs(object):
    class WithCastAttrs(object_with_cast_attrs):
        def _cast_attr1(self, value):
            return (value,)

    class WithInheritedCastAttrs(WithCastAttrs):
        def _cast_attr3(self, value):
            return [value]

    def test_cast_attrs(self):
        obj = self.WithCastAttrs()
        with pytest.raises(AttributeError):
            assert obj.attr1
        with pytest.raises(AttributeError):
            assert obj.attr2
        obj.attr1 = sentinel.attr1_custom
        obj.attr2 = sentinel.attr2_custom
        assert obj.attr1 == (sentinel.attr1_custom,)
        assert obj.attr2 == sentinel.attr2_custom

    def test_inherited_cast_attrs(self):
        obj = self.WithInheritedCastAttrs()
        with pytest.raises(AttributeError):
            assert obj.attr1
        with pytest.raises(AttributeError):
            assert obj.attr2
        with pytest.raises(AttributeError):
            assert obj.attr3
        with pytest.raises(AttributeError):
            assert obj.attr4
        obj.attr1 = sentinel.attr1_custom
        obj.attr2 = sentinel.attr2_custom
        obj.attr3 = sentinel.attr3_custom
        obj.attr4 = sentinel.attr4_custom
        assert obj.attr1 == (sentinel.attr1_custom,)
        assert obj.attr2 == sentinel.attr2_custom
        assert obj.attr3 == [sentinel.attr3_custom]
        assert obj.attr4 == sentinel.attr4_custom


class TestDefaultsAndCasts(object):
    class WithDefaultsAndCasts(object_with_defaults, object_with_cast_attrs):
        default_attr1 = sentinel.attr1_default

        def _cast_attr1(self, value):
            return (value,)

    def test_defaults_and_casts(self):
        obj = self.WithDefaultsAndCasts()
        print(obj.__class__.__mro__)
        # Note how default fallbacks override the casts in this configuration
        assert obj.attr1 == sentinel.attr1_default
        obj.attr1 = sentinel.attr1_custom
        assert obj.attr1 == (sentinel.attr1_custom,)

    class WithCastsAndDefaults(object_with_cast_attrs, object_with_defaults):
        default_attr1 = sentinel.attr1_default

        def _cast_attr1(self, value):
            return (value,)

    def test_casts_and_defaults(self):
        obj = self.WithCastsAndDefaults()
        print(obj.__class__.__mro__)
        assert obj.attr1 == (sentinel.attr1_default,)
        obj.attr1 = sentinel.attr1_custom
        assert obj.attr1 == (sentinel.attr1_custom,)


class TestObjectWithOptAttrs(object):
    class WithOptAttrs(object_witp_opt_attrs):
        default_attr1 = sentinel.attr1_default

        def _cast_attr1(self, value):
            return (value,)

    def test_defaults_and_casts(self):
        obj = self.WithOptAttrs()
        print(obj.__class__.__mro__)
        assert obj.attr1 == (sentinel.attr1_default,)
        obj.attr1 = sentinel.attr1_custom
        assert obj.attr1 == (sentinel.attr1_custom,)


class TestObjectProxy(object):
    class Proxied(object):
        attr1 = sentinel.attr1_default

    def test_naked_proxy(self):
        obj = self.Proxied()
        prx = object_proxy(obj)
        assert prx.attr1 == sentinel.attr1_default
        prx.attr1 = sentinel.attr1_custom
        assert prx.attr1 == sentinel.attr1_custom
        assert obj.attr1 == sentinel.attr1_custom
        with pytest.raises(AttributeError):
            obj.attr2
        with pytest.raises(AttributeError):
            prx.attr2

    class OverridingProxy(object_proxy):
        attr2 = sentinel.attr2_default

    def test_overriding_proxy(self):
        obj = self.Proxied()
        prx = self.OverridingProxy(obj)
        assert prx.attr1 == sentinel.attr1_default
        assert prx.attr2 == sentinel.attr2_default
        with pytest.raises(AttributeError):
            obj.attr2
        prx.attr1 = sentinel.attr1_custom
        prx.attr2 = sentinel.attr2_custom
        assert prx.attr1 == sentinel.attr1_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert prx.attr2 == sentinel.attr2_custom
        with pytest.raises(AttributeError):
            obj.attr2
        with pytest.raises(AttributeError):
            obj.attr3
        with pytest.raises(AttributeError):
            prx.attr3

    def test_proxy_builtins(self):
        prx = object_proxy(7)
        assert prx == 7
        assert prx > 6
        assert prx >= 7
        assert prx < 8
        assert prx <= 7


class TestProxyWithOptAttrs(object):
    class Proxied(object):
        pass

    class ProxyWithOptAttrs(object_witp_opt_attrs, object_proxy):
        default_attr1 = sentinel.attr1_default

        @property
        def default_child1(self):
            return self.attr1

    def test_proxy_with_attrs(self):
        obj = self.Proxied()
        obj.attr2 = sentinel.attr2_default
        prx = self.ProxyWithOptAttrs(obj)
        assert prx.attr1 == sentinel.attr1_default
        assert prx.attr2 == sentinel.attr2_default
        with pytest.raises(AttributeError):
            obj.attr1
        prx.attr1 = sentinel.attr1_custom
        prx.attr2 = sentinel.attr2_custom
        assert prx.attr1 == sentinel.attr1_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert prx.attr2 == sentinel.attr2_custom
        assert obj.attr2 == sentinel.attr2_custom

    def test_proxy_with_child_props(self):
        obj = self.Proxied()
        prx = self.ProxyWithOptAttrs(obj)
        assert prx.attr1 == sentinel.attr1_default
        assert prx.child1 == sentinel.attr1_default
        with pytest.raises(AttributeError):
            obj.attr1
        prx.attr1 = sentinel.attr1_custom
        assert prx.attr1 == sentinel.attr1_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert prx.child1 == sentinel.attr1_custom
        prx.child1 = sentinel.child1_custom
        assert prx.attr1 == sentinel.attr1_custom
        assert prx.child1 == sentinel.child1_custom
        assert obj.attr1 == sentinel.attr1_custom
        assert obj.child1 == sentinel.child1_custom
