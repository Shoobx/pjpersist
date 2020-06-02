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
"""Statistics on executed queries"""
import sys
from collections import namedtuple

from zope.exceptions import exceptionformatter


QueryStats = namedtuple("QueryStats",
                        ["query", "args", "time", "traceback", "database"])

QueryTotals = namedtuple('QueryTotals',
                         ["total_queries", "total_time", "sorted_queries"])


# Number of most expensive queries to print out
NUM_OF_QUERIES_TO_REPORT = 10

REPORT_TRACEBACK = False

# Traceback limit
TB_LIMIT = 15  # 15 should be sufficient to figure


class QueryReport(object):
    def __init__(self):
        self.qlog = []
        self.report_traceback = REPORT_TRACEBACK

    def record(self, query, args, elapsed_time, database=None):
        """Record executed query

        elapsed_time is time, elapsed by executing query, in secodes
        """
        traceback = self._collect_traceback()
        self.qlog.append(QueryStats(query, args, elapsed_time,
                                    traceback, database))

    def calc_totals(self):
        """Calculate totals and return QueryTotals object
        """

        total_queries = len(self.qlog)
        total_time = sum(q.time for q in self.qlog)
        sorted_queries = sorted(self.qlog, key=lambda q: q.time)
        return QueryTotals(total_queries, total_time, sorted_queries)

    def calc_and_report(self):
        """Calculate totals and print out report
        """
        if len(self.qlog) == 0:
            return "Query report: no queries were executed"
        totals = self.calc_totals()
        sep = '-' * 60

        report = []
        p = report.append

        p("Query report:")
        p(sep)
        p("%s most expensive queries:" % NUM_OF_QUERIES_TO_REPORT)
        for q in totals.sorted_queries[-NUM_OF_QUERIES_TO_REPORT:]:
            p("*** %s" % q.query)
            p("... ARGS: %s" % (q.args,))
            p("... TIME: %.4fms" % (q.time * 1000))
            if self.report_traceback and q.traceback:
                p(q.traceback)
            p("")
        p(sep)
        p("Queries executed: %s" % totals.total_queries)
        p("Time spent: %.4fms" % (totals.total_time * 1000))

        return "\n".join(report)

    def clear(self):
        self.qlog = []

    def _collect_traceback(self):
        try:
            raise ValueError('boom')
        except:
            # we need here exceptionformatter, otherwise __traceback_info__
            # is not added
            stack = exceptionformatter.extract_stack(
                sys.exc_info()[2].tb_frame.f_back, limit=TB_LIMIT)
            tb = ''.join(stack[:-2])
            return tb
