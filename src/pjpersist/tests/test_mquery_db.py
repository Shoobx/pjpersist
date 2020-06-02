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
import doctest
import json
import pprint

from pjpersist import testing, mquery, sqlbuilder as sb

dataset = [
    {'foo': 'bar'},
    {'nr': 42},
    {'some': {'numbers': [42, 69, 105]}, "nr": None},
    {'more': {'strings': ['a', 'f', 'x']}, "nr": [1, None]},
    {'plan': 'getdown', 'day': 'Friday', 'drink': 'whiskey', 'nr': 42},
]

def jformat(obj):
    """Helper for inserting JSON"""
    return "('%s')" % json.dumps(obj).replace("'", "''")


def setUp(test):
    testing.setUp(test)

    conn = test.globs['conn']
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE mq (id SERIAL PRIMARY KEY, data JSONB)")
        cur.execute("INSERT INTO mq (data) VALUES " +
                    ", ".join(jformat(datum) for datum in dataset))
    conn.commit()


def select(conn, query, print_sql=False):
    try:
        with conn.cursor() as cur:
            converter = mquery.Converter("mq", "data")
            sql = sb.sqlrepr(
                sb.Select(sb.Field("mq", "data"), where=converter.convert(query)),
                'postgres'
            )
            if print_sql:
                print('SQL> ', sql)
            cur.execute(sql)
            for e in cur.fetchall():
                pprint.pprint(e[0])
    finally:
        conn.rollback()

def doctest_operators():
    """Test simple selectors and comparisons:


    We can do simple matches of strings:

       >>> select(conn, {'foo': 'bar'})
       {'foo': 'bar'}

    And numbers:

       >>> select(conn, {'nr': 42})
       {'nr': 42}
       {'day': 'Friday', 'drink': 'whiskey', 'nr': 42, 'plan': 'getdown'}

    We can query for an element in the list:

       >>> select(conn, {'some.numbers': 69})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

    Comparison operators:

       >>> select(conn, {'nr': {'$gt': 40}})
       {'nr': 42}
       {'more': {'strings': ['a', 'f', 'x']}, 'nr': [1, None]}
       {'day': 'Friday', 'drink': 'whiskey', 'nr': 42, 'plan': 'getdown'}

    List searches:

       >>> select(conn, {'nr': {'$in': [40, 41, 42]}})
       {'nr': 42}
       {'day': 'Friday', 'drink': 'whiskey', 'nr': 42, 'plan': 'getdown'}

       >>> select(conn, {'foo': {'$in': ['foo', 'bar', 'baz']}})
       {'foo': 'bar'}

       >>> select(conn, {'foo': {'$nin': ['foo', 'baz']}})
       {'foo': 'bar'}

       >>> select(conn, {'more.strings': {'$in': ['a', 'g']}})
       {'more': {'strings': ['a', 'f', 'x']}, 'nr': [1, None]}

       >>> select(conn, {'more.strings': {'$in': ['h', 'g']}})

       >>> select(conn, {'some.numbers': {'$in': [42, 200]}})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

       >>> select(conn, {'some.numbers': {'$in': [80, 200]}})

    Edge cases with empty lists:

       >>> select(conn, {'nr': {'$in': []}}, True)
       SQL>  SELECT mq.data FROM mq WHERE 'f'

       >>> select(conn, {'nr': {'$nin': []}}, True)
       SQL>  SELECT mq.data FROM mq WHERE 't'
       {'foo': 'bar'}
       {'nr': 42}
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}
       {'more': {'strings': ['a', 'f', 'x']}, 'nr': [1, None]}
       {'day': 'Friday', 'drink': 'whiskey', 'nr': 42, 'plan': 'getdown'}


    Existence of keys:

       >>> select(conn, {'some.numbers': {'$exists': True}})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

       >>> select(conn, {'nr': {'$exists': False}})
       {'foo': 'bar'}

    Negation of comparisons:

       >>> select(conn, {'nr': {'$not': {'$gt': 40}}})
       {'foo': 'bar'}
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

       >>> select(conn, {'nr': {'$not': {'$gt': 42}}})
       {'foo': 'bar'}
       {'nr': 42}
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}
       {'day': 'Friday', 'drink': 'whiskey', 'nr': 42, 'plan': 'getdown'}

    List sizes:

       >>> select(conn, {'some.numbers': {'$size': 3}})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

    $all:

       >>> select(conn, {'some.numbers': {'$all': [69, 42]}})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

       >>> select(conn, {'some.numbers': {'$all': [69, 43]}})

    $elemMatch matches when one of the array elements matches all
    conditions:

       >>> select(conn, {'some.numbers': {'$elemMatch':
       ...                   [{'$gt': 68}, {'$lt': 70}]}})
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}

       >>> select(conn, {'some.numbers': {'$elemMatch':
       ...                   [{'$gt': 60}, {'$lt': 65}]}})

    _id is specialcased:

       >>> select(conn, {'_id': 1}, True)
       SQL>  SELECT mq.data FROM mq WHERE ((mq.id) = (1))
       {'foo': 'bar'}

       >>> select(conn, {'_id': {'$lt': 2}}, True)
       SQL>  SELECT mq.data FROM mq WHERE ((mq.id) < (2))
       {'foo': 'bar'}

    Comparing to null in Mongo matches if the value is indeed null, or
    if the value does not exist, or ir the value is a list containing null!

       >>> select(conn, {'nr': None}, True)
       SQL>  SELECT mq.data FROM mq
               WHERE ((((mq.data) -> ('nr')) = ('null'))
                   OR ((('[null]'::jsonb) <@ ((mq.data) -> ('nr')))
                   OR (((mq.data) -> ('nr')) IS NULL)))
       {'foo': 'bar'}
       {'nr': None, 'some': {'numbers': [42, 69, 105]}}
       {'more': {'strings': ['a', 'f', 'x']}, 'nr': [1, None]}

    """


def test_suite():
    suite =  doctest.DocTestSuite(
        setUp=setUp, tearDown=testing.tearDown,
        checker=testing.checker,
        optionflags=testing.OPTIONFLAGS)
    suite.layer = testing.db_layer
    return suite
