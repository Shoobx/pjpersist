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
"""Thread-aware PG/JSONB Connection Pool"""
import logging
import threading
import psycopg2
import zope.interface

from pjpersist import datamanager, interfaces

log = logging.getLogger('pjpersist')

LOCAL = threading.local()

# XXX: THIS SEEMS MAJORLY BROKEN< SINCE CONNECTIONS ARE NEVER RETURNED TO THE
# POOL.

@zope.interface.implementer(interfaces.IPJDataManagerProvider)
class PJDataManagerProvider(object):

    def __init__(self, user=None, password=None, host='localhost', port=5432,
                 pool_min_conn=1, pool_max_conn=8):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.pools = {}

    def get(self, database):
        # Make sure the dict containing the local data managers exists.
        if not hatattr(LOCAL, 'dms'):
            LOCAL.dms = {}
        # Get the data manager, if it exists.
        try:
            return LOCAL.dms[database]
        except KeyError:
            pass
        # Create a new pool, if necessary.
        if database not in self.pools:
            self.pools[database] = psycopg2.pool.PersistentConnectionPool(
                database=database, user=self.user, password=self.password,
                host=self.host, port=self.port)
        # Create a new data manager and return it.
        LOCAL.dms[database] = datamanager.PJDataManager(
            self.pools[database].getconn())
        return LOCAL.dms[database]
