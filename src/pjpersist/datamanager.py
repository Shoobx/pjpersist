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
"""PostGreSQL/JSONB Persistent Data Manager"""
import binascii
import hashlib
import logging
import os
import random
import re
import socket
import struct
import threading
import time
import traceback
import uuid
from collections.abc import MutableMapping
from typing import Optional

import psycopg2
import psycopg2.errorcodes
import psycopg2.extensions
import psycopg2.extras
import transaction

import pjpersist.sqlbuilder as sb
import zope.interface
from pjpersist import interfaces, serialize
from pjpersist.querystats import QueryReport

# Flag enabling full two-phase-commit support. Note, that this requires
# postgres database to set max_prepared_transactions setting to positive value.
PJ_TWO_PHASE_COMMIT_ENABLED = False

PJ_ACCESS_LOGGING = False
# set to True to automatically create tables if they don't exist
# it is relatively expensive, so create your tables with a schema.sql
# and turn this off for production

# Enable query statistics reporting after transaction ends
PJ_ENABLE_QUERY_STATS = False

# you can register listeners to GLOBAL_QUERY_STATS_LISTENERS with
# `register_query_stats_listener`.
GLOBAL_QUERY_STATS_LISTENERS = set()

# Maximum query length to output with query log
MAX_QUERY_ARGUMENT_LENGTH = 500


PJ_AUTO_CREATE_TABLES = True

# set to True to automatically create IColumnSerialization columns
# will also create tables regardless of the PJ_AUTO_CREATE_TABLES setting
# so this is super expensive
PJ_AUTO_CREATE_COLUMNS = True


TABLE_LOG = logging.getLogger('pjpersist.table')

THREAD_NAMES = []
THREAD_COUNTERS = {}

# When a conflict error is thrown we want to ensure it gets
# handled properly at a higher level (i.e. the transaction is
# retried). In cases where is it not handled correctly we
# will have the traceback of where the conflict occurred
# for debugging later.
# Make sure you set CONFLICT_TRACEBACK_INFO.traceback to None
# after the error is processed.
CONFLICT_TRACEBACK_INFO = threading.local()
CONFLICT_TRACEBACK_INFO.traceback = None

mhash = hashlib.md5()
mhash.update(socket.gethostname().encode('utf-8'))
HOSTNAME_HASH = mhash.digest()[:3]
PID_HASH = struct.pack(">H", os.getpid() % 0xFFFF)

LOG = logging.getLogger(__name__)

psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

PREPARED_TRANSACTION_ID = object()

SERIALIZATION_ERRORS = (
    psycopg2.errorcodes.SERIALIZATION_FAILURE,
    psycopg2.errorcodes.DEADLOCK_DETECTED
)

DISCONNECTED_EXCEPTIONS = (
    psycopg2.OperationalError,
    psycopg2.InterfaceError,
)

# Hints to decide what sort of SQL command we're about to execute
# this is a VERY simple estimation whether the given SQL command
# is a read or write operation
# An exact solution would be to parse the SQL command, but that is
# A) slow,
# B) out of scope,
# C) since our code issues the commands we're in control
SQL_FIRST_WORDS = {
    'alter': 'ddl',
    'create': 'ddl',
    'delete': 'write',
    'drop': 'ddl',
    'insert': 'write',
    'update': 'write',
    'with': 'read',
    'select': 'read',
    'truncate': 'write',
    }

# Flag whether tpc_vote should call tpc_prepare when the transaction
# had no writes. See PJDataManager.tpc_vote
CALL_TPC_PREPARE_ON_NO_WRITE_TRANSACTION = True
# Flag whether PJDataManager should log on commit whether the transaction
# had writes.
LOG_READ_WRITE_TRANSACTION = False


def createId():
    # 4 bytes current time
    id = struct.pack(">i", int(time.time()))
    # 3 bytes machine
    id += HOSTNAME_HASH
    # 2 bytes pid
    id += PID_HASH
    # 1 byte thread id
    tname = threading.currentThread().name
    if tname not in THREAD_NAMES:
        THREAD_NAMES.append(tname)
    tidx = THREAD_NAMES.index(tname)
    id += struct.pack(">B", tidx & 0xFF)
    # 2 bytes counter
    THREAD_COUNTERS.setdefault(tidx, random.randint(0, 0xFFFF))
    THREAD_COUNTERS[tidx] += 1
    id += struct.pack(">H", THREAD_COUNTERS[tidx] & 0xFFFF)
    return binascii.hexlify(id).decode('ascii')


class Json(psycopg2.extras.Json):
    """In logs, we want to have the JSON value not just Json object at <>"""
    def __repr__(self):
        if PJ_ACCESS_LOGGING:
            try:
                s = self.dumps(self.adapted)
            except:
                s = 'exception'
            return '<%s %s>' % (self.__class__.__name__, s)
        else:
            return '<%s>' % (self.__class__.__name__, )


class PJPersistCursor(psycopg2.extras.DictCursor):
    def __init__(self, datamanager, flush, *args, **kwargs):
        super(PJPersistCursor, self).__init__(*args, **kwargs)
        self.datamanager = datamanager
        self.flush = flush

    def log_query(self, sql, args, duration):

        txn = transaction.get()
        txn = '%i - %s' % (id(txn), txn.description)

        TABLE_LOG.debug(
            "%s,\n args:%r,\n TXN:%s,\n time:%sms",
            sql, args, txn, duration*1000)

    def _autoCreateTables(self, sql, args, beacon):
        # XXX: need to set a savepoint, just in case the real execute
        #      fails, it would take down all further commands
        super(PJPersistCursor, self).execute("SAVEPOINT before_execute;")

        try:
            return self._execute_and_log(sql, args)
        except psycopg2.Error as e:
            # XXX: ugly: we're creating here missing tables on the fly
            msg = str(e)
            TABLE_LOG.debug("%s %r failed with %s", sql, args, msg)
            # if the exception message matches
            m = re.search('relation "(.*?)" does not exist', msg)
            if m:
                # need to rollback to the above savepoint, otherwise
                # PG would just ignore any further command
                super(PJPersistCursor, self).execute(
                    "ROLLBACK TO SAVEPOINT before_execute;")

                # we extract the tableName from the exception message
                tableName = m.group(1)

                self.datamanager._create_doc_table(
                    self.datamanager.database, tableName)

                try:
                    return self._execute_and_log(sql, args)
                except psycopg2.Error:
                    # Join the transaction, because failed queries require
                    # aborting the transaction.
                    self.datamanager._join_txn()
            # Join the transaction, because failed queries require
            # aborting the transaction.
            self.datamanager._join_txn()
            self.datamanager._doom_txn()
            check_for_conflict(e, sql, beacon=beacon)
            check_for_disconnect(e, sql, beacon=beacon)
            # otherwise let it fly away
            raise

    def execute(self, sql, args=None, beacon=None, flush_hint=None):
        """execute a SQL statement
        sql - SQL string or SQLBuilder expression
        args - optional list of args for the SQL string
        beacon - optional unique identifier for the statement to help
                 debugging errors. Going to be added to all possible
                 exceptions and log entries
        flush_hint - list of tables to flush before querying database
                     or None to flush all
        """
        # Convert SQLBuilder object to string
        if not isinstance(sql, str):
            sql = sql.__sqlrepr__('postgres')

        # Determine SQL command type (read/write), well sort of
        # See also comments on SQL_FIRST_WORDS
        firstWord = sql.strip().split()[0].lower()
        # By default we opt for 'write' to be on the safe side
        sqlCommandType = SQL_FIRST_WORDS.get(firstWord, 'write')
        if sqlCommandType in ('write', 'ddl'):
            self.datamanager.setDirty()

        if self.flush and sqlCommandType == 'read' and flush_hint != []:
            # Flush the data manager before any select.
            # We do this to have the written data available for queries
            self.datamanager.flush(flush_hint=flush_hint)

        # XXX: Optimization opportunity to store returned JSONB docs in the
        # cache of the data manager. (SR)

        if PJ_AUTO_CREATE_TABLES:
            self._autoCreateTables(sql, args, beacon)
        else:
            try:
                # otherwise just execute the given sql
                return self._execute_and_log(sql, args)
            except psycopg2.Error as e:
                # Join the transaction, because failed queries require
                # aborting the transaction.
                self.datamanager._join_txn()
                self.datamanager._doom_txn()
                check_for_conflict(e, sql, beacon=beacon)
                check_for_disconnect(e, sql, beacon=beacon)
                raise

    def _sanitize_arg(self, arg):
        r = repr(arg)
        if len(r) > MAX_QUERY_ARGUMENT_LENGTH:
            r = r[:MAX_QUERY_ARGUMENT_LENGTH] + "..."
            return r
        return arg

    def _execute_and_log(self, sql, args):
        # Very useful logging of every SQL command with traceback to code.
        __traceback_info__ = (self.datamanager.database, sql, args)
        started = time.time()
        try:
            res = super(PJPersistCursor, self).execute(sql, args)
        finally:
            duration = time.time() - started
            db = self.datamanager.database

            debug = (PJ_ACCESS_LOGGING or PJ_ENABLE_QUERY_STATS)

            if debug:
                saneargs = [self._sanitize_arg(a) for a in args] \
                    if args else args
            else:
                # We don't want to do expensive sanitization in prod mode
                saneargs = args

            if PJ_ACCESS_LOGGING:
                self.log_query(sql, saneargs, duration)

            if PJ_ENABLE_QUERY_STATS:
                self.datamanager._query_report.record(
                    sql, saneargs, duration, db)

            for rep in GLOBAL_QUERY_STATS_LISTENERS:
                rep.record(sql, saneargs, duration, db)
        return res


def check_for_conflict(e, sql, beacon=None):
    """Check whether exception indicates serialization failure and raise
    ConflictError in this case.

    Serialization failures are denoted by postgres codes:
        40001 - serialization_failure
        40P01 - deadlock_detected

    e - exception caught
    sql - SQL string that was executed when the exception occurred
    beacon - optional unique identifier for the statement to help
             debugging errors. Going to be added to all possible
             exceptions and log entries
    """
    if e.pgcode in SERIALIZATION_ERRORS:
        if beacon is None:
            beacon = uuid.uuid4()
        beacon = 'Beacon: %s' % beacon
        CONFLICT_TRACEBACK_INFO.traceback = (
            traceback.format_stack() + [beacon])
        LOG.warning("Conflict detected with code %s sql: %s, %s",
                    e.pgcode, sql, beacon)
        raise interfaces.ConflictError(str(e).strip(), beacon, sql)


def check_for_disconnect(e, sql, beacon=None):
    """Check whether exception indicates a database disconnected error
    and raise DatabaseDisconnected in this case
    Note, DB disconnect detection is NOT easy

    e - exception caught
    sql - SQL string that was executed when the exception occurred
    beacon - optional unique identifier for the statement to help
             debugging errors. Going to be added to all possible
             exceptions and log entries
    """
    if isinstance(e, DISCONNECTED_EXCEPTIONS):
        # XXX: having an exception of the above type might NOT be
        #      an exact sign of a DB disconnect, but as it looks we
        #      don't have a better chance to figure
        if beacon is None:
            beacon = uuid.uuid4()
        beacon = 'Beacon: %s' % beacon
        LOG.warning(
            "Caught exception %r, reraising as DatabaseDisconnected %s",
            e, beacon)
        raise interfaces.DatabaseDisconnected(str(e).strip(), beacon, sql)


class Root(MutableMapping):

    table = 'persistence_root'

    def __init__(self, jar, table=None):
        self._jar = jar
        if table is not None:
            self.table = table
        if PJ_AUTO_CREATE_TABLES:
            self._init_table()

    def _init_table(self):
        with self._jar.getCursor(False) as cur:
            cur.execute(
                "SELECT * FROM information_schema.tables where table_name=%s",
                (self.table,))
            if cur.rowcount:
                return

            LOG.info("Creating table %s" % self.table)
            cur.execute('''
                CREATE TABLE %s (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    dbref TEXT[])
                ''' % self.table)
            self._jar._conn.commit()

    def __getitem__(self, key):
        with self._jar.getCursor(False) as cur:
            tbl = sb.Table(self.table)
            cur.execute(
                sb.Select(sb.Field(self.table, 'dbref'), tbl.name == key))
            if not cur.rowcount:
                raise KeyError(key)
            db, tbl, id = cur.fetchone()['dbref']
            dbref = serialize.DBRef(tbl, id, db)
            return self._jar.load(dbref)

    def __setitem__(self, key, value):
        dbref = self._jar.insert(value)
        if self.get(key) is not None:
            del self[key]
        with self._jar.getCursor(False) as cur:
            cur.execute(
                'INSERT INTO %s (name, dbref) VALUES (%%s, %%s)' % self.table,
                (key, list(dbref.as_tuple()))
                )

    def __delitem__(self, key):
        self._jar.remove(self[key])
        with self._jar.getCursor(False) as cur:
            tbl = sb.Table(self.table)
            cur.execute(sb.Delete(self.table, tbl.name == key))

    def keys(self):
        with self._jar.getCursor(False) as cur:
            cur.execute(sb.Select(sb.Field(self.table, 'name')))
            return [doc['name'] for doc in cur.fetchall()]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.keys())


@zope.interface.implementer(interfaces.IPJDataManager)
class PJDataManager(object):

    root = None

    # Data manager is completely new. NOTE: It is important to leave this
    # property on class level and not add it to constructor, because
    # constructor is called to "reset" the data manager
    _pristine = True

    # Flag showing whether there is any write in the current transaction
    _dirty: bool

    _isolation_level: Optional[str]
    _readonly: Optional[bool]
    _deferrable: Optional[bool]

    def __init__(self, pool, root_table=None):
        self._pool = pool
        self._reader = serialize.ObjectReader(self)
        self._writer = serialize.ObjectWriter(self)
        self.transaction_manager = transaction.manager
        self._query_report = QueryReport()
        self._reset_data_manager()

        if self.root is None:
            # Getting Root can call self._join_txn when the table gets
            # auto-created, that calls self._begin, that might set
            # self._tpc_activated, so do this after setting self._tpc_activated
            self.root = Root(self, root_table)

    def _reset_data_manager(self):
        self._conn = None
        self.database = None
        # All of the following object lists are keys by object id. This is
        # needed when testing containment, since that can utilize `__cmp__()`
        # which can have undesired side effects. `id()` is guaranteed to not
        # use any method or state of the object itself.
        self._registered_objects = {}
        self._loaded_objects = {}
        self._inserted_objects = {}
        self._removed_objects = {}
        self._dirty = False

        self._readonly = None
        self._deferrable = None
        self._isolation_level = None

        # The latest states written to the database.
        self._latest_states = {}
        self._needs_to_join = True
        self._object_cache = {}
        self.annotations = {}

        self._txn_active = False
        self._tpc_activated = False

    def getCursor(self, flush=True):
        self._join_txn()
        def factory(*args, **kwargs):
            return PJPersistCursor(self, flush, *args, **kwargs)
        cur = self._conn.cursor(cursor_factory=factory)

        if not self._txn_active:
            # clear any traceback before starting next txn
            CONFLICT_TRACEBACK_INFO.traceback = None
            self._txn_active = True
        return cur

    def createId(self):
        return createId()

    def create_tables(self, tables):
        if isinstance(tables, str):
            tables = [tables]

        for tbl in tables:
            self._create_doc_table(self.database, tbl)

        with self.getCursor(False) as cur:
            cur.connection.commit()

    def _create_doc_table(self, database, table, extra_columns=''):
        if self.database != database:
            raise NotImplementedError(
                'Cannot store an object of a different database.',
                self.database, database)

        with self.getCursor(False) as cur:
            cur.execute(
                "SELECT * FROM information_schema.tables WHERE table_name=%s",
                (table,))
            if not cur.rowcount:
                LOG.info("Creating data table %s" % table)
                if extra_columns:
                    extra_columns += ', '
                cur.execute('''
                    CREATE TABLE %s (
                        id VARCHAR(24) NOT NULL PRIMARY KEY, %s
                        data JSONB)''' % (table, extra_columns))
                # this index helps a tiny bit with JSONB_CONTAINS queries
                cur.execute('''
                    CREATE INDEX %s_data_gin ON %s USING GIN (data);
                    ''' % (table, table))

    def _ensure_sql_columns(self, obj, table):
        # create the table required for the object, with the necessary
        # _pj_column_fields translated to SQL types
        if PJ_AUTO_CREATE_COLUMNS:
            if interfaces.IColumnSerialization.providedBy(obj):
                # XXX: exercise for later, not just create but check
                #      the columns
                # SELECT column_name
                #  FROM INFORMATION_SCHEMA.COLUMNS
                #  WHERE table_name = '<name of table>';
                columns = []
                for field in obj._pj_column_fields:
                    pgtype = serialize.PYTHON_TO_PG_TYPES[field._type]
                    columns.append("%s %s" % (field.__name__, pgtype))

                columns = ', '.join(columns)

                self._create_doc_table(self.database, table, columns)

    def _insert_doc(self, database, table, doc, id=None, column_data=None):
        # Create id if it is None.
        if id is None:
            id = self.createId()
        # Insert the document into the table.
        with self.getCursor() as cur:
            builtins = dict(id=id, data=Json(doc))
            if column_data is None:
                column_data = builtins
            else:
                column_data.update(builtins)

            columns = []
            values = []
            for colname, value in column_data.items():
                columns.append(colname)
                values.append(value)
            placeholders = ', '.join(['%s'] * len(columns))
            columns = ', '.join(columns)
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (
                table, columns, placeholders)

            cur.execute(sql, tuple(values),
                        beacon="%s:%s:%s" % (database, table, id))
        return id

    def _update_doc(self, database, table, doc, id, column_data=None):
        # Insert the document into the table.
        with self.getCursor() as cur:
            builtins = dict(data=Json(doc))
            if column_data is None:
                column_data = builtins
            else:
                column_data.update(builtins)

            columns = []
            values = []
            for colname, value in column_data.items():
                columns.append(colname+'=%s')
                values.append(value)
            columns = ', '.join(columns)
            sql = "UPDATE %s SET %s WHERE id = %%s" % (table, columns)

            cur.execute(sql, tuple(values) + (id,),
                        beacon="%s:%s:%s" % (database, table, id))
        return id

    def _get_doc(self, database, table, id):
        tbl = sb.Table(table)
        with self.getCursor() as cur:
            cur.execute(sb.Select(sb.Field(table, '*'), tbl.id == id),
                        beacon="%s:%s:%s" % (database, table, id),
                        flush_hint=[table])
            res = cur.fetchone()
            return res['data'] if res is not None else None

    def _get_doc_by_dbref(self, dbref):
        return self._get_doc(dbref.database, dbref.table, dbref.id)

    def _get_doc_py_type(self, database, table, id):
        tbl = sb.Table(table)
        with self.getCursor() as cur:
            datafld = sb.Field(table, 'data')
            cur.execute(
                sb.Select(sb.JGET(datafld, interfaces.PY_TYPE_ATTR_NAME),
                          tbl.id == id),
                beacon="%s:%s:%s" % (database, table, id))
            res = cur.fetchone()
            return res[0] if res is not None else None

    def _get_table_from_object(self, obj):
        return self._writer.get_table_name(obj)

    def flush(self, flush_hint=None):
        # flush_hint contains tables that we want to flush, leaving all other
        # objects registered.
        # Now write every registered object, but make sure we write each
        # object just once.
        processed = set()
        flushed = set()
        docobject_flushed = set()
        # Make sure that we do not compute the list of flushable objects all
        # at once. While writing objects, new sub-objects might be registered
        # that also need saving.
        todo = set(self._registered_objects.keys())
        while todo:
            obj_id = todo.pop()
            obj = self._registered_objects[obj_id]
            __traceback_info__ = obj

            docobj = self._get_doc_object(obj)
            docobj_id = id(docobj)
            processed.add(obj_id)

            dbname, table = self._writer.get_table_name(docobj)
            if flush_hint and table not in flush_hint:
                continue

            flushed.add(obj_id)

            if docobj_id not in docobject_flushed:
                self._writer.store(docobj)
                docobject_flushed.add(docobj_id)

            self.setDirty()
            todo = set(self._registered_objects.keys()) - processed

        # Let's now reset all objects as if they were not modified:
        for obj_id in flushed:
            # Another nested flush already took care of this object.
            if obj_id not in self._registered_objects:
                continue
            obj = self._registered_objects[obj_id]
            obj._p_changed = False

        self._registered_objects = {
            obj_id: obj
            for obj_id, obj in self._registered_objects.items()
            if obj_id not in flushed
        }

    def _get_doc_object(self, obj):
        seen = []
        # Make sure we write the object representing a document in a
        # table and not a sub-object.
        while getattr(obj, '_p_pj_sub_object', False):
            if id(obj) in seen:
                raise interfaces.CircularReferenceError(obj)
            seen.append(id(obj))
            obj = obj._p_pj_doc_object
        return obj

    def _join_txn(self):
        if self._needs_to_join:
            self._acquire_conn()
            # once we have a working connection, we can join the transaction
            transaction = self.transaction_manager.get()
            transaction.join(self)
            self._needs_to_join = False
            self._begin(transaction)

    def _doom_txn(self):
        try:
            transaction = self.transaction_manager.get()
            transaction.doom()
            return True
        except ValueError:
            # We are not in active trasaction phase,
            # so it cannot be doomed.
            return False

    def dump(self, obj):
        res = self._writer.store(obj)
        self.setDirty()
        if id(obj) in self._registered_objects:
            obj._p_changed = False
            del self._registered_objects[id(obj)]
        return res

    def load(self, dbref, klass=None):
        self._join_txn()
        dm = self
        if dbref.database != self.database:
            # This is a reference of object from different database! We need to
            # locate the suitable data manager for this.
            dmp = zope.component.getUtility(interfaces.IPJDataManagerProvider)
            dm = dmp.get(dbref.database)
            dm._join_txn()
            assert dm.database == dbref.database, (dm.database, dbref.database)
            return dm.load(dbref, klass)

        return self._reader.get_ghost(dbref, klass)

    def reset(self):
        # we need to issue rollback on self._conn too, to get the latest
        # DB updates, not just reset PJDataManager state
        self.abort(None)

    def _acquire_conn(self):
        """Get connection from connection pool"""
        self._conn = self._pool.getconn()
        assert self._conn.status == psycopg2.extensions.STATUS_READY
        self.database = get_database_name_from_dsn(self._conn.dsn)

    def _release_conn(self, conn):
        """Release the connection after transaction is complete
        """
        if not conn.closed:
            # Set transaction options back to their default values so that next
            # transaction is not affected
            conn.reset()
        self._pool.putconn(conn)
        self._reset_data_manager()

    def insert(self, obj, oid=None):
        self._join_txn()
        if obj._p_oid is not None:
            raise ValueError('Object._p_oid is already set.', obj)
        res = self._writer.store(obj, id=oid)
        self.setDirty()
        obj._p_changed = False
        self._object_cache[hash(obj._p_oid)] = obj
        self._inserted_objects[id(obj)] = obj
        return res

    def remove(self, obj):
        if obj._p_oid is None:
            raise ValueError('Object._p_oid is None.', obj)
        # If the object is still in the ghost state, let's load it, so that we
        # have the state in case we abort the transaction later.
        if obj._p_changed is None:
            self.setstate(obj)
        # Now we remove the object from PostGreSQL.
        dbname, table = self._get_table_from_object(obj)
        with self.getCursor() as cur:
            cur.execute('DELETE FROM %s WHERE id = %%s' % table,
                        (obj._p_oid.id,),
                        beacon="%s:%s:%s" % (dbname, table, obj._p_oid.id))
            self.setDirty()
        if hash(obj._p_oid) in self._object_cache:
            del self._object_cache[hash(obj._p_oid)]

        # Edge case: The object was just added in this transaction.
        if id(obj) in self._inserted_objects:
            # but it still had to be removed from PostGreSQL, because insert
            # inserted it just before
            del self._inserted_objects[id(obj)]

        self._removed_objects[id(obj)] = obj
        # Just in case the object was modified before removal, let's remove it
        # from the modification list. Note that all sub-objects need to be
        # deleted too!
        for key, reg_obj in list(self._registered_objects.items()):
            if self._get_doc_object(reg_obj) is obj:
                del self._registered_objects[key]
        # We are not doing anything fancy here, since the object might be
        # added again with some different state.

    def setstate(self, obj, doc=None):
        # When reading a state from PostGreSQL, we also need to join the
        # transaction, because we keep an active object cache that gets stale
        # after the transaction is complete and must be cleaned.
        self._join_txn()
        # If the doc is None, but it has been loaded before, we look it
        # up. This acts as a great hook for optimizations that load many
        # documents at once. They can now dump the states into the
        # _latest_states dictionary.
        if doc is None:
            doc = self._latest_states.get(obj._p_oid, None)
        self._reader.set_ghost_state(obj, doc)
        self._loaded_objects[id(obj)] = obj

    def oldstate(self, obj, tid):
        # I cannot find any code using this method. Also, since we do not keep
        # version history, we always raise an error.
        raise KeyError(tid)

    def register(self, obj):
        self._join_txn()

        if self._readonly:
            raise interfaces.ReadOnlyDataManagerError()

        # Do not bring back removed objects. But only main the document
        # objects can be removed, so check for that.
        if id(self._get_doc_object(obj)) in self._removed_objects:
            return

        if obj is not None:
            obj_id = id(obj)
            if obj_id not in self._registered_objects:
                self._registered_objects[obj_id] = obj
                obj_registered = getattr(obj, '_pj_object_registered', None)
                if obj_registered is not None:
                    obj_registered(self)

    def abort(self, transaction):
        if self._conn is None:
            # Connection was never aqcuired - nothing to abort
            return
        self._report_stats()
        try:
            if self._tpc_activated:
                self._conn.tpc_rollback()
            else:
                self._conn.rollback()
        except DISCONNECTED_EXCEPTIONS:
            # this happens usually when PG is restarted and the connection dies
            # our only chance to exit the spiral is to abort the transaction
            pass
        self._release_conn(self._conn)
        self._dirty = False

    def _might_execute_with_error(self, op):
        # run the given method, check for conflicts and DB disconnect
        try:
            op()
        except psycopg2.Error as e:
            check_for_conflict(e, "DataManager.commit")
            check_for_disconnect(e, "DataManager.commit")
            raise

    def setTransactionOptions(
            self,
            readonly: bool = None,
            deferrable: bool = None,
            isolation_level: int = None):
        if isolation_level is not None:
            self._isolation_level = isolation_level
        if readonly is not None:
            self._readonly = readonly
        if deferrable is not None:
            self._deferrable = deferrable

    def _begin(self, transaction):
        self._conn.set_session(isolation_level=self._isolation_level,
                               deferrable=self._deferrable,
                               readonly=self._readonly)

        # This function is called when PJDataManager joins transaction. When
        # two phase commit is requested, we will assign transaction id to
        # underlying connection.
        if not PJ_TWO_PHASE_COMMIT_ENABLED:
            # We don't need to do anything special when two phase commit is
            # disabled. Transaction starts automatically.
            return

        assert self._pristine, ("Error attempting to add data manager "
                                "from old transaction. Create a new "
                                "PJDataManager for new transaction, do not "
                                "modify objects from previously committed "
                                "transactions")
        self._pristine = False

        # Create a global id for the transaction. If it wasn't yet created,
        # create now.
        try:
            txnid = transaction.data(PREPARED_TRANSACTION_ID)
        except KeyError:
            txnid = str(uuid.uuid4())
            transaction.set_data(PREPARED_TRANSACTION_ID, txnid)

        try:
            xid = self._conn.xid(0, txnid, self.database)
            self._conn.tpc_begin(xid)
        except psycopg2.Error as e:
            check_for_disconnect(e, 'PJDataManager._begin')
            raise
        self._tpc_activated = True

    def _log_rw_stats(self):
        if LOG_READ_WRITE_TRANSACTION:
            if self.isDirty():
                LOG.info("PJDataManager transaction had writes")
            else:
                LOG.info("PJDataManager transaction had NO_writes")

    def commit(self, transaction):
        self.flush()
        self._report_stats()
        self._log_rw_stats()

        if not self._tpc_activated:
            try:
                self._might_execute_with_error(self._conn.commit)
                self._dirty = False
            finally:
                self._release_conn(self._conn)

    def tpc_begin(self, transaction):
        pass

    def tpc_vote(self, transaction):
        if self._tpc_activated:
            assert self._conn.status == psycopg2.extensions.STATUS_BEGIN
            if self.isDirty():
                # if the transaction wrote anything we have to call tpc_prepare
                self._might_execute_with_error(self._conn.tpc_prepare)
            else:
                # If the transaction had NO writes

                # We try here hard to avoid calling tpc_prepare when there
                # were NO writes in the current transaction.
                # We found that on AWS Aurora tpc_prepare is SLOW even with no
                # writes.
                if CALL_TPC_PREPARE_ON_NO_WRITE_TRANSACTION:
                    # call tpc_prepare only when the config says so
                    self._might_execute_with_error(self._conn.tpc_prepare)

    def tpc_finish(self, transaction):
        if self._tpc_activated:
            self._report_stats()
            try:
                self._might_execute_with_error(self._conn.tpc_commit)
                self._dirty = False
            finally:
                self._release_conn(self._conn)

    def tpc_abort(self, transaction):
        self.abort(transaction)

    def sortKey(self):
        # `'PJDataManager:%s' % id(self)` would be a better sort key,
        # but this makes our DatamanagerConflictTest lock up.
        return 'PJDataManager:0'

    def _report_stats(self):
        if not PJ_ENABLE_QUERY_STATS:
            return

        stats = self._query_report.calc_and_report()
        TABLE_LOG.info(stats)

    def isDirty(self):
        # this DM is dirty when we had writes or have objects to flush
        # flush on SQL select/with makes this necessary
        #
        # what was written can be checked by looking at TABLE_LOG
        # and self._registered_objects
        return self._dirty or bool(self._registered_objects)

    def setDirty(self):
        if self._readonly:
            raise interfaces.ReadOnlyDataManagerError()
        self._dirty = True

    def __del__(self):
        if self._conn is None:
            return

        LOG.warning("Releasing connection after destroying PJDataManager. "
                    "Active transaction will be aborted.")
        self._release_conn(self._conn)


def get_database_name_from_dsn(dsn):
    import re
    m = re.match(r'.*dbname *= *(.+?)( |$)', dsn)
    if not m:
        LOG.warning("Cannot determine database name from DSN '%s'" % dsn)
        return None

    return m.groups()[0]


def register_query_stats_listener(listener):
    """Register new query stats listener

    All executed sql statements will be reported via the `listner.report()`.
    Note, that queries from all threads will be reported to the same registered
    object.

    `listener` object has to implement `record(sql, args, time, db)` method.
    QueryReport object may be used for this for detailed query analysis.
    """
    GLOBAL_QUERY_STATS_LISTENERS.add(listener)


def unregister_query_stats_listener(listener):
    """Unregister listener, registered by `register_query_stats_listener`
    """
    GLOBAL_QUERY_STATS_LISTENERS.remove(listener)
