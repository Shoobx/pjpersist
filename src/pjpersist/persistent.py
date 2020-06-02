##############################################################################
#
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
"""Persistent Object Support"""
import persistent
import zope.interface

from pjpersist import interfaces


@zope.interface.implementer(interfaces.IPersistentSerializationHooks)
class PersistentSerializationHooks(persistent.Persistent):

    def _pj_after_store_hook(self, conn):
        return None

    def _pj_after_load_hook(self, conn):
        return None


@zope.interface.implementer(interfaces.IColumnSerialization)
class SimpleColumnSerialization(object):

    _pj_column_fields = ()

    def _pj_get_column_fields(self):
        return {
            field.__name__: getattr(self, field.__name__)
            for field in self._pj_column_fields}


# XXX: extend later to a z3c.form'ish Fields to have `omit` too
def select_fields(schema, *fieldnames):
    return tuple(schema[fname] for fname in fieldnames)
