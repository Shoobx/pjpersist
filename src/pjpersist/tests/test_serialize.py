##############################################################################
#
# Copyright (c) 2011 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""PostGreSQL/JSONB Persistence Serialization Tests"""
import base64
import collections
import datetime
import doctest
import persistent
import pprint
import copy
import copyreg
import pickle

from pjpersist import interfaces, serialize, testing

class Top(persistent.Persistent):
    _p_pj_table = 'Top'

def create_top(name):
    top = Top()
    top.name = name
    return top

class Top2(Top):
    pass

class Tier2(persistent.Persistent):
    _p_pj_sub_object = True

class Foo(persistent.Persistent):
    _p_pj_table = 'Foo'

class Bar(persistent.Persistent):
    _p_pj_database = 'foo'
    _p_pj_table = 'Bar'

class Anything(persistent.Persistent):
    pass

class StoreType(persistent.Persistent):
    _p_pj_table = 'storetype'

class StoreType2(StoreType):
    pass

class Simple(object):
    pass

class Constant(object):
    def __reduce__(self):
        return 'Constant'
Constant = Constant()

class StringConstant(str):
    def __reduce__(self):
        return 'StringConstant'
StringConstant = StringConstant()

class CopyReggedConstant(object):
    def custom_reduce_fn(self):
        return 'CopyReggedConstant'
copyreg.pickle(CopyReggedConstant, CopyReggedConstant.custom_reduce_fn)
CopyReggedConstant = CopyReggedConstant()


def doctest_link_to_parent():
    """Link to Parent

    When an object is written, all persistent subobjects will receive a jar
    and a link to the parent object. However, if one develops their own
    `__getstate__` and `__setstate__` functions, this assignment must be done
    manually. This method provides a quick API for doing so.

    >>> foo = Foo()
    >>> commit()

    >>> foo.bar = Bar('bar')
    >>> foo.bar._p_jar is None
    True

    >>> serialize.link_to_parent(foo.bar, foo)
    >>> foo.bar._p_jar is foo._p_jar
    True
    >>> foo.bar._p_pj_doc_object is foo
    True
    """


def doctest_link_to_parent_full_example():
    """Link to Parent - Full Example

    >>> class Blah(persistent.Persistent):
    ...     def __init__(self):
    ...         self.dict = serialize.PersistentDict()
    ...     def __getstate__(self):
    ...         serialize.link_to_parent(self.dict, self)
    ...         return {'dict': dict(self.dict)}
    ...     def __setstate__(self, state):
    ...         self.dict = serialize.PersistentDict(state['dict'])

    >>> blah = Blah()
    >>> blah.dict._p_jar is None
    True

    >>> dm.root['blah'] = blah

    >>> blah.dict._p_jar is dm
    True

    >>> blah.dict[1] = 'data'
    >>> blah.dict._p_changed
    True

    >>> commit()
    >>> dm.root['blah'].dict
    {1: 'data'}
    """


def doctest_DBRef():
    """DBRef class

    Create a simple DBRef to start with:

      >>> dbref1 = serialize.DBRef('table1', '0001', 'database1')
      >>> dbref1
      DBRef('table1', '0001', 'database1')

    We can also convert the ref quickly to a JSON structure or a simple tuple:

      >>> dbref1.as_tuple()
      ('database1', 'table1', '0001')

      >>> pprint.pprint(dbref1.as_json())
      {'_py_type': 'DBREF',
       'database': 'database1',
       'id': '0001',
       'table': 'table1'}

    Note that the hash of a ref is consistent over all DBRef instances:

      >>> dbref11 = serialize.DBRef('table1', '0001', 'database1')
      >>> hash(dbref1) == hash(dbref11)
      True

    Let's make sure that some other comparisons work as well:

      >>> dbref1 == dbref11
      True

      >>> dbref1 in [dbref11]
      True

    Let's now compare to a truely different DB Ref instance:

      >>> dbref2 = serialize.DBRef('table1', '0002', 'database1')

      >>> hash(dbref1) == hash(dbref2)
      False
      >>> dbref1 == dbref2
      False
      >>> dbref1 in [dbref2]
      False

    Serialization also works well.

      >>> refp = pickle.dumps(dbref1)

      >>> dbref11 = pickle.loads(refp)
      >>> dbref1 == dbref11
      True
      >>> id(dbref1) == id(dbref11)
      False

    Don't fail on various comparisons:

      >>> dbref1 == None
      False

      >>> dbref1 == Simple
      False

      >>> dbref1 != None
      True

      >>> dbref1 != Simple
      True

    """

def doctest_ObjectSerializer():
    """Test the abstract ObjectSerializer class.

    Object serializers are hooks into the serialization process to allow
    better serialization for particular objects. For example, the result of
    reducing a datetime.date object is a short, optimized binary string. This
    representation might be optimal for pickles, but is really aweful for
    PostGreSQL, since it does not allow querying for dates. An object
    serializer can be used to use a better representation, such as the date
    ordinal number.

      >>> os = serialize.ObjectSerializer()

    So here are the methods that must be implemented by an object serializer:

      >>> os.can_read({})
      Traceback (most recent call last):
      ...
      NotImplementedError

      >>> os.read({})
      Traceback (most recent call last):
      ...
      NotImplementedError

      >>> os.can_write(object())
      Traceback (most recent call last):
      ...
      NotImplementedError

      >>> os.write(object())
      Traceback (most recent call last):
      ...
      NotImplementedError
    """

def doctest_ObjectWriter_get_table_name():
    """ObjectWriter: get_table_name()

    This method determines the table name and database for a given
    object. It can either be specified via '_p_pj_table' or is
    determined from the class path. When the table name is specified, the
    mapping from table name to class path is stored.

      >>> writer = serialize.ObjectWriter(dm)
      >>> writer.get_table_name(Anything())
      ('pjpersist_test', 'pjpersist_dot_tests_dot_test_serialize_dot_Anything')

      >>> top = Top()
      >>> writer.get_table_name(top)
      ('pjpersist_test', 'Top')

    When classes use inheritance, it often happens that all sub-objects share
    the same table. However, only one can have an entry in our mapping
    table to avoid non-unique answers. Thus we require all sub-types after the
    first one to store their typing providing a hint for deseriealization:

      >>> top2 = Top2()
      >>> writer.get_table_name(top2)
      ('pjpersist_test', 'Top')

    Since the serializer also supports serializing any object without the
    intend of storing it in PostGreSQL, we have to be abel to look up the
    table name of a persistent object without a jar being around.

      >>> writer = serialize.ObjectWriter(None)
      >>> writer.get_table_name(Bar())
      ('foo', 'Bar')

    """

def doctest_ObjectWriter_get_non_persistent_state():
    r"""ObjectWriter: get_non_persistent_state()

    This method produces a proper reduced state for custom, non-persistent
    objects.

      >>> writer = serialize.ObjectWriter(dm)

    A simple new-style class:

      >>> class This(object):
      ...     def __init__(self, num):
      ...         self.num = num

      >>> this = This(1)
      >>> pprint.pprint(writer.get_non_persistent_state(this))
      {'_py_type': '__main__.This', 'num': 1}

    A simple old-style class:

      >>> class That(object):
      ...     def __init__(self, num):
      ...         self.num = num

      >>> that = That(1)
      >>> pprint.pprint(writer.get_non_persistent_state(that))
      {'_py_type': '__main__.That', 'num': 1}

    The method also handles persistent classes that do not want their own
    document:

      >>> top = Top()
      >>> writer.get_non_persistent_state(top)
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top'}

    And then there are the really weird cases, which is the reason we usually
    have serializers for them:

      >>> orig_serializers = serialize.SERIALIZERS
      >>> serialize.SERIALIZERS = []

      >>> pprint.pprint(
      ...     writer.get_non_persistent_state(datetime.date(2011, 11, 1)))
      {'_py_factory': 'datetime.date',
       '_py_factory_args': [{'_py_type': 'BINARY', 'data': 'B9sLAQ=='}]}

      >>> serialize.SERIALIZERS = orig_serializers
    """

def doctest_ObjectWriter_get_persistent_state():
    r"""ObjectWriter: get_persistent_state()

    This method produces a proper reduced state for a persistent object, which
    is basically a DBRef.

      >>> writer = serialize.ObjectWriter(dm)

      >>> foo = Foo()
      >>> foo._p_oid

      >>> pprint.pprint(writer.get_persistent_state(foo))
      {'_py_type': 'DBREF',
       'database': 'pjpersist_test',
       'id': '0001020304050607080a0b0c0',
       'table': 'Foo'}

      >>> dm.commit(None)
      >>> foo._p_oid
      DBRef('Foo', '0001020304050607080a0b0c0', 'pjpersist_test')
      >>> dumpTable('Foo')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Foo'},
        'id': '0001020304050607080a0b0c0'}]

    The next time the object simply returns its reference:

      >>> pprint.pprint(writer.get_persistent_state(foo))
      {'_py_type': 'DBREF',
       'database': 'pjpersist_test',
       'id': '0001020304050607080a0b0c0',
       'table': 'Foo'}
      >>> dumpTable('Foo')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Foo'},
        'id': '0001020304050607080a0b0c0'}]
    """


def doctest_ObjectWriter_get_state_PJ_NATIVE_TYPES():
    """ObjectWriter: get_state(): PJ-native Types

      >>> writer = serialize.ObjectWriter(None)
      >>> writer.get_state(1)
      1
      >>> writer.get_state(1.0)
      1.0
      >>> writer.get_state('Test')
      'Test'
      >>> print(writer.get_state(None))
      None
    """

def doctest_ObjectWriter_get_state_constant():
    """ObjectWriter: get_state(): Constants

      >>> writer = serialize.ObjectWriter(None)
      >>> writer.get_state(Constant)
      {'_py_constant': 'pjpersist.tests.test_serialize.Constant'}
      >>> writer.get_state(interfaces.IObjectWriter)
      {'_py_constant': 'pjpersist.interfaces.IObjectWriter'}
      >>> writer.get_state(CopyReggedConstant)
      {'_py_constant': 'pjpersist.tests.test_serialize.CopyReggedConstant'}
      >>> writer.get_state(StringConstant)
      {'_py_constant': 'pjpersist.tests.test_serialize.StringConstant'}
    """

def doctest_ObjectWriter_get_state_types():
    """ObjectWriter: get_state(): types (type, class)

      >>> writer = serialize.ObjectWriter(None)
      >>> pprint.pprint(writer.get_state(Top))
      {'_py_type': 'type', 'path': 'pjpersist.tests.test_serialize.Top'}
      >>> pprint.pprint(writer.get_state(str))
      {'_py_type': 'type', 'path': '__builtin__.str'}
    """

def doctest_ObjectWriter_get_state_sequences():
    """ObjectWriter: get_state(): sequences (tuple, list, PersistentList)

    We convert any sequence into a simple list, since JSONB supports that
    type natively. But also reduce any sub-objects.

      >>> class Number(object):
      ...     def __init__(self, num):
      ...         self.num = num

      >>> writer = serialize.ObjectWriter(None)
      >>> pprint.pprint(writer.get_state((1, '2', Number(3))))
      [1, '2', {'_py_type': '__main__.Number', 'num': 3}]
      >>> pprint.pprint(writer.get_state([1, '2', Number(3)]))
      [1, '2', {'_py_type': '__main__.Number', 'num': 3}]
    """

def doctest_ObjectWriter_get_state_mappings():
    """ObjectWriter: get_state(): mappings (dict, PersistentDict)

    We convert any mapping into a simple dict, since JSONB supports that
    type natively. But also reduce any sub-objects.

      >>> class Number(object):
      ...     def __init__(self, num):
      ...         self.num = num

      >>> writer = serialize.ObjectWriter(None)
      >>> pprint.pprint(writer.get_state({'1': 1, '2': '2', '3': Number(3)}))
      {'1': 1, '2': '2', '3': {'_py_type': '__main__.Number', 'num': 3}}

    Unfortunately, JSONB only supports text keys. So whenever we have non-text
    keys, we need to create a less natural, but consistent structure:

      >>> pprint.pprint(writer.get_state({1: 'one', 2: 'two', 3: 'three'}))
      {'dict_data': [(1, 'one'), (2, 'two'), (3, 'three')]}

    Another edge case is when the input has a `dict_data` key

      >>> writer = serialize.ObjectWriter(None)
      >>> state = writer.get_state(
      ...     {'1': 1, 'dict_data': 'works?'})
      >>> pprint.pprint(sorted(state['dict_data']))
      [('1', 1), ('dict_data', 'works?')]

    It gets even worse with tuple keyed mappings,
    tuple keys get converted to JSON as a list,
    which need to be handled then by get_object

      >>> mapping = {
      ...     (1, 'key-one', None): 'value-one',
      ...     (2, 'key-two', True): 'value-two',
      ...     'key-three': 'value-three'}
      >>> pprint.pprint(writer.get_state(mapping))
      {'dict_data': [([1, 'key-one', None], 'value-one'),
                     ([2, 'key-two', True], 'value-two'),
                     ('key-three', 'value-three')]}

    """

def doctest_ObjectWriter_get_state_Persistent():
    """ObjectWriter: get_state(): Persistent objects

      >>> writer = serialize.ObjectWriter(dm)

      >>> top = Top()
      >>> pprint.pprint(writer.get_state(top))
      {'_py_type': 'DBREF',
       'database': 'pjpersist_test',
       'id': '0001020304050607080a0b0c',
       'table': 'Top'}

    But a persistent object can declare that it does not want a separate
    document:

      >>> top2 = Top()
      >>> top2._p_pj_sub_object = True
      >>> writer.get_state(top2, top)
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top'}
    """

def doctest_ObjectWriter_get_state_sub_doc_object_with_no_pobj():
    """ObjectWriter: get_state(): Called with a sub-document object and no pobj

    While this should not really happen, we want to make sure we are properly
    protected against it. Usually, the writer sets the jar of the parent
    object equal to its jar. But it cannot do so, if `pobj` or `pobj._p_jar`
    is `None`.

      >>> writer = serialize.ObjectWriter(dm)

      >>> t2 = Tier2()
      >>> writer.get_state(t2)
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Tier2'}

      >>> t2._p_jar is None
      True
      >>> t2._p_pj_doc_object is None
      True

    Let's now pass in a `pobj` without a jar:

      >>> top = Top()
      >>> writer.get_state(t2, top)
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Tier2'}

      >>> t2._p_jar is None
      True
      >>> t2._p_pj_doc_object is top
      True
    """

def doctest_ObjectWriter_get_state_same_obj_in_dict():
    """ObjectWriter: get_state():

    If get_state gets the very same object in a structure it must not fail.

      >>> writer = serialize.ObjectWriter(dm)

      >>> pdict = serialize.PersistentDict()
      >>> one = Simple()
      >>> one.data = 'data'
      >>> pdict['one'] = one
      >>> pdict['two'] = one

      >> from cPickle import dumps

      >> print dumps(pdict)

      >> import pickletools
      >> pickletools.dis(dumps(pdict))

      >>> pprint.pprint(writer.get_state(pdict))
      {'one': {'_py_type': 'pjpersist.tests.test_serialize.Simple',
               'data': 'data'},
       'two': {'_py_type': 'pjpersist.tests.test_serialize.Simple',
               'data': 'data'}}

    """

def doctest_ObjectWriter_get_state_same_obj_in_list():
    """ObjectWriter: get_state():

    If get_state gets the very same object in a structure it must not fail.

      >>> writer = serialize.ObjectWriter(dm)

      >>> plist = serialize.PersistentList()
      >>> one = Simple()
      >>> one.data = 'data'
      >>> plist.append(one)
      >>> plist.append(one)

      >> from cPickle import dumps

      >> print dumps(plist, protocol=0)

      >>> pprint.pprint(writer.get_state(plist))
      [{'_py_type': 'pjpersist.tests.test_serialize.Simple', 'data': 'data'},
       {'_py_type': 'pjpersist.tests.test_serialize.Simple', 'data': 'data'}]

    """

def doctest_ObjectWriter_get_full_state():
    """ObjectWriter: get_full_state()

      >>> writer = serialize.ObjectWriter(dm)

    Let's get the state of a regular object"

      >>> any = Anything()
      >>> any.name = 'anything'
      >>> pprint.pprint(writer.get_full_state(any))
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Anything',
       'name': 'anything'}

      >>> any_ref = dm.insert(any)
      >>> pprint.pprint(writer.get_full_state(any))
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Anything',
       'name': 'anything'}

    Now an object that stores its type:

      >>> st = StoreType()
      >>> st.name = 'storetype'
      >>> pprint.pprint(writer.get_full_state(st))
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.StoreType',
       'name': 'storetype'}

      >>> st_ref = dm.insert(st)
      >>> pprint.pprint(writer.get_full_state(st))
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.StoreType',
       'name': 'storetype'}
    """

def doctest_ObjectWriter_store():
    """ObjectWriter: store()

      >>> writer = serialize.ObjectWriter(dm)

    Simply store an object:

      >>> top = Top()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top'},
        'id': '0001020304050607080a0b0c0'}]

    Now that we have an object, storing an object simply means updating the
    existing document:

      >>> top.name = 'top'
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'name': 'top'},
        'id': '0001020304050607080a0b0c0'}]
    """

def doctest_ObjectWriter_store_with_new_object_references():
    """ObjectWriter: store(): new object references

    When two new objects reference each other, extracting the full state would
    cause infinite recursion errors. The code protects against that by
    optionally only creating an initial empty reference document.

      >>> writer = serialize.ObjectWriter(dm)

      >>> top = Top()
      >>> top.foo = Foo()
      >>> top.foo.top = top
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'foo': {'_py_type': 'DBREF',
                          'database': 'pjpersist_test',
                          'id': '0001020304050607080a0b0c0',
                          'table': 'Foo'}},
        'id': '0001020304050607080a0b0c0'}]
    """

def doctest_ObjectWriter_store_sub_persistent():
    """ObjectWriter: store()
    Make sure that subobject modifications get noticed after the
    first object add

      >>> writer = serialize.ObjectWriter(dm)

    Simply store an object:

      >>> top = Top()
      >>> top.top = Tier2()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'top': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Tier2'}},
        'id': '0001020304050607080a0b0c0'}]

    Now that we have an object, update the subobject property:

      >>> top.top.name = 'top'

    JUST commit here to see whether the subobject changes are noticed by the
    persistence system

      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'top': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Tier2',
                          'name': 'top'}},
        'id': '0001020304050607080a0b0c0'}]
    """

def doctest_ObjectWriter_store_notsub_persistent():
    """ObjectWriter: store()

      >>> writer = serialize.ObjectWriter(dm)

    Simply store an object:

      >>> top = Top()
      >>> top.top = Foo()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'top': {'_py_type': 'DBREF',
                          'database': 'pjpersist_test',
                          'id': '0001020304050607080a0b0c0',
                          'table': 'Foo'}},
        'id': '0001020304050607080a0b0c0'}]
      >>> dumpTable('Foo')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Foo'},
        'id': '5790ba2db25d2b42d000ccd3'}]

    Now that we have an object, update the subobject property:

      >>> top.top.name = 'top'

    JUST commit here to see whether the subobject changes are noticed by the
    persistence system

      >>> dm.commit(None)
      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'top': {'_py_type': 'DBREF',
                          'database': 'pjpersist_test',
                          'id': '0001020304050607080a0b0c0',
                          'table': 'Foo'}},
        'id': '0001020304050607080a0b0c0'}]

    Here we have the name set:

      >>> dumpTable('Foo')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Foo',
                 'name': 'top'},
        'id': '5790ba49b25d2b494600d22d'}]
    """

def doctest_ObjectReader_simple_resolve():
    """ObjectReader: simple_resolve()

    This methods simply resolves a Python path to the represented object.

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.simple_resolve('pjpersist.tests.test_serialize.Top')
      <class 'pjpersist.tests.test_serialize.Top'>

    After the original lookup, the result is cached:

      >>> pprint.pprint(serialize.PATH_RESOLVE_CACHE)
      {'pjpersist.tests.test_serialize.Top':
          <class 'pjpersist.tests.test_serialize.Top'>}

    Note that even lookup failures are cached.

      >>> reader.simple_resolve('path.to.bad')
      Traceback (most recent call last):
      ...
      ImportError: path.to.bad

      >>> pprint.pprint(serialize.PATH_RESOLVE_CACHE)
      {'path.to.bad': None,
       'pjpersist.tests.test_serialize.Top': <class 'pjpersist...Top'>}

     Resolving the path the second time uses the cache:

      >>> reader.simple_resolve('pjpersist.tests.test_serialize.Top')
      <class 'pjpersist.tests.test_serialize.Top'>

      >>> reader.simple_resolve('path.to.bad')
      Traceback (most recent call last):
      ...
      ImportError: path.to.bad
    """

def doctest_ObjectReader_resolve_simple_dblookup():
    """ObjectReader: resolve(): simple

    This methods resolves a table name to its class. The table name
    can be either any arbitrary string or a Python path.

      >>> reader = serialize.ObjectReader(dm)
      >>> ref = serialize.DBRef('Top', '4eb1b3d337a08e2de7000100')

    Now we need the doc to exist in the DB to be able to tell it's class.

      >>> reader.resolve(ref)
      Traceback (most recent call last):
      ...
      ImportError: DBRef('Top', '4eb1b3d337a08e2de7000100', None)
    """

def doctest_ObjectReader_resolve_simple_decorator():
    """ObjectReader: resolve(): decorator declared table

    This methods resolves a table name to its class. The table name
    can be either any arbitrary string or a Python path.

      >>> @serialize.table('foobar_table')
      ... class Foo(object):
      ...     pass

      >>> reader = serialize.ObjectReader(dm)
      >>> ref = serialize.DBRef('foobar_table', '4eb1b3d337a08e2de7000100')

    Once we declared on the class which table it uses, it's easy to resolve
    even without DB access.

      >>> result = reader.resolve(ref)
      >>> result
      <class '__main__.Foo'>

      >>> result is Foo
      True
    """

def doctest_ObjectReader_resolve_simple_decorator_more():
    """ObjectReader: resolve():
    decorator declared table, more classes in one table

    This methods resolves a table name to its class. The table name
    can be either any arbitrary string or a Python path.

      >>> @serialize.table('foobar_table')
      ... class FooBase(object):
      ...     pass

      >>> @serialize.table('foobar_table')
      ... class FooFoo(FooBase):
      ...     pass

      >>> reader = serialize.ObjectReader(dm)
      >>> ref = serialize.DBRef('foobar_table', '4eb1b3d337a08e2de7000100')

    As we have now more classes declared for the same table, we have to
    lookup the JSONB from the DB

      >>> result = reader.resolve(ref)
      Traceback (most recent call last):
      ...
      ImportError: DBRef('foobar_table', '4eb1b3d337a08e2de7000100', None)
    """

def doctest_ObjectReader_resolve_quick_when_type_in_doc():
    """ObjectReader: resolve(): Quick lookup when type in document.

    This methods resolves a table name to its class. The table name
    can be either any arbitrary string or a Python path.

      >>> st = StoreType()
      >>> st_ref = dm.insert(st)
      >>> st2 = StoreType2()
      >>> st2_ref = dm.insert(st2)
      >>> dm.commit(None)

    Let's now resolve the references:

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.resolve(st_ref)
      <class 'pjpersist.tests.test_serialize.StoreType'>
      >>> reader.resolve(st2_ref)
      <class 'pjpersist.tests.test_serialize.StoreType2'>

      >>> dm.commit(None)

    So here comes the trick. When fast-loading objects, the documents are made
    immediately available in the ``_latest_states`` mapping. This allows our
    quick resolve to utilize that document instead of looking it up in the
    database:

      >>> writer = serialize.ObjectWriter(dm)
      >>> tbl = dm._get_table_from_object(st)
      >>> dm._latest_states[st_ref] = writer.get_full_state(st)
      >>> dm._latest_states[st2_ref] = writer.get_full_state(st2)

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.resolve(st_ref)
      <class 'pjpersist.tests.test_serialize.StoreType'>
      >>> reader.resolve(st2_ref)
      <class 'pjpersist.tests.test_serialize.StoreType2'>

  """

def doctest_ObjectReader_resolve_lookup_with_multiple_maps():
    """ObjectReader: resolve(): lookup with multiple maps entries

    When the table name to Python path map has multiple entries, things
    are more interesting. In this case, we need to lookup the object, if it
    stores its persistent type otherwise we use the first map entry.

      >>> writer = serialize.ObjectWriter(dm)
      >>> top = Top()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')
      >>> top2 = Top2()
      >>> writer.store(top2)
      DBRef('Top', '000000000000000000000001', 'pjpersist_test')
      >>> dm.commit(None)

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.resolve(top._p_oid)
      <class 'pjpersist.tests.test_serialize.Top'>
      >>> reader.resolve(top2._p_oid)
      <class 'pjpersist.tests.test_serialize.Top2'>

      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top'},
        'id': '0001020304050607080a0b0c0'},
       {'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top2'},
        'id': '0001020304050607080a0b0c0'}]

    If the DBRef does not have an object id, then an import error is raised:

      >>> reader.resolve(serialize.DBRef('Top', None, 'pjpersist_test'))
      Traceback (most recent call last):
      ...
      ImportError: DBRef('Top', None, 'pjpersist_test')
    """

def doctest_ObjectReader_get_non_persistent_object_py_type():
    """ObjectReader: get_non_persistent_object(): _py_type

    The simplest case is a document with a _py_type:

      >>> reader = serialize.ObjectReader(dm)
      >>> state = {'_py_type': 'pjpersist.tests.test_serialize.Simple'}
      >>> save_state = copy.deepcopy(state)
      >>> reader.get_non_persistent_object(state, None).__class__
      <class 'pjpersist.tests.test_serialize.Simple'>

    Make sure that state is unchanged:

      >>> state == save_state
      True

    It is a little bit more interesting when there is some additional state:

      >>> state = {'_py_type': 'pjpersist.tests.test_serialize.Simple',
      ...          'name': 'Here'}
      >>> save_state = copy.deepcopy(state)

      >>> simple = reader.get_non_persistent_object(state, None)
      >>> simple.name
      'Here'

    Make sure that state is unchanged:

      >>> state == save_state
      True

    """

def doctest_ObjectReader_get_non_persistent_object_py_persistent_type():
    """ObjectReader: get_non_persistent_object(): _py_persistent_type

    In this case the document has a _py_persistent_type attribute, which
    signals a persistent object living in its parent's document:

      >>> top = Top()

      >>> reader = serialize.ObjectReader(dm)
      >>> state = {'_py_persistent_type': 'pjpersist.tests.test_serialize.Tier2',
      ...          'name': 'Number 2'}
      >>> save_state = copy.deepcopy(state)

      >>> tier2 = reader.get_non_persistent_object(state, top)
      >>> tier2.__class__
      <class 'pjpersist.tests.test_serialize.Tier2'>

    We keep track of the containing object, so we can set _p_changed when this
    object changes.

      >>> tier2._p_pj_doc_object.__class__
      <class 'pjpersist.tests.test_serialize.Top'>
      >>> tier2._p_jar.__class__
      <class 'pjpersist.datamanager.PJDataManager'>

    Make sure that state is unchanged:

      >>> state == save_state
      True

    """

def doctest_ObjectReader_get_non_persistent_object_py_factory():
    """ObjectReader: get_non_persistent_object(): _py_factory

    This is the case of last resort. Specify a factory and its arguments:

      >>> reader = serialize.ObjectReader(dm)

      >>> state = {'_py_factory': 'pjpersist.tests.test_serialize.create_top',
      ...          '_py_factory_args': ('TOP',)}
      >>> save_state = copy.deepcopy(state)

      >>> top = reader.get_non_persistent_object(state, None)
      >>> top.__class__
      <class 'pjpersist.tests.test_serialize.Top'>
      >>> top.name
      'TOP'

    Make sure that state is unchanged:

      >>> state == save_state
      True

    """

def doctest_ObjectReader_get_object_binary():
    """ObjectReader: get_object(): binary data

    Binary data is just converted to bytes:

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'BINARY',
      ...         'data': base64.b64encode(b'hello'),
      ...     },
      ...     None) == b'hello'
      True
    """

def doctest_ObjectReader_get_object_datetime():
    """ObjectReader: get_object(): datetime

    Serialization of date/time related objects has a special handler.

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'datetime.date',
      ...         'value': '2005-07-13',
      ...     },
      ...     None)
      datetime.date(2005, 7, 13)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'datetime.time',
      ...         'value': '17:18:10.100000',
      ...     },
      ...     None)
      datetime.time(17, 18, 10, 100000)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'datetime.datetime',
      ...         'value': '2005-07-13T17:18:10.100000',
      ...     },
      ...     None)
      datetime.datetime(2005, 07, 13, 17, 18, 10, 100000)
    """

def doctest_ObjectReader_get_object_datetime_BBB():
    """ObjectReader: get_object(): datetime (BBB)

    Originally, we did not track sub-seconds.

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'datetime.time',
      ...         'value': '17:18:10',
      ...     },
      ...     None)
      datetime.time(17, 18, 10)
      >>> reader.get_object(
      ...     {
      ...         '_py_type': 'datetime.datetime',
      ...         'value': '2005-07-13T17:18:10',
      ...     },
      ...     None)
      datetime.datetime(2005, 7, 13, 17, 18, 10)
    """

def doctest_ObjectReader_get_object_dbref():
    """ObjectReader: get_object(): DBRef

      >>> writer = serialize.ObjectWriter(dm)
      >>> top = Top()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')

    Database references load the ghost state of the object they represent:

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(top._p_oid.as_json(), None).__class__
      <class 'pjpersist.tests.test_serialize.Top'>
    """

def doctest_ObjectReader_get_object_type_ref():
    """ObjectReader: get_object(): type reference

    Type references are resolved.

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(
      ...     {'_py_type': 'type',
      ...      'path': 'pjpersist.tests.test_serialize.Simple'},
      ...     None)
      <class 'pjpersist.tests.test_serialize.Simple'>
    """

def doctest_ObjectReader_get_object_instance():
    """ObjectReader: get_object(): instance

    Instances are completely loaded:

      >>> reader = serialize.ObjectReader(dm)
      >>> simple = reader.get_object(
      ...     {'_py_type': 'pjpersist.tests.test_serialize.Simple',
      ...      'name': 'easy'},
      ...     None)
      >>> simple.__class__
      <class 'pjpersist.tests.test_serialize.Simple'>
      >>> simple.name
      'easy'
    """

def doctest_ObjectReader_get_object_sequence():
    """ObjectReader: get_object(): sequence

    Sequences become persistent lists with all objects deserialized.

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object([1, '2', 3.0], None)
      [1, '2', 3.0]
    """

def doctest_ObjectReader_get_object_mapping():
    """ObjectReader: get_object(): mapping

    Mappings become persistent dicts with all objects deserialized.

      >>> reader = serialize.ObjectReader(dm)
      >>> pprint.pprint(dict(reader.get_object({'1': 1, '2': 2, '3': 3}, None)))
      {'1': 1, '2': 2, '3': 3}

    Since JSONB does not allow for non-string keys, the state for a dict with
    non-string keys looks different:

      >>> pprint.pprint(dict(reader.get_object(
      ...     {'dict_data': [(1, '1'), (2, '2'), (3, '3')]},
      ...     None)))
      {1: '1', 2: '2', 3: '3'}

    It gets even worse with tuple keyed mappings,
    tuple keys get converted to JSON as a list,
    which need to be handled then by get_object

      >>> inp = {'dict_data': [([1, 'key-one', None], 'value-one'),
      ...                      ([2, 'key-two', True], 'value-two'),
      ...                      ('key-three', 'value-three')]}
      >>> pprint.pprint(dict(reader.get_object(inp, None)))
      {'key-three': 'value-three',
       (1, 'key-one', None): 'value-one',
       (2, 'key-two', True): 'value-two'}

    """

def doctest_ObjectReader_get_object_constant():
    """ObjectReader: get_object(): constant

      >>> reader = serialize.ObjectReader(dm)
      >>> reader.get_object(
      ...     {'_py_constant': 'pjpersist.tests.test_serialize.Constant'},
      ...     None)
      <pjpersist.tests.test_serialize.Constant object at ...>
      >>> reader.get_object(
      ...     {'_py_constant': 'pjpersist.interfaces.IObjectWriter'}, None)
      <InterfaceClass pjpersist.interfaces.IObjectWriter>
    """

def doctest_ObjectReader_get_ghost():
    """ObjectReader: get_ghost()

      >>> writer = serialize.ObjectWriter(dm)
      >>> top = Top()
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')

    The ghost object is a shell without any loaded object state:

      >>> reader = serialize.ObjectReader(dm)
      >>> gobj = reader.get_ghost(top._p_oid)
      >>> gobj._p_jar.__class__
      <class 'pjpersist.datamanager.PJDataManager'>
      >>> gobj._p_state
      0

    The second time we look up the object, it comes from cache:

      >>> gobj = reader.get_ghost(top._p_oid)
      >>> gobj._p_state
      0
    """

def doctest_ObjectReader_set_ghost_state():
    r"""ObjectReader: set_ghost_state()

      >>> writer = serialize.ObjectWriter(dm)
      >>> top = Top()
      >>> top.name = 'top'
      >>> writer.store(top)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test')

    The ghost object is a shell without any loaded object state:

      >>> reader = serialize.ObjectReader(dm)
      >>> gobj = reader.get_ghost(top._p_oid)
      >>> gobj._p_jar.__class__
      <class 'pjpersist.datamanager.PJDataManager'>
      >>> gobj._p_state
      0

    Now load the state:

      >>> reader.set_ghost_state(gobj)
      >>> gobj.name
      'top'

    """


def doctest_deserialize_persistent_references():
    """Deserialization o persistent references.

    The purpose of this test is to demonstrate the proper deserialization of
    persistent object references.

    Let's create a simple object hierarchy:

      >>> top = Top()
      >>> top.name = 'top'
      >>> top.foo = Foo()
      >>> top.foo.name = 'foo'

      >>> dm.root['top'] = top
      >>> commit()

    Let's check that the objects were properly serialized.

      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'foo': {'_py_type': 'DBREF',
                          'database': 'pjpersist_test',
                          'id': '0001020304050607080a0b0c0',
                          'table': 'Foo'},
                 'name': 'top'},
        'id': '0001020304050607080a0b0c0'}]

      >>> dumpTable('Foo')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Foo',
                 'name': 'foo'},
        'id': '0001020304050607080a0b0c0'}]

    Now we access the objects objects again to see whether they got properly
    deserialized.

      >>> top2 = dm.root['top']
      >>> id(top2) == id(top)
      False
      >>> top2.name
      'top'

      >>> id(top2.foo) == id(top.foo)
      False
      >>> top2.foo.__class__
      <class 'pjpersist.tests.test_serialize.Foo'>
      >>> top2.foo.name
      'foo'
    """


def doctest_deserialize_persistent_foreign_references():
    """
    Make sure we can reference objects from other databases.

    For this, we have to provide IPJDataManagerProvider

    First, store some object in one database
      >>> writer_other = serialize.ObjectWriter(dm_other)
      >>> top_other = Top()
      >>> top_other.name = 'top_other'
      >>> top_other.state = {'complex_data': 'value'}
      >>> writer_other.store(top_other)
      DBRef('Top', '0001020304050607080a0b0c', 'pjpersist_test_other')

    Store other object in datbase and refrence first one
      >>> writer_other = serialize.ObjectWriter(dm)
      >>> top = Top()
      >>> top.name = 'main'
      >>> top.other = top_other
      >>> dm.root['top'] = top
      >>> commit()

      >>> dumpTable('Top')
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
                 'name': 'main',
                 'other': {'_py_type': 'DBREF',
                            'database': 'pjpersist_test_other',
                            'id': '0001020304050607080a0b0c0',
                            'table': 'Top'}},
        'id': '0001020304050607080a0b0c0'}]

      >>> top = dm.root['top']
      >>> print(top.name)
      main
      >>> print(top.other.name)
      top_other
      >>> top.other.state
      {'complex_data': 'value'}
    """


def doctest_PersistentDict_equality():
    """Test basic functions if PersistentDicts

      >>> import datetime
      >>> obj1 = serialize.PersistentDict({'key':'value'})
      >>> obj2 = serialize.PersistentDict({'key':'value'})
      >>> obj3 = serialize.PersistentDict({'key':None})
      >>> obj4 = serialize.PersistentDict({'key':datetime.datetime.now()})

      >>> obj1 == obj1 and obj2 == obj2 and obj3 == obj3 and obj4 == obj4
      True

      >>> obj1 == obj2
      True

      >>> obj1 == obj3
      False

      >>> obj1 == obj4
      False

      >>> obj3 == obj4
      False
    """


def doctest_table_decorator():
    """Test serialize.table

    This is our test class

      >>> @serialize.table('foobar_table')
      ... class Foo(object):
      ...     pass

    Check that TABLE_ATTR_NAME gets set

      >>> getattr(Foo, interfaces.TABLE_ATTR_NAME)
      'foobar_table'

    Check that TABLE_KLASS_MAP gets updated

      >>> len(serialize.TABLE_KLASS_MAP)
      1
      >>> list(serialize.TABLE_KLASS_MAP['foobar_table'])
      [<class '__main__.Foo'>]

    Add a few more classes

      >>> @serialize.table('barbar_table')
      ... class Bar(object):
      ...     pass

    Another typical case, base and subclass stored in the same table

      >>> @serialize.table('foobar_table')
      ... class FooFoo(Foo):
      ...     pass

    Dump TABLE_KLASS_MAP

      >>> pprint.pprint(
      ...     [(k, sorted(v, key=lambda cls:cls.__name__))
      ...      for k, v in sorted(serialize.TABLE_KLASS_MAP.items())])
      [('barbar_table', [<class '__main__.Bar'>]),
       ('foobar_table', [<class '__main__.Foo'>, <class '__main__.FooFoo'>])]

    Edge case, using the decorator on a non class fails:

      >>> serialize.table('foobar_table')(object())
      Traceback (most recent call last):
      ...
      TypeError: ("Can't declare _p_pj_table", <object object at ...>)

    """


class CustomDict(collections.UserDict, object):
    def __getstate__(self):
        return self.data

    def __setstate__(self, state):
        self.data = state


def doctest_non_persistent_object_empty_custom():
    """ObjectReader: get_non_persistent_object(): _py_persistent_type edge case

    When the state was empty __setstate__ did not get called.
    The result is such custom objects as `CustomDict` got broken.
    The `data` attribute was never set, thus `CustomDictInstance.items()`
    or any method call failed with
    `AttributeError: 'CustomDict' object has no attribute 'data'`

      >>> top = Top()
      >>> top2 = Top()

    Set an 'empty' dict

      >>> top2.sub = CustomDict()

      >>> list(top2.sub.items())
      []

      >>> top2._p_pj_sub_object = True
      >>> writer = serialize.ObjectWriter(dm)
      >>> state = writer.get_state(top2, top)

    Look at the state of `sub` here, it has just the class path, no data
    Because some optimizations remove data.
    
      >>> pprint.pprint(state)
      {'_py_persistent_type': 'pjpersist.tests.test_serialize.Top',
       'sub': {'_py_type': 'pjpersist.tests.test_serialize.CustomDict'}}

      >>> reader = serialize.ObjectReader(dm)
      >>> newobj = reader.get_non_persistent_object(state, None)
      >>> newobj.__class__
      <class 'pjpersist.tests.test_serialize.Top'>

    Make sure that the `CustomDict` object still works despite being 'empty'.
    IOW `__setstate__` was called

      >>> list(newobj.sub.items())
      []

    """


def test_suite():
    suite = doctest.DocTestSuite(
        setUp=testing.setUp, tearDown=testing.tearDown,
        checker=testing.checker,
        optionflags=testing.OPTIONFLAGS)
    suite.layer = testing.db_layer
    return suite

