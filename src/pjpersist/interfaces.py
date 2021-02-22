##############################################################################
#
# Copyright (c) 2011 Zope Foundation and Contributors.
# Copyright (c) 2014 Shoobx, Inc.
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
"""PG/JSONB Persistence Interfaces"""
import datetime
import decimal
import persistent.interfaces
import transaction.interfaces
import types
import zope.interface
import zope.schema

PJ_NATIVE_TYPES = (int, bool, float, str, type(None))

REFERENCE_SAFE_TYPES = (
    datetime.datetime, datetime.date, datetime.time, decimal.Decimal)

DATABASE_ATTR_NAME = '_p_pj_database'
TABLE_ATTR_NAME = '_p_pj_table'
SUB_OBJECT_ATTR_NAME = '_p_pj_sub_object'
DOC_OBJECT_ATTR_NAME = '_p_pj_doc_object'
STATE_ATTR_NAME = '_p_pj_state'
PY_TYPE_ATTR_NAME = '_py_persistent_type'


class CircularReferenceError(Exception):
    pass


class ConflictError(transaction.interfaces.TransientError):
    pass


class DatabaseDisconnected(transaction.interfaces.TransientError):
    pass


class ReadOnlyDataManagerError(transaction.interfaces.TransactionError):
    """Attempt to modify objects governed by a read-only data manager."""


class IObjectSerializer(zope.interface.Interface):
    """An object serializer allows for custom serialization output for
    objects."""

    def can_read(state):
        """Returns a boolean indicating whether this serializer can deserialize
        this state."""

    def get_object(state):
        """Convert the state to an object."""

    def can_write(obj):
        """Returns a boolean indicating whether this serializer can serialize
        this object."""

    def get_state(obj):
        """Convert the object to a state/document."""


class IObjectWriter(zope.interface.Interface):
    """The object writer stores an object in the database."""

    def get_non_persistent_state(obj, seen):
        """Convert a non-persistent object to a JSONB state/document."""

    def get_persistent_state(obj, seen):
        """Convert a persistent object to a JSONB state/document."""

    def get_state(obj, seen=None):
        """Convert an arbitrary object to a JSONB state/document.

        A ``CircularReferenceError`` is raised, if a non-persistent loop is
        detected.
        """

    def store(obj, id=None):
        """Store an object in the database with given id

        If id is not specified, unique one will be generated
        """


class IObjectReader(zope.interface.Interface):
    """The object reader reads an object from the database."""

    def resolve(path):
        """Resolve a path to a class.

        The path can be any string. It is the responsibility of the resolver
        to maintain the mapping from path to class.
        """

    def get_object(state, obj):
        """Get an object from the given state.

        The ``obj`` is the JSONB document of which the created object is part
        of.
        """

    def set_ghost_state(obj):
        """Convert a ghosted object to an active object by loading its state.
        """

    def get_ghost(coll_name, oid):
        """Get the ghosted version of the object.
        """


class IPJConnectionPool(zope.interface.Interface):
    def getconn():
        """Get connection from the pool"""

    def putconn(conn):
        """Put conncetion back to the pool"""

    def closeall():
        """Close all connection in the pool"""

    def reopen():
        """Reopen the pool after it was closed"""


class IPJDataManager(persistent.interfaces.IPersistentDataManager):
    """A persistent data manager that stores data in PostGreSQL/JSONB."""

    root = zope.interface.Attribute(
        """Get the root object, which is a mapping.""")

    def create_tables(tables):
        """Create passed tables and persistence_name_map, use this instead
        of PJ_AUTO_CREATE_TABLES"""

    def get_table_of_object(obj):
        """Return the table name for an object."""

    def reset():
        """Reset the datamanager for the next transaction."""

    def dump(obj):
        """Store the object to PostGreSQL/JSONB and return its DBRef."""

    def load(dbref):
        """Load the object from PostGreSQL/JSONB by using its DBRef.

        Note: The returned object is in the ghost state.
        """

    def flush():
        """Flush all changes to PostGreSQL."""

    def insert(obj, id=None):
        """Insert an object into PostGreSQL.

        The correct collection is determined by object type.

        If `id` is provided, object will be inserted under that id. Otherwise,
        a new unique id will be generated.
        """

    def remove(obj):
        """Remove an object from PostGreSQL.

        The correct collection is determined by object type.
        """

    def isDirty():
        """Return a bool whether there was any database write since the
        transaction started.

        A SQL write command or any persistent object change will set this flag.

        `transaction.commit` or `transaction.abort` clears this flag.
        """

    def setDirty():
        """Set dirty flag"""

    def setTransactionOptions(
        readonly: bool = None,
        deferrable: bool = None,
        isolation_level: int = None) -> None:
        """Set the options for the future transaction

        Options can only be set before the postgres transaction has started
        """


class IPJDataManagerProvider(zope.interface.Interface):
    """Utility to get a PJ data manager.

    Implementations of this utility usually maintain connection information
    and ensure that there is one consistent datamanager per thread.
    """

    def get(database):
        """Return a PJ data manager for the given database."""


class IPersistentSerializationHooks(zope.interface.Interface):
    """Persistent Serialization Hooks

    Persistent objects implementing this interface will be given the
    opportunity during storage proceedings to consuct some custom
    serialization tasks.
    """

    def _pj_after_store_hook(conn):
        """Custom store hook.

        This method is called after the object has been stored in the
        database. The ``conn`` attribute is a connection to the database.

        You should not manage the connection within this method, ie. abort or
        commit the transaction.
        """

    def _pj_after_load_hook(conn):
        """Custom load hook.

        This method is called after the object has been loaded fully from the
        database. The ``conn`` attribute is a connection to the database.

        You should not manage the connection within this method, ie. abort or
        commit the transaction.
        """


class IColumnSerialization(zope.interface.Interface):
    """Column Serialization Support

    Persistent objects implementing this interfave are able to store some of
    their data into columns of their storage table. This allows developers to
    access those attributes in a more natural way using SQL.
    """

    _pj_column_fields = zope.schema.Tuple(
        title='Column Fields',
        description=(
            'A list of zope.schema fields that represent columns '
            'in the storage table. Fields cannot be named `id` or '
            '`data` as those attributes are reserved.'
            ''
            'The fields are used to '
            '- auto create the SQL table '
            '- populate native SQL column values by `_pj_get_column_fields` '
            'see also pjpersist.zope.container.PJContainer._pj_column_fields'
            'that list of field names should be in sync with this'),
        required=True)

    def _pj_get_column_fields():
        """Get Column Fields values as a mapping from name to value."""
