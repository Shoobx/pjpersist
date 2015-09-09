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
"""PostGreSQL/JSONB Persistence Zope Containers"""
import UserDict
import json
import persistent
import transaction
import zope.component
import warnings

from rwproperty import getproperty, setproperty
from zope.container import contained, sample
from zope.container.interfaces import IContainer

import pjpersist.sqlbuilder as sb
from pjpersist import interfaces, serialize
from pjpersist.zope import interfaces as zinterfaces
from pjpersist.mquery import Converter

USE_CONTAINER_CACHE = True


class PJContained(contained.Contained):

    _v_name = None
    _pj_name_attr = None
    _pj_name_getter = None
    _pj_name_setter = None

    _pj_parent_attr = None
    _pj_parent_getter = None
    _pj_parent_setter = None
    _v_parent = None

    @getproperty
    def __name__(self):
        if self._v_name is None:
            if self._pj_name_attr is not None:
                self._v_name = getattr(self, self._pj_name_attr, None)
            elif self._pj_name_getter is not None:
                self._v_name = self._pj_name_getter()
        return self._v_name
    @setproperty
    def __name__(self, value):
        if self._pj_name_setter is not None:
            self._pj_name_setter(value)
        self._v_name = value

    @getproperty
    def __parent__(self):
        if self._v_parent is None:
            if self._pj_parent_attr is not None:
                self._v_parent = getattr(self, self._pj_parent_attr, None)
            elif self._pj_parent_getter is not None:
                self._v_parent = self._pj_parent_getter()
        return self._v_parent
    @setproperty
    def __parent__(self, value):
        if self._pj_parent_setter is not None:
            self._pj_parent_setter(value)
        self._v_parent = value


class SimplePJContainer(sample.SampleContainer, persistent.Persistent):
    _pj_remove_documents = True

    def __getstate__(self):
        state = super(SimplePJContainer, self).__getstate__()
        state['data'] = state.pop('_SampleContainer__data')
        return state

    def __setstate__(self, state):
        # pjpersist always reads a dictionary as persistent dictionary. And
        # modifying this dictionary will cause the persistence mechanism to
        # kick in. So we create a new object that we can easily modify without
        # harm.
        state = dict(state)
        state['_SampleContainer__data'] = state.pop('data', {})
        super(SimplePJContainer, self).__setstate__(state)

    def __getitem__(self, key):
        obj = super(SimplePJContainer, self).__getitem__(key)
        obj._v_name = key
        obj._v_parent = self
        return obj

    def get(self, key, default=None):
        '''See interface `IReadContainer`'''
        obj = super(SimplePJContainer, self).get(key, default)
        if obj is not default:
            obj._v_name = key
            obj._v_parent = self
        return obj

    def items(self):
        items = super(SimplePJContainer, self).items()
        for key, obj in items:
            obj._v_name = key
            obj._v_parent = self
        return items

    def values(self):
        return [v for k, v in self.items()]

    def __setitem__(self, key, obj):
        super(SimplePJContainer, self).__setitem__(key, obj)
        self._p_changed = True

    def __delitem__(self, key):
        obj = self[key]
        super(SimplePJContainer, self).__delitem__(key)
        if self._pj_remove_documents:
            self._p_jar.remove(obj)
        self._p_changed = True


class PJContainer(contained.Contained,
                  persistent.Persistent,
                  UserDict.DictMixin):
    zope.interface.implements(IContainer, zinterfaces.IPJContainer)
    _pj_table = None
    _pj_mapping_key = 'key'
    _pj_parent_key = 'parent'
    _pj_remove_documents = True

    def __init__(self, table=None,
                 mapping_key=None, parent_key=None):
        if table:
            self._pj_table = table
        if mapping_key is not None:
            self._pj_mapping_key = mapping_key
        if parent_key is not None:
            self._pj_parent_key = parent_key

    @property
    def _pj_jar(self):
        if not hasattr(self, '_v_mdmp'):
            # If the container is in a PJ storage hierarchy, then getting
            # the datamanager is easy, otherwise we do an adapter lookup.
            if interfaces.IPJDataManager.providedBy(self._p_jar):
                return self._p_jar

            # cache result of expensive component lookup
            self._v_mdmp = zope.component.getUtility(
                    interfaces.IPJDataManagerProvider)

        return self._v_mdmp.get(None)

    def _pj_get_parent_key_value(self):
        if getattr(self, '_p_jar', None) is None:
            raise ValueError('_p_jar not found.')
        if interfaces.IPJDataManager.providedBy(self._p_jar):
            return self
        else:
            return 'zodb-'+''.join("%02x" % ord(x) for x in self._p_oid).strip()

    def _pj_get_items_filter(self):
        """return a filter that selects the rows of the current container"""
        queries = []
        # Make sure that we only look through objects that have the mapping
        # key. Objects not having the mapping key cannot be part of the
        # table.
        datafld = sb.Field(self._pj_table, 'data')
        if self._pj_mapping_key is not None:
            queries.append(
                sb.JSONB_CONTAINS(datafld, self._pj_mapping_key))
        # We also make want to make sure we separate the items properly by the
        # container.
        if self._pj_parent_key is not None:
            pv = self._pj_jar._writer.get_state(self._pj_get_parent_key_value())
            queries.append(sb.JGET(datafld, self._pj_parent_key) == pv)
        return sb.AND(*queries)

    def _pj_add_items_filter(self, qry):
        # need to work around here an <expr> AND None situation, which
        # would become <sqlexpr> AND NULL
        itemsqry = self._pj_get_items_filter()
        if qry is not None:
            if itemsqry is not None:
                return qry & itemsqry
            else:
                return qry
        return itemsqry

    @property
    def _cache(self):
        if not USE_CONTAINER_CACHE:
            return {}
        txn = transaction.manager.get()
        if not hasattr(txn, '_v_pj_container_cache'):
            txn._v_pj_container_cache = {}
        return txn._v_pj_container_cache.setdefault(self, {})

    @property
    def _cache_complete(self):
        if not USE_CONTAINER_CACHE:
            return False
        txn = transaction.manager.get()
        if not hasattr(txn, '_v_pj_container_cache_complete'):
            txn._v_pj_container_cache_complete = {}
        return txn._v_pj_container_cache_complete.get(self, False)

    def _cache_mark_complete(self):
        txn = transaction.manager.get()
        if not hasattr(txn, '_v_pj_container_cache_complete'):
            txn._v_pj_container_cache_complete = {}
        txn._v_pj_container_cache_complete[self] = True

    def _cache_get_key(self, id, doc):
        return doc[self._pj_mapping_key]

    def _locate(self, obj, id, doc):
        """Helper method that is only used when locating items that are already
        in the container and are simply loaded from PostGreSQL."""
        if obj.__name__ is None:
            obj._v_name = doc[self._pj_mapping_key]
        if obj.__parent__ is None:
            obj._v_parent = self

    def _load_one(self, id, doc):
        """Get the python object from the id/doc state"""
        obj = self._cache.get(self._cache_get_key(id, doc))
        if obj is not None:
            return obj
        # Create a DBRef object and then load the full state of the object.
        dbref = serialize.DBRef(self._pj_table, id, self._pj_jar.database)
        # Stick the doc into the _latest_states:
        self._pj_jar._latest_states[dbref] = doc
        obj = self._pj_jar.load(dbref)
        self._locate(obj, id, doc)
        # Add the object into the local container cache.
        self._cache[obj.__name__] = obj
        return obj

    def __cmp__(self, other):
        # UserDict implements the semantics of implementing comparison of
        # items to determine equality, which is not what we want for a
        # container, so we revert back to the default object comparison.
        return cmp(id(self), id(other))

    def __getitem__(self, key):
        # First check the container cache for the object.
        obj = self._cache.get(key)
        if obj is not None:
            return obj
        if self._cache_complete:
            raise KeyError(key)
        # The cache cannot help, so the item is looked up in the database.
        datafld = sb.Field(self._pj_table, 'data')
        fld = sb.JGET(datafld, self._pj_mapping_key)
        qry = (fld == key)
        obj = self.find_one(qry)
        if obj is None:
            raise KeyError(key)
        return obj

    def _real_setitem(self, key, value):
        # Make sure the value is in the database, since we might want
        # to use its oid.
        if value._p_oid is None:
            self._pj_jar.insert(value)

        # This call by itself causes the state to change _p_changed to True.
        if self._pj_mapping_key is not None:
            setattr(value, self._pj_mapping_key, key)
        if self._pj_parent_key is not None:
            setattr(value, self._pj_parent_key, self._pj_get_parent_key_value())

    def __setitem__(self, key, value):
        # When the key is None, we need to determine it.
        if key is None:
            if self._pj_mapping_key is None:
                key = self._pj_jar.createId()
            else:
                # we have _pj_mapping_key, use that attribute
                key = getattr(value, self._pj_mapping_key)
        # We want to be as close as possible to using the Zope semantics.
        contained.setitem(self, self._real_setitem, key, value)
        # Also add the item to the container cache.
        self._cache[key] = value

    def add(self, value, key=None):
        # We are already supporting ``None`` valued keys, which prompts the key
        # to be determined here. But people felt that a more explicit
        # interface would be better in this case.
        self[key] = value

    def __delitem__(self, key):
        value = self[key]
        # First remove the parent and name from the object.
        if self._pj_mapping_key is not None:
            try:
                delattr(value, self._pj_mapping_key)
            except AttributeError:
                # Sometimes we do not control those attributes.
                pass
        if self._pj_parent_key is not None:
            try:
                delattr(value, self._pj_parent_key)
            except AttributeError:
                # Sometimes we do not control those attributes.
                pass
        # Let's now remove the object from the database.
        if self._pj_remove_documents:
            self._pj_jar.remove(value)
        # Remove the object from the container cache.
        if USE_CONTAINER_CACHE:
            del self._cache[key]
        # Send the uncontained event.
        contained.uncontained(value, self, key)

    def __contains__(self, key):
        if self._cache_complete:
            return key in self._cache

        if key in self._cache:
            return True

        datafld = sb.Field(self._pj_table, 'data')
        fld = sb.JGET(datafld, self._pj_mapping_key)
        qry = (fld == key)

        res = self.count(qry)
        return res > 0


    def __iter__(self):
        # If the cache contains all objects, we can just return the cache keys.
        if self._cache_complete:
            return iter(self._cache)
        datafld = sb.Field(self._pj_table, 'data')
        fld = sb.JGET(datafld, self._pj_mapping_key)
        qry = (fld != None)
        result = self.raw_find(qry, fields=(self._pj_mapping_key,))
        return iter(doc[self._pj_mapping_key] for doc in result)

    def keys(self):
        return list(self.__iter__())

    def iteritems(self):
        # If the cache contains all objects, we can just return the cache keys.
        if self._cache_complete:
            return self._cache.iteritems()
        result = self.raw_find(self._pj_get_items_filter())
        items = [(row['data'][self._pj_mapping_key],
                  self._load_one(row['id'], row['data']))
                 for row in result]
        # Signal the container that the cache is now complete.
        self._cache_mark_complete()
        # Return an iterator of the items.
        return iter(items)

    def _get_sb_fields(self, fields):
        """Return sqlbuilder fields based on passed field names or * if no
        fields are passed"""
        if not fields:
            res = sb.Field(self._pj_table, '*')
        else:
            datafld = sb.Field(self._pj_table, 'data')
            res = []
            first_class_fields = {'id', 'data'}
            # prefer sql columns over json fields
            # XXX: this does not work, because we need here the contained object
            #if interfaces.IColumnSerialization.providedBy(self):
            #    for field in self._pj_column_fields:
            #        first_class_fields.add(field.__name__)
            for name in fields:
                if name in first_class_fields:
                    res.append(sb.Field(self._pj_table, name))
                else:
                    if '.' not in name:
                        accessor = sb.JSON_GETITEM(datafld, name)
                    else:
                        accessor = sb.JSON_PATH(datafld, name.split("."))
                    res.append(sb.ColumnAS(accessor, name.replace('.', '_')))
                # XXX: handle functions later here
        return res

    # BBB: providing support for mongo style queries
    #      anything further is just a pain, like figuring fields
    #      and keeping return values unchanged
    #      (in the means of returning the same dict)
    def convert_mongo_query(self, spec):
        warnings.warn("Using mongo queries is deprecated",
                      DeprecationWarning, stacklevel=3)
        c = Converter(self._pj_table, 'data')
        qry = c.convert(spec)
        return qry

    def raw_find(self, qry=None, fields=(), **kwargs):
        if isinstance(qry, dict):
            qry = self.convert_mongo_query(qry)
        qry = self._pj_add_items_filter(qry)

        # returning the cursor instead of fetchall at the cost of not closing it
        # iterating over the cursor is better and this way we expose rowcount
        # and friends
        cur = self._pj_jar.getCursor()
        if qry is None:
            cur.execute(sb.Select(self._get_sb_fields(fields), **kwargs))
        else:
            cur.execute(sb.Select(self._get_sb_fields(fields), qry, **kwargs))
        return cur

    def find(self, qry=None, **kwargs):
        # Search for matching objects.
        result = self.raw_find(qry, **kwargs)
        for row in result:
            obj = self._load_one(row['id'], row['data'])
            yield obj

    def raw_find_one(self, qry=None, id=None):
        if qry is None and id is None:
            raise ValueError(
                'Missing parameter, at least qry or id must be specified.')
        if isinstance(qry, dict):
            qry = self.convert_mongo_query(qry)
        tbl = sb.Table(self._pj_table)
        if qry is None:
            qry = (tbl.id == id)
        elif id is not None:
            qry = qry & (tbl.id == id)
        qry = self._pj_add_items_filter(qry)

        with self._pj_jar.getCursor() as cur:
            cur.execute(sb.Select(sb.Field(self._pj_table, '*'), qry, limit=2))
            if cur.rowcount == 0:
                return None
            if cur.rowcount > 1:
                raise ValueError('Multiple results returned.')
            return cur.fetchone()

    def find_one(self, qry=None, id=None):
        res = self.raw_find_one(qry, id)
        if res is None:
            return None
        return self._load_one(res['id'], res['data'])

    def count(self, qry=None):
        if isinstance(qry, dict):
            qry = self.convert_mongo_query(qry)

        where = self._pj_add_items_filter(qry)
        count = sb.func.COUNT(sb.Field(self._pj_table, 'id'))
        if where is None:
            select = sb.Select(count)
        else:
            select = sb.Select(count, where=where)

        with self._pj_jar.getCursor() as cur:
            cur.execute(select)
            return cur.fetchone()[0]

    def clear(self):
        for key in self.keys():
            del self[key]
        # Signal the container that the cache is now complete.
        # we just removed all objects, eh?
        self._cache.clear()
        self._cache_mark_complete()

    def __nonzero__(self):
        where = self._pj_add_items_filter(None) or True
        select = sb.Select(sb.func.COUNT(sb.Field(self._pj_table, 'id')),
                           where=where)
        with self._pj_jar.getCursor() as cur:
            cur.execute(select)
            return cur.fetchone()[0] > 0


class IdNamesPJContainer(PJContainer):
    """A container that uses the PostGreSQL table UID as the name/key."""
    _pj_mapping_key = None

    def __init__(self, table=None, parent_key=None):
        super(IdNamesPJContainer, self).__init__(table, parent_key)

    @property
    def _pj_remove_documents(self):
        # Objects must be removed, since removing the id of a document is not
        # allowed.
        return True

    def _cache_get_key(self, id, doc):
        return id

    def _locate(self, obj, id, doc):
        obj._v_name = id
        obj._v_parent = self

    def __getitem__(self, key):
        # First check the container cache for the object.
        obj = self._cache.get(key)
        if obj is not None:
            return obj
        if self._cache_complete:
            raise KeyError(key)
        # We do not have a cache entry, so we look up the object.
        filter = self._pj_get_items_filter()
        obj = self.find_one(filter, id=key)
        if obj is None:
            raise KeyError(key)
        return obj

    def __contains__(self, key):
        # If all objects are loaded, we can look in the local object cache.
        if self._cache_complete:
            return key in self._cache
        # Look in PostGreSQL.
        return self.raw_find_one(id=key) is not None

    def __iter__(self):
        # If the cache contains all objects, we can just return the cache keys.
        if self._cache_complete:
            return iter(self._cache)
        # Look up all ids in PostGreSQL.
        result = self.raw_find(None)
        return iter(unicode(row['id']) for row in result)

    def iteritems(self):
        # If the cache contains all objects, we can just return the cache keys.
        if self._cache_complete:
            return self._cache.iteritems()
        # Load all objects from the database.
        result = self.raw_find(self._pj_get_items_filter())
        items = [(row['id'],
                  self._load_one(row['id'], row['data']))
                 for row in result]
        # Signal the container that the cache is now complete.
        self._cache_mark_complete()
        # Return an iterator of the items.
        return iter(items)

    def _real_setitem(self, key, value):
        # We want JSONB document ids to be our keys, so pass it to insert(), if
        # key is provided
        if value._p_oid is None:
            self._pj_jar.insert(value, key)

        super(IdNamesPJContainer, self)._real_setitem(key, value)


class AllItemsPJContainer(PJContainer):
    _pj_parent_key = None


class SubDocumentPJContainer(PJContained, PJContainer):
    _p_pj_sub_object = True
