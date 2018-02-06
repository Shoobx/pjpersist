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
"""Query statistics reporter tests"""

import doctest

from pjpersist import testing
from pjpersist.querystats import QueryReport


def doctest_calculate_empty():
    """
    Stats on fresh collector indicate 0 queries
        >>> qr = QueryReport()
        >>> qr.calc_totals()
        QueryTotals(total_queries=0, total_time=0, sorted_queries=[])
    """


def doctest_calculate_several():
    """
    Record several queries and calculate stats

        >>> qr = QueryReport()
        >>> qr.record("SELECT 1", [], 0.005)
        >>> qr.record("SELECT 2", [], 0.0001)
        >>> qr.record("SELECT 3", [], 0.8)

        >>> stats = qr.calc_totals()
        >>> stats
        QueryTotals(total_queries=3, total_time=0.8051, sorted_queries=[...])

        >>> [q.query for q in stats.sorted_queries]
        ['SELECT 2', 'SELECT 1', 'SELECT 3']
    """


def doctest_calc_and_report_empty():
    """
    Print out empty query report

        >>> qr = QueryReport()
        >>> print(qr.calc_and_report())
        Query report: no queries were executed
        """


def doctest_calc_and_report_several():
    """
    Record several queries and produce report

        >>> qr = QueryReport()
        >>> qr.record("SELECT 1", [], 0.005)
        >>> qr.record("SELECT 2", (1, 2, 3), 0.0001)
        >>> qr.record("SELECT 3", ["a", "b", 3], 0.8)
        >>> qr.report_traceback = True

        >>> print(qr.calc_and_report())
        Query report:
        ------------------------------------------------------------
        10 most expensive queries:
        *** SELECT 2
        ... ARGS: (1, 2, 3)
        ... TIME: 0.1000ms
        File ...
        <BLANKLINE>
        *** SELECT 1
        ... ARGS: []
        ... TIME: 5.0000ms
        File ...
        <BLANKLINE>
        *** SELECT 3
        ... ARGS: ['a', 'b', 3]
        ... TIME: 800.0000ms
        File ...
        <BLANKLINE>
        ------------------------------------------------------------
        Queries executed: 3
        Time spent: 805.1000ms
    """


def test_suite():
    dtsuite = doctest.DocTestSuite(
        optionflags=testing.OPTIONFLAGS)

    return dtsuite

