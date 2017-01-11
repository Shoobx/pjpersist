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
"""PostGreSQL/JSONB Persistence Zope Container Interfaces"""
import zope.interface
import zope.schema


class IPJContainer(zope.interface.Interface):

    _pj_table = zope.schema.ASCIILine(
        title=u'PostGreSQL Table',
        description=(
            u'Specifies the PostGreSQL table in which to store items.')
        )

    _pj_mapping_key = zope.schema.ASCIILine(
        title=u'Mapping Key',
        description=(
            u'Specifies the attribute name of the item that is used as the '
            u'mapping/dictionary/container key.'),
        default='key')

    _pj_parent_key = zope.schema.ASCIILine(
        title=u'Parent Key',
        description=(
            u'Specifies the attribute name of the item that is used to store '
            u'the parent/container reference.'),
        default='parent')

    _pj_remove_documents = zope.schema.Bool(
        title=u'Remove Documents',
        description=(
            u'A flag when set causes documents to be removed from the DB when '
            u'they are removed from the container.'),
        default=True)

    _pj_column_fields = zope.schema.Tuple(
        title=u'Column Fields',
        description=(u'A list of fields that represent columns '
                     u'in the storage table. the default values are `id` '
                     u'and `data`, but more can be added.'),
        default=('id', 'data'),
        required=True)

    def _pj_get_parent_key_value():
        """Returns the value that is used to specify a particular container as
        the parent of the item.
        """

    def _pj_get_resolve_filter():
        """Returns a query to apply when querying for single id
        """

    def _pj_get_list_filter():
        """Returns a query spec representing a filter that only returns
        objects in this container."""

    def convert_mongo_query(spec):
        """BBB: providing support for mongo style queries"""

    def raw_find(qry, fields=(), **kwargs):
        """Return a raw psycopg result cursor for the specified query.

        The qry is updated to also contain the container's filter condition.
        ``kwargs`` allows you to pass parameters to sqlbuilder.Select

        Note: The user is responsible of closing the cursor after use.
        """

    def find(qry, **kwargs):
        """Return a Python object result set for the specified query.

        The qry is updated to also contain the container's filter condition.
        ``kwargs`` allows you to pass parameters to sqlbuilder.Select

        Note: The user is responsible of closing the cursor after use.
        """

    def raw_find_one(qry=None, id=None):
        """Return the record for the specified query.

        At least one of the arguments must be specified. If no document was
        found, returns None.

        The qry is updated to also contain the container's filter condition.

        Note: The user is responsible of closing the cursor after use.
        """

    def find_one(qry=None, id=None):
        """Return a single Python object for the specified query.

        At least one of the arguments must be specified.

        The qry is updated to also contain the container's filter condition.

        Note: The user is responsible of closing the cursor after use.
        """

    def count(qry=None):
        """Count items matching query conditions

        Provides a quick way to count items without fetching them from
        database.
        """

    def add(value, key=None):
        """Add an object without necessarily knowing the key of the object.

        Either pass in a valid key or the key will be:
        - in case ``_pj_mapping_key`` is ``None``: the object's OID
        - otherwise ``getattr(value, _pj_mapping_key)``
        """

    def clear():
        """Delete all items from this container.

        Note, that this will not touch all items from the collection, but only
        those, specified in ``_pj_get_items_filter``.
        """
