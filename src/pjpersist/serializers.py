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
"""Python Serializers for common objects with weird reduce output."""
import datetime
from pjpersist import serialize


class DateSerializer(serialize.ObjectSerializer):

    fmt = "%Y-%m-%d"

    def can_read(self, state):
        return isinstance(state, dict) and \
               state.get('_py_type') == 'datetime.date'

    def read(self, state):
        return datetime.datetime.strptime(state['value'], self.fmt).date()

    def can_write(self, obj):
        return type(obj) is datetime.date

    def write(self, obj):
        return {'_py_type': 'datetime.date',
                'value': obj.strftime(self.fmt).zfill(10)}


class TimeSerializer(serialize.ObjectSerializer):

    fmt = "%H:%M:%S"

    def can_read(self, state):
        return isinstance(state, dict) and \
               state.get('_py_type') == 'datetime.time'

    def read(self, state):
        return datetime.datetime.strptime(state['value'], self.fmt).time()

    def can_write(self, obj):
        return type(obj) is datetime.time

    def write(self, obj):
        return {'_py_type': 'datetime.time',
                'value': obj.strftime(self.fmt)}


class DateTimeSerializer(serialize.ObjectSerializer):

    # XXX: timezone?
    fmt = "%Y-%m-%dT%H:%M:%S.%f"

    def can_read(self, state):
        return isinstance(state, dict) and \
               state.get('_py_type') == 'datetime.datetime'

    def read(self, state):
        return datetime.datetime.strptime(state['value'], self.fmt)

    def can_write(self, obj):
        return type(obj) is datetime.datetime

    def write(self, obj):
        return {'_py_type': 'datetime.datetime',
                'value': obj.strftime(self.fmt).zfill(26)}
