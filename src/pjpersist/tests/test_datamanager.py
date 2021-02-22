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
import contextlib
import doctest
import persistent
import unittest
import psycopg2
import psycopg2.errors
from pprint import pprint

import transaction
import mock

from pjpersist import interfaces, serialize, testing, datamanager


class Root(persistent.Persistent):
    pass


class Foo(persistent.Persistent):
    name = None

    def __init__(self, name=None):
        self.name = name

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)


class Super(persistent.Persistent):
    _p_pj_table = 'Super'

    def __init__(self, name=None):
        self.name = name

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)


class Sub(Super):
    pass


class Bar(persistent.Persistent):
    _p_pj_sub_object = True

    def __init__(self, name=None):
        super(Bar, self).__init__()
        self.name = name

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)


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
      ['foo']
      >>> root['foo'] == foo
      True

    Root objects can be overridden:

      >>> foo2 = Foo()
      >>> root['foo'] = foo2
      >>> root.keys()
      ['foo']
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

      >>> dbname, table = dm._get_table_from_object(foo)
      >>> dm.reset()

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
      ...     testing.DummyConnectionPool(conn),
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
      >>> list(dm._registered_objects.values())
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

      >>> list(dm._registered_objects.values())
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

      >>> list(dm._inserted_objects.values())
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

      >>> list(dm._registered_objects.values())
      [<Foo Foo 2>]

    But storing works as expected (flush is implicit before find):

      >>> dm.flush()
      >>> dumpTable(dm._get_table_from_object(foo2)[1])
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'foo'},
        'id': '0001020304050607080a0b0c0'},
       {'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'Foo 2'},
        'id': '0001020304050607080a0b0c0'}]
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

      >>> list(dm._removed_objects.values())
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
      >>> list(dm._removed_objects.values())
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
      >>> list(dm._removed_objects.values())
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
      >>> list(dm._removed_objects.values())
      [<Foo foo>]

      >>> foo.name = 'bar'
      >>> list(dm._removed_objects.values())
      [<Foo bar>]
      >>> list(dm._registered_objects.values())
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
      >>> list(dm._removed_objects.values())
      [<Foo foo>]

    Within the same transaction we modify the object. But the object should
    not appear in the registered objects list.

      >>> foo._p_changed = True
      >>> dm._registered_objects
      {}

    Now, because of other lookups, the changes are flushed, which should not
    restore the object.

      >>> dm.flush()
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
      >>> list(dm._removed_objects.values())
      [<Foo foo>]

    Now, because of other lookups, the changes are flushed, which should not
    restore the object.

      >>> dm.flush()
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

      >>> foo = Foo('foo')
      >>> ref = dm.dump(foo)

      >>> dm.commit(None)
      >>> dm._needs_to_join
      True

      >>> foo2 = Foo()
      >>> foo2._p_oid = ref
      >>> dm.setstate(foo2)
      >>> foo2.name
      'foo'

      >>> dm._needs_to_join
      False
    """


def doctest_PJDataManager_setstate_twice():
    r"""PJDataManager: setstate()

    `setstate` and in turn `set_ghost_state` must not muck with the state
    stored in `_latest_states` otherwise the next setstate will fail badly
    IOW `get_non_persistent_object` must not change it's parameter `state`
    this is a more high level test for the same

      >>> foo = Foo('foo')

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
      'foo'

      >>> zope.interface.Interface.providedBy(foo2)
      True

      >>> foo3 = Foo()
      >>> foo3._p_oid = ref
      >>> dm.setstate(foo3)
      >>> foo3.name
      'foo'

      >>> zope.interface.Interface.providedBy(foo3)
      True
    """


def doctest_PJDataManager_oldstate():
    r"""PJDataManager: oldstate()

    Loads the state of an object for a given transaction. Since we are not
    supporting history, this always raises a key error as documented.

      >>> foo = Foo('foo')
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

      >>> foo = Foo('foo')
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
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'one'},
        'id': '0001020304050607080a0b0c0'},
       {'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'two'},
        'id': '0001020304050607080a0b0c0'}]

    Now, in a second transaction we modify the state of objects in all three
    ways:

      >>> foo = dm.load(foo_ref)
      >>> foo.name = '1'
      >>> list(dm._registered_objects.values())
      [<Foo 1>]

      >>> foo2 = dm.load(foo2_ref)
      >>> dm.remove(foo2)
      >>> list(dm._removed_objects.values())
      [<Foo two>]

      >>> foo3_ref = dm.insert(Foo('three'))

      >>> dm.flush()
      >>> dumpTable(table)
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': '1'},
        'id': '0001020304050607080a0b0c0'},
       {'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'three'},
        'id': '0001020304050607080a0b0c0'}]

    Let's now abort the transaction and everything should be back to what it
    was before:

      >>> dm.abort(transaction.get())
      >>> dumpTable(table)
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'one'},
        'id': '0001020304050607080a0b0c0'},
       {'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'two'},
        'id': '0001020304050607080a0b0c0'}]
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
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.ComplexFoo',
                 'item': {'_py_type': 'pjpersist.tests.test_datamanager.FooItem',
                           'bar': 6},
                 'name': 'complex'},
        'id': '0001020304050607080a0b0c0'}]

    2. Modify the item and flush it to database

      >>> foo1 = dm.load(foo1_ref)
      >>> foo1.name = 'modified'
      >>> dm.flush()

      >>> dumpTable(table)
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.ComplexFoo',
                 'item': {'_py_type': 'pjpersist.tests.test_datamanager.FooItem',
                           'bar': 6},
                 'name': 'modified'},
        'id': '0001020304050607080a0b0c0'}]

    3. Abort the current transaction and expect original state is restored

      >>> dm.abort(transaction.get())
      >>> dumpTable(table)
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.ComplexFoo',
                 'item': {'_py_type': 'pjpersist.tests.test_datamanager.FooItem',
                           'bar': 6},
                 'name': 'complex'},
        'id': '0001020304050607080a0b0c0'}]
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

    This method finishes the two-phase commit. Let's store a simple object:

      >>> foo = Foo()
      >>> dm.register(foo)
      >>> transaction.commit()

    Note that objects cannot be stored twice in the same transaction:

      >>> dm.reset()
      >>> dm.register(foo)
      >>> dm.register(foo)
      >>> transaction.commit()

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
      'PJDataManager:...'
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
      >>> commit()

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
      >>> commit()

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
      >>> commit()

    Now change a subobject property

      >>> bar.name = 'new'
      >>> commit()

    And reload from the DB:

      >>> dm.root['one'].bar.name
      'new'
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
      >>> commit()

      >>> cur = conn.cursor()
      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      ['persistence_root',
       'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

    Now, save foo first, and then add subobjects

      >>> foo = Foo('two')
      >>> dm.root['two'] = foo
      >>> commit()

      >>> sup = Super('second super')
      >>> bar = Bar('second bar')

      >>> bar._p_pj_sub_object = True
      >>> bar._p_pj_doc_object = sup
      >>> sup.bar = bar

      >>> sup._p_pj_sub_object = True
      >>> sup._p_pj_doc_object = foo
      >>> foo.sup = sup
      >>> commit()

      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      ['persistence_root',
       'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

      >>> dm.root['two'].sup.bar
      <Bar second bar>

      >>> cur = dm.getCursor()
      >>> cur.execute(
      ... '''SELECT * FROM pjpersist_dot_tests_dot_test_datamanager_dot_foo
      ...    WHERE data @> '{"name": "one"}' ''')
      >>> pprint([dict(e) for e in cur.fetchall()])
      [{'data': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Foo',
                 'name': 'one',
                 'sup': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Super',
                          'bar': {'_py_persistent_type': 'pjpersist.tests.test_datamanager.Bar',
                                   'name': 'bar'},
                          'name': 'super'}},
        'id': '0001020304050607080a0b0c0'}]

    Now, make changes to the subobjects and then commit

      >>> foo = dm.root['one']
      >>> foo.sup.name = 'new super'
      >>> foo.sup.bar.name = 'new bar'
      >>> commit()

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
      ['persistence_root',
       'pjpersist_dot_tests_dot_test_datamanager_dot_foo']

    Even if _p_pj_doc_object is pointed to subobject, subobject does not get
    saved to its own table:

      >>> foo.sup.bar._p_pj_doc_object = foo.sup
      >>> foo.sup.bar.name = 'newer bar'
      >>> foo.sup.name = 'newer sup'
      >>> commit()

      >>> cur.execute('SELECT tablename from pg_tables;')
      >>> sorted(e[0] for e in cur.fetchall()
      ...        if not e[0].startswith('pg_') and not e[0].startswith('sql_'))
      ['persistence_root',
       'pjpersist_dot_tests_dot_test_datamanager_dot_foo']
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

      >>> transaction.commit()

    Let's now load everything again:

      >>> dm.root['app'].one
      <Super one>
      >>> dm.root['app'].two
      <Sub two>
      >>> dm.root['app'].three
      <Sub three>
      >>> transaction.commit()

    Make sure that after a restart, the objects can still be stored.

      >>> serialize.AVAILABLE_NAME_MAPPINGS = set()
      >>> serialize.PATH_RESOLVE_CACHE = {}
      >>> dm2 = datamanager.PJDataManager(testing.DummyConnectionPool(conn))

      >>> dm2.root['app'].four = Sub('four')
      >>> transaction.commit()

      >>> serialize.AVAILABLE_NAME_MAPPINGS = set()
      >>> serialize.PATH_RESOLVE_CACHE = {}

      >>> dm2.root['app'].four
      <Sub four>
    """


def doctest_PJDataManager_no_compare():
    r"""PJDataManager: No object methods are called during register/dump.

    Using object comparison within the data manager can have undesired side
    effects. For example, `__cmp__()` could make use of other model objects
    that cause flushes and queries in the data manager. This can have very
    convoluted side effects, including loss of data.

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

      >>> commit()

    Let's now modify bar a few times with intermittend flushes.

      >>> foo = dm.root['foo']
      >>> foo.bar.name = 'bar-new'
      >>> dm.flush()
      >>> foo.bar.name = 'bar-newer'

      >>> commit()
      >>> dm.root['foo'].bar.name
      'bar-newer'
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


class DatamanagerConflictTest(testing.PJTestCase):

    def test_conflict_del_1(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        txn = transaction.manager.get()
        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        transaction.commit()

        conn1 = testing.getConnection(testing.DBNAME)
        conn2 = testing.getConnection(testing.DBNAME)

        dm2 = datamanager.PJDataManager(testing.DummyConnectionPool(conn2))
        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        dm1 = datamanager.PJDataManager(testing.DummyConnectionPool(conn1))
        self.assertEqual(dm1.root['foo'].name, 'foo-first')
        dm1.root['foo'].name = 'foo-second'

        #Finish in order 2 - 1

        with self.assertRaises(interfaces.ConflictError):
            transaction.commit()

        transaction.abort()

        conn2.close()
        conn1.close()

    def test_conflict_del_2(self):
        """Check conflict detection. We modify and delete the same object in
        different transactions, simulating separate processes."""

        foo = Foo('foo-first')
        self.dm.root['foo'] = foo

        transaction.commit()

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(testing.DummyConnectionPool(conn1))

        self.assertEqual(dm1.root['foo'].name, 'foo-first')

        dm1.root['foo'].name = 'foo-second'

        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(testing.DummyConnectionPool(conn2))

        self.assertEqual(dm2.root['foo'].name, 'foo-first')
        del dm2.root['foo']

        #Finish in order 1 - 2
        # well, try to... dm1.tpc_finish will block until dm2 is done

        @testing.run_in_thread
        def background_commit():
            with self.assertRaises(interfaces.ConflictError):
                dm1.commit(None)
        dm2.commit(None)

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

        transaction.commit()

        conn2 = testing.getConnection(testing.DBNAME)
        dm2 = datamanager.PJDataManager(testing.DummyConnectionPool(conn2))
        del dm2.root['foo']

        conn1 = testing.getConnection(testing.DBNAME)
        dm1 = datamanager.PJDataManager(testing.DummyConnectionPool(conn1))
        dm1.root['foo'].name = 'foo-second'

        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNone(ctb)

        # Finish in order 2 - 1
        with self.assertRaises(interfaces.ConflictError):
            transaction.commit()

        # verify by length that we have the full traceback
        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNotNone(ctb)
        # Make all work
        self.assertTrue(len(ctb) > 20)
        self.assertIn('Beacon:', ctb[-1])
        transaction.abort()

        # start another transaction and verify the traceback
        # is reset
        datamanager.PJDataManager(testing.DummyConnectionPool(conn2))

        ctb = datamanager.CONFLICT_TRACEBACK_INFO.traceback
        self.assertIsNone(ctb)

        conn2.close()
        conn1.close()

    def test_conflict_commit_1(self):
        """Test conflict on commit

        The typical detail string for such failures is:

        DETAIL:  Reason code: Canceled on identification as a pivot, during
        commit attempt.
        """

        # We will not reproduce the full scenario with pjpersist, however we
        # will pretend the right exception is thrown by commit.
        #
        # First, get the error, that psycopg throws in such case
        # The example is taken from https://wiki.postgresql.org/wiki/SSI
        conn1 = self.conn

        conn2 = testing.getConnection(testing.DBNAME)

        with conn1.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mytab")
            cur.execute(
                "CREATE TABLE mytab (class int NOT NULL, value int NOT NULL )")
            cur.execute(
                "INSERT INTO mytab VALUES (1, 10), (1, 20), (2, 100), (2, 200)")
        conn1.commit()

        with self.dm.getCursor() as cur1, conn2.cursor() as cur2:
            cur1.execute("SELECT SUM(value) FROM mytab WHERE class = 1")
            cur1.execute("INSERT INTO mytab VALUES (2, 30)")

            cur2.execute("SELECT SUM(value) FROM mytab WHERE class = 2")
            cur2.execute("INSERT INTO mytab VALUES (1, 300)")

        conn2.commit()
        conn2.close()

        # Now datamanager, holding conn1 is in doomed state. it is expected to
        # fail on commit attempt.
        with self.assertRaises(interfaces.ConflictError):
            transaction.commit()

    def test_catch_bad_sql(self):
        """Test breaks psycopg2 transaction but tries to commit anyway."""

        # An offending piece of code swallows psycopg2 exception,
        # leaving psycopg2 transaction in a failed state
        with self.dm.getCursor() as cursor:
            with self.assertRaises(psycopg2.errors.SyntaxError):
                cursor.execute("BAD SQL")

        # The transaction is now marked as doomed, so we cannot commit it
        with self.assertRaises(transaction.interfaces.DoomedTransaction):
            transaction.commit()
        transaction.abort()

    def test_db_disconnect(self):
        """check_for_disconnect converts some psycopg2 exceptions to
        DatabaseDisconnected exceptions, check that
        """
        def fail(*args, **kw):
            raise psycopg2.OperationalError('boom')

        with mock.patch(
                'pjpersist.datamanager.PJPersistCursor._execute_and_log',
                side_effect=fail):
            with self.dm.getCursor() as cur:
                with self.assertRaises(interfaces.DatabaseDisconnected):
                    cur.execute("DROP TABLE IF EXISTS mytab")

        def fail(*args, **kw):
            raise psycopg2.InterfaceError('boom')

        with mock.patch(
                'pjpersist.datamanager.PJPersistCursor._execute_and_log',
                side_effect=fail):
            with self.dm.getCursor() as cur:
                with self.assertRaises(interfaces.DatabaseDisconnected):
                    cur.execute("DROP TABLE IF EXISTS mytab")


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

    def test_setTransactionOptions_setIsolation(self):
        """It is possible to request transaction options before first
        statement is executed
        """

        self.dm.setTransactionOptions(isolation_level="READ COMMITTED")

        cur = self.dm.getCursor()
        cur.execute('SHOW transaction_isolation')
        res = cur.fetchone()
        self.assertEqual(res[0], 'read committed')

    def test_option_reset_after_commit(self):
        # First, check the default isolation level
        cur = self.dm.getCursor()
        cur.execute('SHOW transaction_isolation')
        res = cur.fetchone()
        default_level = res[0]
        self.assertNotEqual(default_level, 'repeatable read')
        transaction.commit()

        # Now change it
        self.dm.setTransactionOptions(isolation_level="REPEATABLE READ")
        cur = self.dm.getCursor()
        cur.execute('SHOW transaction_isolation')
        res = cur.fetchone()
        self.assertEqual(res[0], 'repeatable read')
        transaction.commit()

        # On the subsequent transaction, we should go back to default level
        cur = self.dm.getCursor()
        cur.execute('SHOW transaction_isolation')
        res = cur.fetchone()
        self.assertEqual(res[0], default_level)


class DirtyTestCase(testing.PJTestCase):

    def setUp(self):
        super(DirtyTestCase, self).setUp()

        # get rid of the previous transaction
        transaction.abort()

        tpc_patch = mock.patch(
            "pjpersist.datamanager.PJ_TWO_PHASE_COMMIT_ENABLED", True)
        no_prep_patch = mock.patch(
            "pjpersist.datamanager."
            "CALL_TPC_PREPARE_ON_NO_WRITE_TRANSACTION", False)
        log_patch = mock.patch(
            "pjpersist.datamanager.LOG_READ_WRITE_TRANSACTION", True)
        self.patches = [tpc_patch, no_prep_patch, log_patch]
        for p in self.patches:
            p.start()

        # First PJDataManager instantiation creates tables, what makes the dm
        # dirty, which we want to avoid here.
        self.conn = testing.getConnection(testing.DBNAME)
        self.dm = datamanager.PJDataManager(testing.DummyConnectionPool(self.conn))

    def tearDown(self):
        for p in self.patches:
            p.stop()

        super(DirtyTestCase, self).tearDown()

    def test_isDirty(self):
        """Test PJDataManager.isDirty setting
        """
        # by default a pristine DM is not dirty
        self.assertEqual(self.dm.isDirty(), False)

        with self.cursor():
            # add an object
            self.dm.root['foo'] = Foo('foo-first')
            self.assertEqual(self.dm.isDirty(), True)

        # a commit/abort clears the dirty flag
        self.assertEqual(self.dm.isDirty(), False)

        with self.cursor(abort=True):
            # modify an object property
            self.dm.root['foo'].name = 'blabla'
            self.assertEqual(self.dm.isDirty(), True)

        # a commit/abort clears the dirty flag
        self.assertEqual(self.dm.isDirty(), False)

        # delete an object in a separate transaction
        with self.cursor():
            self.dm.root['foo2'] = Foo('foo-second')

        with self.cursor():
            del self.dm.root['foo2']
            self.assertEqual(self.dm.isDirty(), True)

        # add and remove an object in the same transaction
        with self.cursor():
            self.dm.root['foo3'] = Foo('foo-third')
            del self.dm.root['foo3']
            self.assertEqual(self.dm.isDirty(), True)

        # check the special dump method
        with self.cursor():
            self.dm.dump(self.dm.root['foo'])
            self.assertEqual(self.dm.isDirty(), True)

    def test_isDirty_sql(self):
        """Test PJDataManager.isDirty setting, SQL commands need to set it too
        """
        with self.cursor() as cur:
            cur.execute("SELECT 1")
            self.assertFalse(self.dm.isDirty())

        with self.cursor() as cur:
            cur.execute("INSERT INTO mytab VALUES (%s, %s)", [1, '10'])
            self.assertTrue(self.dm.isDirty())

        # commit clears dirty
        self.assertFalse(self.dm.isDirty())

        with self.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mytab")
            cur.execute("CREATE TABLE mytab "
                        "(class int NOT NULL, value varchar NOT NULL )")
            self.assertTrue(self.dm.isDirty())

        with self.cursor() as cur:
            cur.execute("INSERT INTO mytab VALUES (%s, %s)", [1, '10'])

        with self.cursor(abort=True) as cur:
            cur.execute("UPDATE mytab SET value='42' WHERE class=1")
            self.assertTrue(self.dm.isDirty())

        self.assertFalse(self.dm.isDirty())

    def test_clean_dm_tpc_no_prepare(self):
        # check that a DM that has NO writes does NOT call tpc_prepare
        self.assertFalse(self.dm.isDirty())

        # load somehing from the DB to get going with PJDataManager
        self.assertEqual(len(self.dm.root), 0)

        # cannot mock patch a C method (tpc_prepare)
        # next best is _might_execute_with_error
        orig = self.dm._might_execute_with_error
        prep_mock = mock.patch.object(
            self.dm, '_might_execute_with_error', side_effect=orig)
        with prep_mock as prep_mock_p:
            transaction.commit()

        self.assertEqual(prep_mock_p.call_count, 1)  # tpc_commit in tpc_finish
        self.assertFalse('tpc_prepare' in str(prep_mock_p.call_args_list))
        self.assertTrue('tpc_commit' in str(prep_mock_p.call_args_list))

    def test_dirty_dm_tpc_prepare(self):
        # check that a DM that HAS writes DOES call tpc_prepare

        # add an object, do some changes to make the DM dirty
        self.dm.root['foo'] = Foo('foo-first')
        self.assertTrue(self.dm.isDirty())

        # cannot mock patch a C method (tpc_prepare)
        orig = self.dm._might_execute_with_error
        prep_mock = mock.patch.object(
            self.dm, '_might_execute_with_error', side_effect=orig)
        with prep_mock as prep_mock_p:
            transaction.commit()

        self.assertEqual(prep_mock_p.call_count, 2)  # tpc_commit in tpc_finish
        self.assertTrue('tpc_prepare' in str(prep_mock_p.call_args_list))
        self.assertTrue('tpc_commit' in str(prep_mock_p.call_args_list))

    def test_release_on_destroy(self):
        # When DM is destroyed without committing or aborting the transaction
        # (for whatever awkward reason), connection should be released.
        conn = testing.getConnection(testing.DBNAME)
        pool = testing.DummyConnectionPool(conn)
        dm = datamanager.PJDataManager(pool)
        dm.getCursor()  # join the transaction
        self.assertTrue(pool.isTaken())

        # WHEN
        # simulate the garbage collection
        dm.__del__()

        # THEN
        self.assertFalse(pool.isTaken())

    def test_release_on_new_transaction(self):
        # When new transaction is started, connection is released because
        # the previous one is aborted.
        # GIVEN
        conn = testing.getConnection(testing.DBNAME)
        pool = testing.DummyConnectionPool(conn)
        dm = datamanager.PJDataManager(pool)
        dm.getCursor()  # join the transaction
        self.assertTrue(pool.isTaken())

        # WHEN

        # Create new transaction to release the reference to our data manager
        # and allow it to be destroyed
        transaction.begin()

        # THEN
        self.assertFalse(pool.isTaken())

    def test_release_on_commit(self):
        # GIVEN
        transaction.abort()
        pool = testing.DummyConnectionPool(self.conn)
        dm = datamanager.PJDataManager(pool)
        dm.getCursor()  # join the transaction
        self.assertTrue(pool.isTaken())

        # WHEN

        # Create new transaction to release the reference to our data manager
        # and allow it to be destroyed
        transaction.commit()

        # THEN
        self.assertFalse(pool.isTaken())

    def test_release_on_abort(self):
        # GIVEN
        transaction.abort()
        pool = testing.DummyConnectionPool(self.conn)
        dm = datamanager.PJDataManager(pool)
        dm.getCursor()  # join the transaction
        self.assertTrue(pool.isTaken())

        # WHEN

        # Create new transaction to release the reference to our data manager
        # and allow it to be destroyed
        transaction.abort()

        # THEN
        self.assertFalse(pool.isTaken())

    def test_readonly_fail_on_write(self):
        transaction.abort()
        pool = testing.DummyConnectionPool(self.conn)
        dm = datamanager.PJDataManager(pool)
        dm.setTransactionOptions(readonly=True)

        # WHEN, THEN
        with self.assertRaises(interfaces.ReadOnlyDataManagerError):
            with dm.getCursor() as cur:
                cur.execute("INSERT INTO mytab VALUES (1, '10')")

    @contextlib.contextmanager
    def cursor(self, abort=False):
        transaction.abort()
        self.dm = datamanager.PJDataManager(testing.DummyConnectionPool(self.conn))
        cur = self.dm.getCursor()
        yield cur
        if abort:
            transaction.abort()
        else:
            transaction.commit()


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
        unittest.makeSuite(DirtyTestCase),
        ))
