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
"""PJ Data Manager Tests"""
import doctest
import persistent
import unittest
import logging
from pprint import pprint

import transaction
import mock
from zope.testing import module

from pjpersist import interfaces, serialize, testing, datamanager

class Root(persistent.Persistent):
    pass

class Foo(persistent.Persistent):
    name = None

    def __init__(self, name=None):
        self.name = name

    def __repr__(self):
        return '<%s %s>' %(self.__class__.__name__, self.name)

class Super(persistent.Persistent):
    _p_pj_table = 'Super'

    def __init__(self, name=None):
        self.name = name

    def __repr__(self):
        return '<%s %s>' %(self.__class__.__name__, self.name)


class Sub(Super):
    pass


class Bar(persistent.Persistent):
    _p_pj_sub_object = True

    def __init__(self, name=None):
        super(Bar, self).__init__()
        self.name = name

    def __repr__(self):
        return '<%s %s>' %(self.__class__.__name__, self.name)


class FooItem(object):
    def __init__(self):
        self.bar = 6

class ComplexFoo(persistent.Persistent):
    def __init__(self):
        self.item = FooItem()
        self.name = 'complex'

def doctest_Root():
    r"""Root: General Test

    This class represents the root(s) of the object tree. All roots are stored
    in a specified table. Since the rooted object needs to immediately
    provide a data manager (jar), the operations on the DB root are not art of
    the transaction mechanism.

      >>> root = datamanager.Root(dm, 'proot')

    Initially the root is empty:

      >>> root.keys()
      []

    Let's now add an item:

      >>> foo = Foo()
      >>> root['foo'] = foo
      >>> root.keys()
      [u'foo']
      >>> root['foo'] == foo
      True

    Root objects can be overridden:

      >>> foo2 = Foo()
      >>> root['foo'] = foo2
      >>> root.keys()
      [u'foo']
      >>> root['foo'] == foo
      False

    And of course we can delete an item:

      >>> del root['foo']
      >>> root.keys()
      []
    """

def doctest_PJDataManager_get_table_from_object():
    r"""PJDataManager: _get_table_from_object(obj)

    Get the table for an object.

      >>> foo = Foo('1')
      >>> foo_ref = dm.insert(foo)
      >>> dm.reset()

      >>> dbname, table = dm._get_table_from_object(foo)

    We are returning the database and table name pair.

      >>> dbname, table
      ('pjpersist_test', 'pjpersist_dot_tests_dot_test_datamanager_dot_Foo')
    """

def doctest_PJDataManager_object_dump_load_reset():
    r"""PJDataManager: dump(), load(), reset()

    The PJ Data Manager is a persistent data manager that manages object
    states in a PostGreSQL database accross Python transactions.

    There are several arguments to create the data manager, but only the
    psycopg2 connection is required:

      >>> dm = datamanager.PJDataManager(
      ...     conn,
      ...     root_table = 'proot')

    There are two convenience methods that let you serialize and de-serialize
    objects explicitly:

      >>> foo = Foo()
      >>> dm.dump(foo)
      DBRef('pjpersist_dot_tests_dot_test_datamanager_dot_Foo',
            '0001020304050607080a0b0c',
            'pjpersist_test')

    When the object is modified, ``dump()`` will remove it from the list of
    registered objects.

      >>> foo.name = 'Foo'
      >>> foo._p_changed
      True
      >>> dm._registered_objects.values()
      [<Foo Foo>]

      >>> foo_ref = dm.dump(foo)

      >>> foo._p_changed
      False
      >>> dm._registered_objects
      {}

      >>> dm.commit(None)

    Let's now reset the data manager, so we do not hit a cache while loading
    the object again:

      >>> dm.reset()

    We can now load the object:

      >>> foo2 = dm.load(foo._p_oid)
      >>> foo == foo2
      False
      >>> foo._p_oid = foo2._p_oid
    """


def doctest_PJDataManager_insertWithExplicitId():
    """
    Objects can be inserted by specifying new object id explicitly.

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo, '000000000000000000000001')
      >>> dm.tpc_finish(None)

    Now, Foo object should be have the provided id

      >>> foo._p_oid.id
      '000000000000000000000001'
  """


def doctest_PJDataManager_flush():
    r"""PJDataManager: flush()

    This method writes all registered objects to PsotGreSQL. It can be used at
    any time during the transaction when a dump is necessary, but is also used
    at the end of the transaction to dump all remaining objects.

    Let's now add an object to the database and reset the manager like it is
    done at the end of a transaction:

      >>> foo = Foo('foo')
      >>> foo_ref = dm.dump(foo)
      >>> dm.commit(None)

    Let's now load the object again and make a modification:

      >>> foo_new = dm.load(foo._p_oid)
      >>> foo_new.name = 'Foo'

    The object is now registered with the data manager:

      >>> dm._registered_objects.values()
      [<Foo Foo>]

    Let's now flush the registered objects:

      >>> dm.flush()

    There are several side effects that should be observed:

    * During a given transaction, we guarantee that the user will always receive
      the same Python object. This requires that flush does not reset the object
      cache.

        >>> id(dm.load(foo._p_oid)) == id(foo_new)
        True

    * The object is removed from the registered objects and the ``_p_changed``
      flag is set to ``False``.

        >>> dm._registered_objects
        {}
        >>> foo_new._p_changed
        False
    """

def doctest_PJDataManager_insert():
    r"""PJDataManager: insert(obj)

    This method inserts an object into the database.

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)

    After insertion, the original is not changed:

      >>> foo._p_changed
      False

    It is also added to the list of inserted objects:

      >>> dm._inserted_objects.values()
      [<Foo foo>]

    Let's make sure it is really in PostGreSQL:

      >>> dm.commit(None)

      >>> foo_new = dm.load(foo_ref)
      >>> foo_new
      <Foo foo>

    Notice, that we cannot insert the object again:

      >>> dm.insert(foo_new)
      Traceback (most recent call last):
      ...
      ValueError: ('Object._p_oid is already set.', <Foo foo>)

    Finally, registering a new object will not trigger an insert, but only
    schedule the object for writing. This is done, since sometimes objects are
    registered when we only want to store a stub since we otherwise end up in
    endless recursion loops.

      >>> foo2 = Foo('Foo 2')
      >>> dm.register(foo2)

      >>> dm._registered_objects.values()
      [<Foo Foo 2>]

    But storing works as expected (flush is implicit before find):

      >>> dm.flush()
      >>> dumpTable(dm._get_table_from_object(foo2)[1])
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'foo'},
        'id': u'0001020304050607080a0b0c0'},
       {'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'Foo 2'},
        'id': u'0001020304050607080a0b0c0'}]
    """


def doctest_PJDataManager_remove():
    r"""PJDataManager: remove(obj)

    This method removes an object from the database.

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)

      >>> dm.commit(None)

    Let's now load the object and remove it.

      >>> foo_new = dm.load(foo_ref)
      >>> dm.remove(foo_new)

    The object is removed from the table immediately:

      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []

    Also, the object is added to the list of removed objects:

      >>> dm._removed_objects.values()
      [<Foo foo>]

    Note that you cannot remove objects that are not in the database:

      >>> dm.remove(Foo('Foo 2'))
      Traceback (most recent call last):
      ValueError: ('Object._p_oid is None.', <Foo Foo 2>)

    There is an edge case, if the object is inserted and removed in the same
    transaction:

      >>> dm.commit(None)

      >>> foo3 = Foo('Foo 3')
      >>> foo3_ref = dm.insert(foo3)
      >>> dm.remove(foo3)

    In this case, the object is removed from PostGreSQL and from the inserted
    object list, but it is still added to removed object list, just in case we
    know if it was removed.

      >>> dm._inserted_objects
      {}
      >>> dm._removed_objects.values()
      [<Foo Foo 3>]

    """


def doctest_PJDataManager_insert_remove():
    r"""PJDataManager: insert and remove in the same transaction

    Let's insert an object:

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)

    And remove it ASAP:

      >>> dm.remove(foo)

      >>> dm._inserted_objects
      {}
      >>> dm._removed_objects.values()
      [<Foo foo>]

      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []

    """


def doctest_PJDataManager_insert_remove_modify():
    r"""PJDataManager: insert and remove in the same transaction

    Let's insert an object:

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)

    And remove it ASAP:

      >>> dm.remove(foo)

      >>> dm._inserted_objects
      {}
      >>> dm._removed_objects.values()
      [<Foo foo>]

      >>> foo.name = 'bar'
      >>> dm._removed_objects.values()
      [<Foo bar>]
      >>> dm._registered_objects.values()
      []

      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []

      >>> dm.reset()

    """

def doctest_PJDataManager_remove_modify_flush():
    r"""PJDataManager: An object is modified after removal.

    Let's insert an object:

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)
      >>> dm.reset()

    Let's now remove it:

      >>> dm.remove(foo)
      >>> dm._removed_objects.values()
      [<Foo foo>]

    Within the same transaction we modify the object. But the object should
    not appear in the registered objects list.

      >>> foo._p_changed = True
      >>> dm._registered_objects
      {}

    Now, because of other lookups, the changes are flushed, which should not
    restore the object.

      >>> dm._flush_objects()
      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []
      >>> dm.reset()

    """

def doctest_PJDataManager_remove_flush_modify():
    r"""PJDataManager: An object is removed, DM flushed, object modified

    Let's insert an object:

      >>> foo = Foo('foo')
      >>> foo_ref = dm.insert(foo)
      >>> dm.reset()

    Let's now remove it:

      >>> foo._p_changed = True
      >>> dm.remove(foo)
      >>> dm._removed_objects.values()
      [<Foo foo>]

    Now, because of other lookups, the changes are flushed, which should not
    restore the object.

      >>> dm._flush_objects()
      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []

    Within the same transaction we modify the object. But the object should
    not appear in the registered objects list.

      >>> foo._p_changed = True
      >>> dm._registered_objects
      {}

      >>> dumpTable(dm._get_table_from_object(foo)[1])
      []

      >>> dm.reset()

    """


def doctest_PJDataManager_setstate():
    r"""PJDataManager: setstate()

    This method loads and sets the state of an object and joins the
    transaction.

      >>> foo = Foo(u'foo')
      >>> ref = dm.dump(foo)

      >>> dm.commit(None)
      >>> dm._needs_to_join
      True

      >>> foo2 = Foo()
      >>> foo2._p_oid = ref
      >>> dm.setstate(foo2)
      >>> foo2.name
      u'foo'

      >>> dm._needs_to_join
      False
    """


def doctest_PJDataManager_setstate_twice():
    r"""PJDataManager: setstate()

    `setstate` and in turn `set_ghost_state` must not muck with the state
    stored in `_latest_states` otherwise the next setstate will fail badly
    IOW `get_non_persistent_object` must not change it's parameter `state`
    this is a more high level test for the same

      >>> foo = Foo(u'foo')

      >>> import zope.interface
      >>> ifaces = (zope.interface.Interface, )
      >>> zope.interface.directlyProvides(foo, tuple(ifaces))

      >>> zope.interface.Interface.providedBy(foo)
      True

      >>> ref = dm.dump(foo)

      >>> dm.commit(None)
      >>> dm._needs_to_join
      True

      >>> foo2 = Foo()
      >>> foo2._p_oid = ref
      >>> dm.setstate(foo2)
      >>> foo2.name
      u'foo'

      >>> zope.interface.Interface.providedBy(foo2)
      True

      >>> foo3 = Foo()
      >>> foo3._p_oid = ref
      >>> dm.setstate(foo3)
      >>> foo3.name
      u'foo'

      >>> zope.interface.Interface.providedBy(foo3)
      True
    """


def doctest_PJDataManager_oldstate():
    r"""PJDataManager: oldstate()

    Loads the state of an object for a given transaction. Since we are not
    supporting history, this always raises a key error as documented.

      >>> foo = Foo(u'foo')
      >>> dm.oldstate(foo, '0')
      Traceback (most recent call last):
      ...
      KeyError: '0'
    """

def doctest_PJDataManager_register():
    r"""PJDataManager: register()

    Registers an object to be stored.

      >>> dm.reset()
      >>> dm._needs_to_join
      True
      >>> len(dm._registered_objects)
      0

      >>> foo = Foo(u'foo')
      >>> dm.register(foo)

      >>> dm._needs_to_join
      False
      >>> len(dm._registered_objects)
      1

   But there are no duplicates:

      >>> dm.register(foo)
      >>> len(dm._registered_objects)
      1
    """

def doctest_PJDataManager_abort():
    r"""PJDataManager: abort()

    Aborts a transaction, which clears all object and transaction registrations:

      >>> foo = Foo()
      >>> dm._registered_objects = {id(foo): foo}
      >>> dm._needs_to_join = False

      >>> dm.abort(transaction.get())

      >>> dm._needs_to_join
      True
      >>> len(dm._registered_objects)
      0

    Let's now create a more interesting case with a transaction that inserted,
    removed and changed objects.

    First let's create an initial state:

      >>> dm.reset()
      >>> foo_ref = dm.insert(Foo('one'))
      >>> foo2_ref = dm.insert(Foo('two'))
      >>> dm.commit(None)

      >>> dbanme, table = dm._get_table_from_object(Foo())
      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'one'},
        'id': u'0001020304050607080a0b0c0'},
       {'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'two'},
        'id': u'0001020304050607080a0b0c0'}]

    Now, in a second transaction we modify the state of objects in all three
    ways:

      >>> foo = dm.load(foo_ref)
      >>> foo.name = '1'
      >>> dm._registered_objects.values()
      [<Foo 1>]

      >>> foo2 = dm.load(foo2_ref)
      >>> dm.remove(foo2)
      >>> dm._removed_objects.values()
      [<Foo two>]

      >>> foo3_ref = dm.insert(Foo('three'))

      >>> dm.flush()
      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'1'},
        'id': u'0001020304050607080a0b0c0'},
       {'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'three'},
        'id': u'0001020304050607080a0b0c0'}]

    Let's now abort the transaction and everything should be back to what it
    was before:

      >>> dm.abort(transaction.get())
      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'one'},
        'id': u'0001020304050607080a0b0c0'},
       {'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'two'},
        'id': u'0001020304050607080a0b0c0'}]
    """


def doctest_PJDataManager_abort_subobjects():
    r"""PJDataManager: abort(): Correct restoring of complex objects

    Object, that contain subobjects should be restored to the state, exactly
    matching one before initial loading.

    1. Create a single record and make sure it is stored in db

      >>> dm.reset()
      >>> foo1_ref = dm.insert(ComplexFoo())
      >>> dm.commit(None)

      >>> dbname, table = dm._get_table_from_object(ComplexFoo())
      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.ComplexFoo',
                 u'item': {u'_py_type': u'pjpersist.tests.test_datamanager.FooItem',
                           u'bar': 6},
                 u'name': u'complex'},
        'id': u'0001020304050607080a0b0c0'}]

    2. Modify the item and flush it to database

      >>> foo1 = dm.load(foo1_ref)
      >>> foo1.name = 'modified'
      >>> dm.flush()

      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.ComplexFoo',
                 u'item': {u'_py_type': u'pjpersist.tests.test_datamanager.FooItem',
                           u'bar': 6},
                 u'name': u'modified'},
        'id': u'0001020304050607080a0b0c0'}]

    3. Abort the current transaction and expect original state is restored

      >>> dm.abort(transaction.get())
      >>> dumpTable(table)
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.ComplexFoo',
                 u'item': {u'_py_type': u'pjpersist.tests.test_datamanager.FooItem',
                           u'bar': 6},
                 u'name': u'complex'},
        'id': u'0001020304050607080a0b0c0'}]
    """

def doctest_PJDataManager_tpc_begin():
    r"""PJDataManager: tpc_begin()

    This is a non-op for the PJ data manager.

      >>> dm.tpc_begin(transaction.get())
    """

def doctest_PJDataManager_tpc_vote():
    r"""PJDataManager: tpc_vote()

    This is a non-op for the PJ data manager.

      >>> dm.tpc_vote(transaction.get())
    """

def doctest_PJDataManager_tpc_finish():
    r"""PJDataManager: tpc_finish()

    This method finishes the two-phase commit. In our simple implementation,
    ``tpc_finish()`` is the same as ``commit()``. So let's store a simple object:

      >>> foo = Foo()
      >>> dm._registered_objects = {id(foo): foo}
      >>> dm.tpc_finish(transaction.get())

    Note that objects cannot be stored twice in the same transaction:

      >>> dm.reset()
      >>> dm._registered_objects = {id(foo): foo, id(foo): foo}
      >>> dm.tpc_finish(transaction.get())

    Also, when a persistent sub-object is stored that does not want its own
    document, then its parent is stored instead, still avoiding dual storage.

      >>> dm.reset()
      >>> foo2 = dm.load(foo._p_oid)
      >>> foo2.bar = Bar()
    """

def doctest_PJDataManager_tpc_abort():
    r"""PJDataManager: tpc_abort()

    Aborts a two-phase commit. This is simply the same as the regular abort.

      >>> foo = Foo()
      >>> dm._registered_objects = {id(foo): foo}
      >>> dm._needs_to_join = False

      >>> dm.tpc_abort(transaction.get())

      >>> dm._needs_to_join
      True
      >>> len(dm._registered_objects)
      0
    """


def doctest_PJDataManager_transaction_abort_after_query():
    r"""

    When we perform illegal sql, connection is set to "aborted" state, and you
    cannot execute any more queries on it. However, after you abort the
    transaction, you can continue.

    Let's execute bad SQL

      >>> foo = Foo()
      >>> cur = dm.getCursor()
      >>> try:
      ...     cur.execute("SELECT 1/0")
      ...     cur.fetchall()
      ... except:
      ...     transaction.abort()

    We aborted transaction and now we can continue doing stuff

    >>> cur = dm.getCursor()
      >>> cur.execute("SELECT 1")
      >>> cur.fetchall()
      [[1]]

    """


def doctest_PJDataManager_sortKey():
    r"""PJDataManager: sortKey()

    The data manager's sort key is trivial.

      >>> dm.sortKey()
      ('PJDataManager', 0)
    """


def doctest_PJDataManager_sub_objects():
    r"""PJDataManager: Properly handling initialization of sub-objects.

    When `_p_pj_sub_object` objects are loaded from PostGreSQL, their `_p_jar`
    and more importantly their `_p_pj_doc_object` attributes are
    set.

    However, when a sub-object is initially added, those attributes are
    missing.

      >>> foo = Foo('one')
      >>> dm.root['one'] = foo
      >>> dm.tpc_finish(None)

      >>> foo = dm.root['one']
      >>> foo._p_changed

      >>> foo.list = serialize.PersistentList()
      >>> foo.list._p_jar
      >>> getattr(foo.list, '_p_pj_doc_object', 'Missing')
      'Missing'

    Of course, the parent object has changed, since an attribute has been set
    on it.

      >>> foo._p_changed
      True

    Now, since we are dealing with an external database and queries, it
    frequently happens that all changed objects are flushed to the database
    before running a query. In our case, this saves the main object andmarks
    it unchanged again:

      >>> dm.flush()
      >>> foo._p_changed
      False

    However, while flushing, no object is read from the database again.  If
    the jar and document obejct are not set on the sub-object, any changes to
    it would not be seen. Thus, the serialization process *must* assign the
    jar and document object attributes, if not set.

      >>> foo.list._p_jar is dm
      True
      >>> foo.list._p_pj_doc_object is foo
      True

    Let's now ensure that changing the sub-object will have the proper effect:

      >>> foo.list.append(1)
      >>> foo.list._p_changed
      True
      >>> dm.tpc_finish(None)

      >>> foo = dm.root['one']
      >>> foo.list
      [1]

    Note: Most of the implementation of this feature is in the `getState()`
    method of the `ObjectWriter` class.
    """


def doctest_PJDataManager_sub_objects_add_modify():
    """PJDataManager: Make sure that subobject modifications get noticed
    after the first object add

      >>> foo = Foo('one')
      >>> bar = Bar('bar')

      >>> bar._p_pj_sub_object = True
      >>> bar._p_pj_doc_object = foo
      >>> foo.bar = bar

      >>> dm.root['one'] = foo
      >>> dm.tpc_finish(None)

    Now change a subobject property

      >>> bar.name = 'new'
      >>> dm.tpc_finish(None)

    And reload from the DB:

      >>> dm.root['one'].bar.name
      u'new'
"""


def doctest_PJDataManager_complex_sub_objects():
    """PJDataManager: Never store objects marked as _p_pj_sub_object

    Let's construct complex object with several levels of containment.
    _p_pj_doc_object will point to an object, that is subobject itself.

      >>> foo = Foo('one')
      >>> sup = Super('super')
      >>> bar = Bar('bar')

      >>> bar._p_pj_sub_object = True
      >>> bar._p_pj_doc_object = sup
      >>> sup.bar = bar

      >>> sup._p_pj_sub_object = True
      >>> sup._p_pj_doc_object = foo
      >>> foo.sup = sup

      >>> dm.root['one'] = foo
      >>> dm.tpc_finish(None)

      >>> cur = dm._conn.cursor()
      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      [u'persistence_root',
       u'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

    Now, save foo first, and then add subobjects

      >>> foo = Foo('two')
      >>> dm.root['two'] = foo
      >>> dm.tpc_finish(None)

      >>> sup = Super('second super')
      >>> bar = Bar('second bar')

      >>> bar._p_pj_sub_object = True
      >>> bar._p_pj_doc_object = sup
      >>> sup.bar = bar

      >>> sup._p_pj_sub_object = True
      >>> sup._p_pj_doc_object = foo
      >>> foo.sup = sup
      >>> dm.tpc_finish(None)

      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      [u'persistence_root',
       u'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

      >>> dm.root['two'].sup.bar
      <Bar second bar>

      >>> cur = dm.getCursor()
      >>> cur.execute(
      ... '''SELECT * FROM pjpersist_dot_tests_dot_test_datamanager_dot_foo
      ...    WHERE data @> '{"name": "one"}' ''')
      >>> pprint([dict(e) for e in cur.fetchall()])
      [{'data': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Foo',
                 u'name': u'one',
                 u'sup': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Super',
                          u'bar': {u'_py_persistent_type': u'pjpersist.tests.test_datamanager.Bar',
                                   u'name': u'bar'},
                          u'name': u'super'}},
        'id': u'0001020304050607080a0b0c0'}]

    Now, make changes to the subobjects and then commit

      >>> foo = dm.root['one']
      >>> foo.sup.name = 'new super'
      >>> foo.sup.bar.name = 'new bar'
      >>> dm.tpc_finish(None)

      >>> foo = dm.root['one']
      >>> foo.sup
      <Super new super>
      >>> foo.sup._p_pj_sub_object
      True
      >>> foo.sup._p_pj_doc_object
      <Foo one>

      >>> foo.sup.bar
      <Bar new bar>

      >>> foo.sup.bar._p_pj_sub_object
      True
      >>> foo.sup.bar._p_pj_doc_object
      <Foo one>

      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      [u'persistence_root',
       u'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

    Even if _p_pj_doc_object is pointed to subobject, subobject does not get
    saved to its own table:

      >>> foo.sup.bar._p_pj_doc_object = foo.sup
      >>> foo.sup.bar.name = 'newer bar'
      >>> foo.sup.name = 'newer sup'
      >>> dm.tpc_finish(None)

      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      [u'persistence_root',
       u'pjpersist_dot_tests_dot_test_datamanager_dot_foo']
    """


def doctest_PJDataManager_table_sharing():
    r"""PJDataManager: Properly share tables with sub-classes

    When objects do not specify a table, then a table based on the
    class path is created for them. In that case, when a sub-class is created,
    the same table should be used. However, during de-serialization, it
    is important that we select the correct class to use.

      >>> dm.root['app'] = Root()

      >>> dm.root['app'].one = Super('one')
      >>> dm.root['app'].one
      <Super one>

      >>> dm.root['app'].two = Sub('two')
      >>> dm.root['app'].two
      <Sub two>

      >>> dm.root['app'].three = Sub('three')
      >>> dm.root['app'].three
      <Sub three>

      >>> dm.tpc_finish(None)

    Let's now load everything again:

      >>> dm.root['app'].one
      <Super one>
      >>> dm.root['app'].two
      <Sub two>
      >>> dm.root['app'].three
      <Sub three>
      >>> dm.tpc_finish(None)

    Make sure that after a restart, the objects can still be stored.

      >>> serialize.AVAILABLE_NAME_MAPPINGS = set()
      >>> serialize.PATH_RESOLVE_CACHE = {}

      >>> dm2 = datamanager.PJDataManager(conn)

      >>> dm2.root['app'].four = Sub('four')
      >>> dm2.tpc_finish(None)

      >>> serialize.AVAILABLE_NAME_MAPPINGS = set()
      >>> serialize.PATH_RESOLVE_CACHE = {}

      >>> dm2.root['app'].four
      <Sub four>
    """


def doctest_PJDataManager_no_compare():
    r"""PJDataManager: No object methods are called during register/dump.

    Using object comparison within the data manager canhave undesired side
    effects. For example, `__cmp__()` could make use of other model objects
    that cause flushes and queries in the data manager. This can have very
    convoluted side effects, including loss of data.

      >>> import UserDict
      >>> class BadObject(persistent.Persistent):
      ...     def __init__(self, name):
      ...         self.name = name
      ...     def __cmp__(self, other):
      ...         raise ValueError('Compare used in data manager!!!')
      ...     def __repr__(self):
      ...         return '<BadObject %s>' % self.name

      >>> dm.root['bo1'] = BadObject('bo1')
      >>> dm.root['bo2'] = BadObject('bo2')

      >>> dm.tpc_finish(None)

    Since `__cmp__()` was not used, no exception was raised.

      >>> bo1 = dm.root['bo1']
      >>> bo1
      <BadObject bo1>
      >>> bo2 = dm.root['bo2']
      >>> bo2
      <BadObject bo2>

      >>> dm.register(bo1)
      >>> dm.register(bo2)
      >>> sorted(dm._registered_objects.values(), key=lambda ob: ob.name)
      [<BadObject bo1>, <BadObject bo2>]

    """


def doctest_PJDataManager_long():
    r"""PJDataManager: Test behavior of long integers.

      >>> dm.root['app'] = Root()
      >>> dm.root['app'].x = 1L
      >>> dm.tpc_finish(None)

    Let's see how it is deserialzied?

      >>> dm.root['app'].x
      1

    Let's now create a really long integer:

      >>> dm.root['app'].x = 2**62
      >>> dm.tpc_finish(None)

      >>> dm.root['app'].x
      4611686018427387904

    And now an overly long one.

      >>> dm.root['app'].x = 1234567890123456789012345678901234567890
      >>> dm.tpc_finish(None)

      >>> dm.root['app'].x
      1234567890123456789012345678901234567890L
    """


def doctest_PJDataManager_modify_sub_delete_doc():
    """PJDataManager: Deletion is not cancelled if sub-object is modified.

    It must be ensured that the deletion of an object is not cancelled when a
    sub-document object is modified (since it is registered with the data
    manager.

      >>> foo = Foo('foo')
      >>> dm.root['foo'] = foo
      >>> foo.bar = Bar('bar')

      >>> dm.tpc_finish(None)
      >>> cur = dm.getCursor()
      >>> cur.execute(
      ...     '''SELECT count(*)
      ...        FROM pjpersist_dot_tests_dot_test_datamanager_dot_Foo''')
      >>> cur.fetchone()[0]
      1L

    Let's now modify bar and delete foo.

      >>> foo = dm.root['foo']
      >>> foo.bar.name = 'bar-new'
      >>> dm.remove(foo)

      >>> dm.tpc_finish(None)
      >>> cur.execute(
      ...     '''SELECT count(*)
      ...        FROM pjpersist_dot_tests_dot_test_datamanager_dot_Foo''')
      >>> cur.fetchone()[0]
      0L
    """

def doctest_PJDataManager_sub_doc_multi_flush():
    """PJDataManager: Sub-document object multi-flush

    Make sure that multiple changes to the sub-object are registered, even if
    they are flushed inbetween. (Note that flushing happens often due to
    querying.)

      >>> foo = Foo('foo')
      >>> dm.root['foo'] = foo
      >>> foo.bar = Bar('bar')

      >>> dm.tpc_finish(None)

    Let's now modify bar a few times with intermittend flushes.

      >>> foo = dm.root['foo']
      >>> foo.bar.name = 'bar-new'
      >>> dm.flush()
      >>> foo.bar.name = 'bar-newer'

      >>> dm.tpc_finish(None)
      >>> dm.root['foo'].bar.name
      u'bar-newer'
    """


def doctest_get_database_name_from_dsn():
    """Test dsn parsing

      >>> from pjpersist.datamanager import get_database_name_from_dsn

      >>> get_database_name_from_dsn("dbname=test user=postgres password=secret")
      'test'

      >>> get_database_name_from_dsn("dbname = test  user='postgres'")
      'test'

      >>> get_database_name_from_dsn("user='postgres' dbname = test")
      'test'

      >>> get_database_name_from_dsn("user='pg' dbname =test   password=pass")
      'test'
    """


def doctest_conflict_mod_1():
    r"""Check conflict detection. We modify the same object in different
    transactions, simulating separate processes.

      >>> foo = Foo('foo-first')
      >>> dm.root['foo'] = foo

      >>> dm.tpc_finish(None)

      >>> conn1 = testing.getConnection(testing.DBNAME)
      >>> dm1 = datamanager.PJDataManager(conn1)

      >>> dm1.root['foo']
      <Foo foo-first>
      >>> dm1.root['foo'].name = 'foo-second'

      >>> conn2 = testing.getConnection(testing.DBNAME)
      >>> dm2 = datamanager.PJDataManager(conn2)

      >>> dm2.root['foo']
      <Foo foo-first>
      >>> dm2.root['foo'].name = 'foo-third'

    Finish in order 2 - 1

      >>> dm2.tpc_finish(None)
      >>> dm1.tpc_finish(None)
      Traceback (most recent call last):
        ...
      ConflictError: ('could not serialize access due to concurrent update\n', 'UPDATE pjpersist_dot_tests_dot_test_datamanager_dot_Foo SET data=%s WHERE id = %s')

      >>> transaction.abort()

      >>> conn2.close()
      >>> conn1.close()

    """


def doctest_conflict_mod_2():
    r"""Check conflict detection. We modify the same object in different
    transactions, simulating separate processes.

      >>> foo = Foo('foo-first')
      >>> dm.root['foo'] = foo

      >>> dm.tpc_finish(None)

      >>> conn1 = testing.getConnection(testing.DBNAME)
      >>> dm1 = datamanager.PJDataManager(conn1)

      >>> dm1.root['foo']
      <Foo foo-first>
      >>> dm1.root['foo'].name = 'foo-second'

      >>> conn2 = testing.getConnection(testing.DBNAME)
      >>> dm2 = datamanager.PJDataManager(conn2)

      >>> dm2.root['foo']
      <Foo foo-first>
      >>> dm2.root['foo'].name = 'foo-third'

    Finish in order 1 - 2

      >>> dm1.tpc_finish(None)
      >>> dm2.tpc_finish(None)
      Traceback (most recent call last):
      ...
      ConflictError: ('could not serialize access due to concurrent update\n', 'UPDATE pjpersist_dot_tests_dot_test_datamanager_dot_Foo SET data=%s WHERE id = %s')

      >>> transaction.abort()

      >>> conn2.close()
      >>> conn1.close()

    """


class DatamanagerConflictTest(testing.PJTestCase):

    def test_conflict_del_1(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        self.dm.tpc_finish(None)

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(conn1)

        self.assertEqual(dm1.root['foo'].name, 'foo-first')

        dm1.root['foo'].name = 'foo-second'

        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(conn2)

        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        #Finish in order 2 - 1

        dm2.tpc_finish(None)
        with self.assertRaises(interfaces.ConflictError):
            dm1.tpc_finish(None)

        transaction.abort()

        conn2.close()
        conn1.close()

    def test_conflict_del_2(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        self.dm.tpc_finish(None)

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(conn1)

        self.assertEqual(dm1.root['foo'].name, 'foo-first')

        dm1.root['foo'].name = 'foo-second'

        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(conn2)

        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        #Finish in order 1 - 2
        # well, try to... dm1.tpc_finish will block until dm2 is done

        @testing.run_in_thread
        def background_commit():
            with self.assertRaises(interfaces.ConflictError):
                dm1.tpc_finish(None)
        dm2.tpc_finish(None)

        transaction.abort()

        conn2.close()
        conn1.close()

    def test_conflict_del_3(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        self.dm.tpc_finish(None)

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(conn1)
        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(conn2)

        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        self.assertEqual(dm1.root['foo'].name, 'foo-first')
        dm1.root['foo'].name = 'foo-second'

        #Finish in order 2 - 1

        dm2.tpc_finish(None)
        with self.assertRaises(interfaces.ConflictError):
            dm1.tpc_finish(None)

        transaction.abort()

        conn2.close()
        conn1.close()

    def test_conflict_del_4(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        self.dm.tpc_finish(None)

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(conn1)
        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(conn2)

        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        self.assertEqual(dm1.root['foo'].name, 'foo-first')
        dm1.root['foo'].name = 'foo-second'

        #Finish in order 1 - 2
        # well, try to... dm1.tpc_finish will block until dm2 is done

        @testing.run_in_thread
        def background_commit():
            with self.assertRaises(interfaces.ConflictError):
                dm1.tpc_finish(None)
        dm2.tpc_finish(None)

        transaction.abort()

        conn2.close()
        conn1.close()

    def test_conflict_tracebacks(self):
        """Verify conflict tracebacks are captured properly
        and reset on the next transaction."""

        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNone(ctb)

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        self.dm.tpc_finish(None)

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(conn1)
        dm1.root['foo'].name = 'foo-second'

        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(conn2)

        del dm2.root['foo']

        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNone(ctb)

        #Finish in order 2 - 1

        dm2.tpc_finish(None)
        with self.assertRaises(interfaces.ConflictError):
            dm1.tpc_finish(None)

        # verify by length that we have the full traceback
        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNotNone(ctb)
        self.assertEquals(len(ctb), 17)
        transaction.abort()

        # start another transaction and verify the traceback
        # is reset
        datamanager.PJDataManager(conn2)

        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNone(ctb)

        conn2.close()
        conn1.close()


    def test_conflict_commit_1(self):
        """Test conflict on commit

        The typical detail string for such failures is:

        DETAIL:  Reason code: Canceled on identification as a pivot, during commit
        attempt.
        """

        # We will not reproduce the full scenario with pjpersist, however we will
        # pretend the right exception is thrown by commit.
        #
        # First, get the error, that psycopg throws in such case
        # The example is taken from https://wiki.postgresql.org/wiki/SSI
        import psycopg2

        conn1 = self.conn
        conn2 = testing.getConnection(testing.DBNAME)

        with conn1.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mytab")
            cur.execute("CREATE TABLE mytab (class int NOT NULL, value int NOT NULL )")
            cur.execute("INSERT INTO mytab VALUES (1, 10), (1, 20), (2, 100), (2, 200)")
        conn1.commit()

        with conn1.cursor() as cur1, conn2.cursor() as cur2:
            cur1.execute("SELECT SUM(value) FROM mytab WHERE class = 1")
            cur1.execute("INSERT INTO mytab VALUES (2, 30)")

            cur2.execute("SELECT SUM(value) FROM mytab WHERE class = 2")
            cur2.execute("INSERT INTO mytab VALUES (1, 300)")

        conn2.commit()
        conn2.close()

        # Now datamanager, holding conn1 is in doomed state. it is expected to
        # fail on commit attempt.
        txn = transaction.get()
        txn.join(self.dm)

        with self.assertRaises(interfaces.ConflictError):
            transaction.commit()


class QueryLoggingTestCase(testing.PJTestCase):
    def setUp(self):
        super(QueryLoggingTestCase, self).setUp()
        self.log = testing.setUpLogging(datamanager.TABLE_LOG)

        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mytab")
            cur.execute("CREATE TABLE mytab (class int NOT NULL, value varchar NOT NULL )")

        pjal_patch = mock.patch("pjpersist.datamanager.PJ_ACCESS_LOGGING",
                                True)
        self.patches = [pjal_patch]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

        super(QueryLoggingTestCase, self).tearDown()
        testing.tearDownLogging(datamanager.TABLE_LOG)

    def test_logging(self):
        with self.dm.getCursor() as cur:
            cur.execute("INSERT INTO mytab VALUES (1, '10')")

        lines = self.log.getvalue().split('\n')
        self.assertEqual(lines[0], "INSERT INTO mytab VALUES (1, '10'),")
        self.assertEqual(lines[1], " args:None,")

    def test_params(self):
        with self.dm.getCursor() as cur:
            cur.execute("INSERT INTO mytab VALUES (%s, %s)", [1, '10'])

        lines = self.log.getvalue().split('\n')
        self.assertEqual(lines[0], "INSERT INTO mytab VALUES (%s, %s),")
        self.assertEqual(lines[1], " args:[1, '10'],")

    def test_long_params(self):
        hugeparam = "1234567890" * 20000
        with self.dm.getCursor() as cur:
            cur.execute("INSERT INTO mytab VALUES (%s, %s)", [1, hugeparam])

        lines = self.log.getvalue().split('\n')
        self.assertEqual(lines[0], "INSERT INTO mytab VALUES (%s, %s),")
        self.assertLess(len(lines[1]), 1000)


class TransactionOptionsTestCase(testing.PJTestCase):
    def setUp(self):
        super(TransactionOptionsTestCase, self).setUp()

        # Transaction options feature isn't really compatible with table
        # autocreation, because transaction features has to be set before any
        # statement is executed in transaction. So we turn it off in these
        # tests.
        pjact_patch = mock.patch("pjpersist.datamanager.PJ_AUTO_CREATE_TABLES",
                                 False)
        pjacc_patch = mock.patch("pjpersist.datamanager.PJ_AUTO_CREATE_COLUMNS",
                                 False)
        self.patches = [pjact_patch, pjacc_patch]
        for p in self.patches:
            p.start()

        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mytab")
            cur.execute("CREATE TABLE mytab (class int NOT NULL, value varchar NOT NULL )")
        transaction.commit()
        self.dm.reset()

    def tearDown(self):
        for p in self.patches:
            p.stop()

        super(TransactionOptionsTestCase, self).tearDown()

    def test_requestTransactionOptions(self):
        """It is possible to request transaction options before first
        statement is executed
        """

        self.dm.requestTransactionOptions(isolation="READ COMMITTED")

        cur = self.dm.getCursor()
        cur.execute('SHOW transaction_isolation')
        res = cur.fetchone()
        self.assertEqual(res[0], 'read committed')


def test_suite():
    dtsuite = doctest.DocTestSuite(
        setUp=testing.setUp, tearDown=testing.tearDown,
        checker=testing.checker,
        optionflags=testing.OPTIONFLAGS)
    dtsuite.layer = testing.db_layer

    return unittest.TestSuite((
        dtsuite,
        unittest.makeSuite(DatamanagerConflictTest),
        unittest.makeSuite(QueryLoggingTestCase),
        unittest.makeSuite(TransactionOptionsTestCase),
        ))
