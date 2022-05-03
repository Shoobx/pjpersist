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
"""Object Serialization for PostGreSQL's JSONB"""
import base64
import copyreg
import datetime
import warnings

import persistent.interfaces
import persistent.dict
import persistent.list
import zope.interface
from zope.dottedname.resolve import resolve
from decimal import Decimal

from pjpersist import interfaces

ALWAYS_READ_FULL_DOC = True

SERIALIZERS = []
AVAILABLE_NAME_MAPPINGS = set()
PATH_RESOLVE_CACHE = {}
TABLE_KLASS_MAP = {}

FMT_DATE = "%Y-%m-%d"
FMT_TIME = "%H:%M:%S.%f"
FMT_DATETIME = "%Y-%m-%dT%H:%M:%S.%f"

# BBB: Will be removed in 2.0.
FMT_TIME_BBB = "%H:%M:%S"
FMT_DATETIME_BBB = "%Y-%m-%dT%H:%M:%S"

# actually we should extract this somehow from psycopg2
PYTHON_TO_PG_TYPES = {
    str: "text",
    bytes: "text",
    bool: "bool",
    float: "double",
    int: "integer",
    Decimal: "numeric",
    datetime.date: "date",
    datetime.time: "time",
    datetime.datetime: "timestamptz",
    datetime.timedelta: "interval",
    list: "array",
}


KNOWN_FACTORIES = {
    '__builtin__.set': set,
}

# we need to convert dicts and dict-ish values which have non-string keys
# to a structure that can be stored with JSONB (which accepts only strings
# as keys)
# so we do:
# A) happy day
# {'1': 1, '2': '2', '3': Number(3)}
# ->
# {'1': 1, '2': '2', '3': {'_py_type': '__main__.Number', 'num': 3}}
#
# B) if there's a non string key:
# {1: 'one', 2: 'two', 3: 'three'}
# ->
# {DICT_NON_STRING_KEY_MARKER: [(1, 'one'), (2, 'two'), (3, 'three')]}
#
# C) if there's `dict_data` in the input:
# {'1': 1, 'dict_data': 'works?'}
# ->
# {DICT_NON_STRING_KEY_MARKER: [('1', 1), ('dict_data', 'works?')]}
#
# case C is required otherwise when converting back to a dict by
# `ObjectReader.get_object` `get_object` would fail because it expects
# our converted list-in-a-dict structure
# basically we do not allow the DICT_NON_STRING_KEY_MARKER to pass through
DICT_NON_STRING_KEY_MARKER = 'dict_data'


def get_dotted_name(obj, escape=False):
    name = obj.__module__ + '.' + obj.__name__
    if not escape:
        return name
    # Make the name safe.
    name = name.replace('.', '_dot_')
    # XXX: Circumventing a bug in sqlobject.sqlbuilder that prohibits names to
    # start with _.
    name = 'u'+name if name.startswith('_') else name
    return name


def link_to_parent(obj, pobj):
    if obj._p_jar is None:
        if pobj is not None and  getattr(pobj, '_p_jar', None) is not None:
            obj._p_jar = pobj._p_jar
        setattr(obj, interfaces.DOC_OBJECT_ATTR_NAME, pobj)


class PersistentDict(persistent.dict.PersistentDict):
    # SUB_OBJECT_ATTR_NAME:
    _p_pj_sub_object = True

    def __init__(self, data=None, **kwargs):
        # We optimize the case where data is not a dict. The original
        # implementation always created an empty dict, which it then
        # updated. This turned out to be expensive.
        if data is None:
            self.data = {}
        elif isinstance(data, dict):
            self.data = data.copy()
        else:
            self.data = dict(data)
        if len(kwargs):
            self.update(kwargs)

    def __getitem__(self, key):
        # The UserDict supports a __missing__() function, which I have never
        # seen or used before, but it makes the method significantly
        # slower. So let's not do that.
        return self.data[key]

    def __eq__(self, other):
        return self.data == other

    def __ne__(self, other):
        return not self.__eq__(other)


class PersistentList(persistent.list.PersistentList):
    # SUB_OBJECT_ATTR_NAME:
    _p_pj_sub_object = True


class DBRef(object):

    def __init__(self, table, id, database=None):
        self._table = table
        self._id = id
        self._database = database
        self.__calculate_hash()

    def __calculate_hash(self):
        self.hash = hash(str(self.database)+str(self.table)+str(self.id))

    @property
    def database(self):
        return self._database

    @database.setter
    def database(self, value):
        self._database = value
        self.__calculate_hash()

    @property
    def table(self):
        return self._table

    @table.setter
    def table(self, value):
        self._table = value
        self.__calculate_hash()

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value
        self.__calculate_hash()

    def __setstate__(self, state):
        self.__init__(state['table'], state['id'], state['database'])

    def __getstate__(self):
        return {'database': self.database,
                'table': self.table,
                'id': self.id}

    def __hash__(self):
        return self.hash

    def __eq__(self, other):
        try:
            return self.hash == other.hash
        except AttributeError:
            # `other` is not a DBRef or is None
            return False

    def __repr__(self):
        return 'DBRef(%r, %r, %r)' %(self.table, self.id, self.database)

    def as_tuple(self):
        return self.database, self.table, self.id

    def as_json(self):
        return {'_py_type': 'DBREF',
                'database': self.database,
                'table': self.table,
                'id': self.id}


class Binary(str):
    pass

@zope.interface.implementer(interfaces.IObjectSerializer)
class ObjectSerializer(object):

    def can_read(self, state):
        raise NotImplementedError

    def read(self, state):
        raise NotImplementedError

    def can_write(self, obj):
        raise NotImplementedError

    def write(self, obj):
        raise NotImplementedError


@zope.interface.implementer(interfaces.IObjectWriter)
class ObjectWriter(object):

    def __init__(self, jar):
        self._jar = jar

    def get_table_name(self, obj):
        __traceback_info__ = obj
        db_name = getattr(
            obj, interfaces.DATABASE_ATTR_NAME,
            self._jar.database if self._jar else None)
        try:
            table_name = getattr(obj, interfaces.TABLE_ATTR_NAME)
        except AttributeError:
            return db_name, get_dotted_name(obj.__class__, True)
        return db_name, table_name

    def get_non_persistent_state(self, obj):
        objectId = id(obj)
        objectType = type(obj)
        __traceback_info__ = obj, objectType, objectId
        # XXX: Look at the pickle library how to properly handle all types and
        # old-style classes with all of the possible pickle extensions.

        # Get the state of the object. Only pickable objects can be reduced.
        reduce_fn = copyreg.dispatch_table.get(objectType)
        if reduce_fn is not None:
            reduced = reduce_fn(obj)
        else:
            # XXX: __reduce_ex__
            reduced = obj.__reduce__()
        # The full object state (item 3) seems to be optional, so let's make
        # sure we handle that case gracefully.
        if isinstance(reduced, str):
            # When the reduced state is just a string it represents a name in
            # a module. The module will be extracted from __module__.
            return {'_py_constant': obj.__module__+'.'+reduced}
        if len(reduced) == 2:
            factory, args = reduced
            obj_state = {}
        else:
            factory, args, obj_state = reduced
            if obj_state is None:
                obj_state = {}
        # We are trying very hard to create a clean JSONB (sub-)document. But
        # we need a little bit of meta-data to help us out later.
        if factory == copyreg._reconstructor and \
               args == (obj.__class__, object, None):
            # This is the simple case, which means we can produce a nicer
            # JSONB output.
            state = {'_py_type': get_dotted_name(args[0])}
        elif factory == copyreg.__newobj__ and args == (obj.__class__,):
            # Another simple case for persistent objects that do not want
            # their own document.
            state = {interfaces.PY_TYPE_ATTR_NAME: get_dotted_name(args[0])}
        else:
            state = {'_py_factory': get_dotted_name(factory),
                     '_py_factory_args': self.get_state(args, obj)}
        for name, value in obj_state.items():
            state[name] = self.get_state(value, obj)
        return state

    def get_persistent_state(self, obj):
        #seen.add(id(obj))
        __traceback_info__ = obj
        # Persistent sub-objects are stored by reference, the key being
        # (table name, oid).
        # Getting the table name is easy, but if we have an unsaved
        # persistent object, we do not yet have an OID. This must be solved by
        # storing the persistent object.
        if obj._p_oid is None:
            dbref = self.store(obj, ref_only=True)
        else:
            db_name, table_name = self.get_table_name(obj)
            dbref = obj._p_oid
        # Create the reference sub-document. The _p_type value helps with the
        # deserialization later.
        return dbref.as_json()

    def get_state(self, obj, pobj=None):
        objectType = type(obj)
        # in_seen = seen
        # if seen is None:
        #     seen = set()
        __traceback_info__ = obj, objectType, pobj
        if objectType in interfaces.PJ_NATIVE_TYPES:
            # If we have a native type, we'll just use it as the state.
            return obj
        if type(obj) == bytes:
            return {
                '_py_type': 'BINARY',
                'data': base64.b64encode(obj).decode('ascii')
            }
        if type(obj) == str:
            return obj
        # Some objects might not naturally serialize well and create a very
        # ugly JSONB entry. Thus, we allow custom serializers to be
        # registered, which can encode/decode different types of objects.
        for serializer in SERIALIZERS:
            if serializer.can_write(obj):
                return serializer.write(obj)

        if objectType == datetime.date:
            return {'_py_type': 'datetime.date',
                    'value': obj.strftime(FMT_DATE)}
        if objectType == datetime.time:
            return {'_py_type': 'datetime.time',
                    'value': obj.strftime(FMT_TIME)}
        if objectType == datetime.datetime:
            return {'_py_type': 'datetime.datetime',
                    'value': obj.strftime(FMT_DATETIME)}

        if isinstance(obj, type):
            # We frequently store class and function paths as meta-data, so we
            # need to be able to properly encode those.
            return {'_py_type': 'type',
                    'path': get_dotted_name(obj)}

        # We need to make sure that the object's jar and doc-object are
        # set. This is important for the case when a sub-object was just
        # added.
        if getattr(obj, interfaces.SUB_OBJECT_ATTR_NAME, False):
            if obj._p_jar is None:
                if pobj is not None and \
                        getattr(pobj, '_p_jar', None) is not None:
                    obj._p_jar = pobj._p_jar
                setattr(obj, interfaces.DOC_OBJECT_ATTR_NAME, pobj)

        if isinstance(obj, (tuple, list, PersistentList)):
            # Make sure that all values within a list are serialized
            # correctly. Also convert any sequence-type to a simple list.
            return [self.get_state(value, pobj) for value in obj]
        if isinstance(obj, (dict, PersistentDict)):
            # Same as for sequences, make sure that the contained values are
            # properly serialized.
            # Note: see comments at the definition of DICT_NON_STRING_KEY_MARKER
            has_non_compliant_key = False
            data = []
            for key, value in obj.items():
                data.append((key, self.get_state(value, pobj)))
                if (not isinstance(key, str) or  # non-string
                        # a key with our special marker
                        key==DICT_NON_STRING_KEY_MARKER):
                    has_non_compliant_key = True
            if not has_non_compliant_key:
                # The easy case: all keys are compliant:
                return dict(data)
            else:
                # We first need to reduce the keys and then produce a data
                # structure.
                data = [(self.get_state(key, pobj), value)
                        for key, value in data]
                return {DICT_NON_STRING_KEY_MARKER: data}

        if isinstance(obj, persistent.Persistent):
            # Only create a persistent reference, if the object does not want
            # to be a sub-document.
            if not getattr(obj, interfaces.SUB_OBJECT_ATTR_NAME, False):
                return self.get_persistent_state(obj)
            # This persistent object is a sub-document, so it is treated like
            # a non-persistent object.

        try:
            res = self.get_non_persistent_state(obj)
        except RuntimeError as re:
            # let it run into a RuntimeError...
            # it's hard to catch a non-persistent - non-persistent circular
            #    reference while NOT catching a
            #    >>> anobj = object()
            #    >>> alist = [anobj, anobj]

            if re.args[0].startswith('maximum recursion depth exceeded'):
                raise interfaces.CircularReferenceError(obj)
            else:
                raise
        return res

    def get_full_state(self, obj):
        doc = self.get_state(obj.__getstate__(), obj)
        # Always add a persistent type info
        doc[interfaces.PY_TYPE_ATTR_NAME] = get_dotted_name(obj.__class__)
        # Return the full state document
        return doc

    def store(self, obj, ref_only=False, id=None):
        __traceback_info__ = (obj, ref_only)

        # If it is the first time that this type of object is stored, getting
        # the table name has the side affect of telling the class whether it
        # has to store its Python type as well. So, do not remove, even if the
        # data is not used right away,
        db_name, table_name = self.get_table_name(obj)

        if obj._p_oid is None:
            # if not yet added,
            # _p_jar needs to be set early for self.get_state and subobjects
            # for subobjects _p_jar to be set
            obj._p_jar = self._jar

        if ref_only:
            # We only want to get OID quickly. Trying to reduce the full state
            # might cause infinite recursion loop. (Example: 2 new objects
            # reference each other.)
            doc = {}
            # Make sure that the object gets saved fully later.
            self._jar.register(obj)

            #doc_id = self._jar.createId()
            #oid = DBRef(table_name, doc_id, db_name)
            #return oid
        else:
            # XXX: Handle newargs; see ZODB.serialize.ObjectWriter.serialize
            # Go through each attribute and search for persistent references.
            doc = self.get_state(obj.__getstate__(), obj)

        # Always add a persistent type info
        doc[interfaces.PY_TYPE_ATTR_NAME] = get_dotted_name(obj.__class__)

        stored = False
        if interfaces.IColumnSerialization.providedBy(obj):
            self._jar._ensure_sql_columns(obj, table_name)
            column_data = obj._pj_get_column_fields()
        else:
            column_data = None
        if obj._p_oid is None:
            doc_id = self._jar._insert_doc(
                db_name, table_name, doc, id, column_data)
            stored = True
            obj._p_oid = DBRef(table_name, doc_id, db_name)
            # Make sure that any other code accessing this object in this
            # session, gets the same instance.
            self._jar._object_cache[hash(obj._p_oid)] = obj
        else:
            self._jar._update_doc(
                db_name, table_name, doc, obj._p_oid.id, column_data)
            stored = True
        # let's call the hook here, to always have _p_jar and _p_oid set
        if interfaces.IPersistentSerializationHooks.providedBy(obj):
            obj._pj_after_store_hook(self._jar._conn)

        if stored:
            # Make sure that the doc is added to the latest states.
            self._jar._latest_states[obj._p_oid] = doc

        return obj._p_oid


@zope.interface.implementer(interfaces.IObjectReader)
class ObjectReader(object):

    def __init__(self, jar):
        self._jar = jar
        self.preferPersistent = True

    def simple_resolve(self, path):
        path = path.replace('_dot_', '.')
        path = path[1:] if path.startswith('u_') else path
        # We try to look up the klass from a cache. The important part here is
        # that we also cache lookup failures as None, since they actually
        # happen more frequently than a hit due to an optimization in the
        # resolve() function.
        try:
            klass = PATH_RESOLVE_CACHE[path]
        except KeyError:
            if path in KNOWN_FACTORIES:
                return KNOWN_FACTORIES[path]
            try:
                klass = resolve(path)
            except ImportError:
                PATH_RESOLVE_CACHE[path] = klass = None
            else:
                PATH_RESOLVE_CACHE[path] = klass
        if klass is None:
            raise ImportError(path)
        return klass

    def resolve(self, dbref):
        __traceback_info__ = dbref
        # 1. Try to optimize on whether there's just one class stored in one
        #    table, that can save us one DB query
        if dbref.table in TABLE_KLASS_MAP:
            results = TABLE_KLASS_MAP[dbref.table]
            if len(results) == 1:
                # there must be just ONE, otherwise we need to check the JSONB
                klass = list(results)[0]
                return klass
        # from this point on we need the dbref.id
        if dbref.id is None:
            raise ImportError(dbref)
        # 2. Get the class from the object state
        #    Multiple object types are stored in the table. We have to
        #    look at the object (JSONB) to find out the type.
        if dbref in self._jar._latest_states:
            # Optimization: If we have the latest state, then we just get
            # this object document. This is used for fast loading or when
            # resolving the same object path a second time. (The latter
            # should never happen due to the object cache.)
            obj_doc = self._jar._latest_states[dbref]
        elif ALWAYS_READ_FULL_DOC:
            # Optimization: Read the entire doc and stick it in the right
            # place so that unghostifying the object later will not cause
            # another database access.
            obj_doc = self._jar._get_doc_by_dbref(dbref)
            # Do not pollute the latest states because the ref could not be
            # found.
            if obj_doc is not None:
                self._jar._latest_states[dbref] = obj_doc
        else:
            # Just read the type from the database, still requires one query
            pytype = self._jar._get_doc_py_type(
                dbref.database, dbref.table, dbref.id)
            obj_doc = {interfaces.PY_TYPE_ATTR_NAME: pytype}
        if obj_doc is None:
            # There is no document for this reference in the database.
            raise ImportError(dbref)
        if interfaces.PY_TYPE_ATTR_NAME in obj_doc:
            # We have always the path to the class in JSONB
            klass = self.simple_resolve(obj_doc[interfaces.PY_TYPE_ATTR_NAME])
        else:
            raise ImportError(dbref)
        return klass

    def _set_object_state(self, state, sub_obj, obj):
        sub_obj_state = self.get_object(state, obj)
        if hasattr(sub_obj, '__setstate__'):
            sub_obj.__setstate__(sub_obj_state)
        else:
            sub_obj.__dict__.update(sub_obj_state)
        if isinstance(sub_obj, persistent.Persistent):
            # This is a persistent sub-object -- mark it as such. Otherwise
            # we risk to store this object in its own table next time.
            setattr(sub_obj, interfaces.SUB_OBJECT_ATTR_NAME, True)

    def get_non_persistent_object(self, state, obj):
        if '_py_constant' in state:
            return self.simple_resolve(state['_py_constant'])

        # this method must NOT change the passed in state dict
        state = dict(state)
        if '_py_type' in state:
            # Handle the simplified case.
            klass = self.simple_resolve(state.pop('_py_type'))
            sub_obj = copyreg._reconstructor(klass, object, None)
            self._set_object_state(state, sub_obj, obj)
        elif interfaces.PY_TYPE_ATTR_NAME in state:
            # Another simple case for persistent objects that do not want
            # their own document.
            klass = self.simple_resolve(state.pop(interfaces.PY_TYPE_ATTR_NAME))
            sub_obj = copyreg.__newobj__(klass)
            self._set_object_state(state, sub_obj, obj)
        else:
            factory = self.simple_resolve(state.pop('_py_factory'))
            factory_args = self.get_object(state.pop('_py_factory_args'), obj)
            sub_obj = factory(*factory_args)
            # if there is anything left over in `state`, set it below
            # otherwise setting a {} state seems to clean out the object
            # but this is such an edge case of an edge case....
            if state:
                self._set_object_state(state, sub_obj, obj)

        if getattr(sub_obj, interfaces.SUB_OBJECT_ATTR_NAME, False):
            setattr(sub_obj, interfaces.DOC_OBJECT_ATTR_NAME, obj)
            sub_obj._p_jar = self._jar
        return sub_obj

    def get_object(self, state, obj):
        # stateIsDict and state_py_type: optimization to avoid X lookups
        # the code was:
        # if isinstance(state, dict) and state.get('_py_type') == 'DBREF':
        # this methods gets called a gazillion times, so being fast is crucial
        stateIsDict = isinstance(state, dict)
        if stateIsDict:
            state_py_type = state.get('_py_type')
            if state_py_type == 'BINARY':
                # Binary data in Python 2 is presented as a string. We will
                # convert back to binary when serializing again.
                return base64.b64decode(state['data'])
            if state_py_type == 'DBREF':
                # Load a persistent object. Using the _jar.load() method to make
                # sure we're loading from right database and caching is properly
                # applied.
                dbref = DBRef(state['table'], state['id'], state['database'])
                return self._jar.load(dbref)
            if state_py_type == 'type':
                # Convert a simple object reference, mostly classes.
                return self.simple_resolve(state['path'])
            if state_py_type == 'datetime.date':
                return datetime.datetime.strptime(
                    state['value'], FMT_DATE).date()
            if state_py_type == 'datetime.time':
                try:
                    return datetime.datetime.strptime(
                        state['value'], FMT_TIME).time()
                except ValueError:
                    # BBB: We originally did not track sub-seconds.
                    warnings.warn(
                        "Data in old time format found. Support for the "
                        "old format will be removed in pjpersist 2.0.",
                        DeprecationWarning)
                    return datetime.datetime.strptime(
                        state['value'], FMT_TIME_BBB).time()
            if state_py_type == 'datetime.datetime':
                try:
                    return datetime.datetime.strptime(
                        state['value'], FMT_DATETIME)
                except ValueError:
                    # BBB: We originally did not track sub-seconds.
                    warnings.warn(
                        "Data in old date/time format found. Support for the "
                        "old format will be removed in pjpersist 2.0.",
                        DeprecationWarning)
                    return datetime.datetime.strptime(
                        state['value'], FMT_DATETIME_BBB)

        # Give the custom serializers a chance to weigh in.
        for serializer in SERIALIZERS:
            if serializer.can_read(state):
                return serializer.read(state)

        if stateIsDict and (
            '_py_factory' in state
            or '_py_constant' in state
            or '_py_type' in state
            or interfaces.PY_TYPE_ATTR_NAME in state):
            # Load a non-persistent object.
            return self.get_non_persistent_object(state, obj)
        if isinstance(state, (tuple, list)):
            # All lists are converted to persistent lists, so that their state
            # changes are noticed. Also make sure that all value states are
            # converted to objects.
            sub_obj = [self.get_object(value, obj) for value in state]
            if self.preferPersistent:
                sub_obj = PersistentList(sub_obj)
                setattr(sub_obj, interfaces.DOC_OBJECT_ATTR_NAME, obj)
                sub_obj._p_jar = self._jar
            return sub_obj
        if stateIsDict:
            # All dictionaries are converted to persistent dictionaries, so
            # that state changes are detected. Also convert all value states
            # to objects.
            # Handle non-string key dicts.
            # Note: see comments at the definition of DICT_NON_STRING_KEY_MARKER
            if DICT_NON_STRING_KEY_MARKER in state:
                items = state[DICT_NON_STRING_KEY_MARKER]
                # a dict can NOT have an unhashable key,
                # most commonly used is a tuple (which converts to JSON as a
                # list, what then would fail here)
                # so convert a list-ish key to tuple
                keyConverter = lambda key: (
                    tuple(key)
                    if isinstance(key, (list, PersistentList))
                    else key)
                sub_obj = {
                    keyConverter(self.get_object(name, obj)):
                        self.get_object(value, obj)
                    for name, value in items}
            else:
                # for performance reasons we keep a separate implementation
                sub_obj = {
                    self.get_object(name, obj):
                        self.get_object(value, obj)
                    for name, value in state.items()}
            if self.preferPersistent:
                sub_obj = PersistentDict(sub_obj)
                setattr(sub_obj, interfaces.DOC_OBJECT_ATTR_NAME, obj)
                sub_obj._p_jar = self._jar
            return sub_obj
        return state

    def set_ghost_state(self, obj, doc=None):
        __traceback_info__ = (obj, doc)
        # Check whether the object state was stored on the object itself.
        if doc is None:
            doc = getattr(obj, interfaces.STATE_ATTR_NAME, None)
        # Look up the object state by table_name and oid.
        if doc is None:
            doc = self._jar._get_doc_by_dbref(obj._p_oid)
        # Check that we really have a state doc now.
        if doc is None:
            raise ImportError(obj._p_oid)
        # Remove unwanted attributes.
        doc.pop(interfaces.PY_TYPE_ATTR_NAME, None)
        # Now convert the document to a proper Python state dict.
        state = dict(self.get_object(doc, obj))
        if obj._p_oid not in self._jar._latest_states:
            # Sometimes this method is called to update the object state
            # before storage. Only update the latest states when the object is
            # originally loaded.
            self._jar._latest_states[obj._p_oid] = doc
        # Set the state.
        obj.__setstate__(state)
        # Run the custom load functions.
        if interfaces.IPersistentSerializationHooks.providedBy(obj):
            obj._pj_after_load_hook(self._jar._conn)

    def get_ghost(self, dbref, klass=None):
        # If we can, we return the object from cache.
        try:
            return self._jar._object_cache[hash(dbref)]
        except KeyError:
            pass
        if klass is None:
            klass = self.resolve(dbref)
        obj = klass.__new__(klass)
        obj._p_jar = self._jar
        obj._p_oid = dbref
        del obj._p_changed
        # Assign the table after deleting _p_changed, since the attribute
        # is otherwise deleted.
        setattr(obj, interfaces.DATABASE_ATTR_NAME, dbref.database)
        setattr(obj, interfaces.TABLE_ATTR_NAME, dbref.table)
        # Adding the object to the cache is very important, so that we get the
        # same object reference throughout the transaction.
        self._jar._object_cache[hash(dbref)] = obj
        return obj


class table(object):
    """Declare the table used by the class.

    sets also the atrtibute interfaces.TABLE_ATTR_NAME
    but register the fact also in TABLE_KLASS_MAP, this will allow pjpersist
    to optimize class lookup when just one class is stored in one table
    otherwise class lookup always needs the JSONB data from PG
    """

    def __init__(self, table_name):
        self.table_name = table_name

    def __call__(self, ob):
        try:
            setattr(ob, interfaces.TABLE_ATTR_NAME, self.table_name)
            TABLE_KLASS_MAP.setdefault(self.table_name, set()).add(ob)
        except AttributeError:
            raise TypeError(
                "Can't declare %s" % interfaces.TABLE_ATTR_NAME, ob)
        return ob
