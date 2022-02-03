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
"""SQLBuilder extensions"""
import json, re

from sqlobject.sqlbuilder import *


########################################
## Postgres JSON operators
########################################

# Let's have them here and then see if they're worth contributing
# upstream when they settle down.

class PGArray(SQLExpression):
    """PostgreSQL array expression.

    The downside of current implementation is that the items must be
    the same type.  Literal arrays like '{1, 1.5, "two"}' can be
    non-homogenous, but need different quoting of strings.
    """

    def __init__(self, iterable):
        self.iterable = iterable

    def __sqlrepr__(self, db):
        assert db == 'postgres', "Postgres-specific feature, sorry."
        items = (sqlrepr(item, db) for item in self.iterable)
        return 'array[%s]' % ", ".join(items)


class PGArrayLiteral(SQLExpression):
    """PostgreSQL array literal expression.

    This works with all types except floats because paths are
    separated by periods also.  This is mostly used for dict/array keys so
    it shouldn't be much of a problem
    Literal arrays don't need quotes around the values like '{a, b, 1, 2}',
    but optional double quoting of string values is valid and helpful certain
    cases, like words with apostrophes I.E '{"Bob''s"}'
    """

    def __init__(self, iterable):
        self.iterable = iterable

    def __sqlrepr__(self, db):
        assert db == 'postgres', "Postgres-specific feature, sorry."
        # strip quotes off of nested array literals
        items = (sqlrepr(item, db) if not
                 isinstance(item, self.__class__) else sqlrepr(item, db)[1:-1]
                 for item in self.iterable)
        literal = '{%s}' % ", ".join(items)
        # switches single quotes to double quotes if there aren't
        # 2 single quotes in a row, which indicates an escaped apostrophe
        regex = re.compile("(?<!')'(?!')")
        return "'{}'".format(regex.sub('"', literal))


class TYPECAST(SQLExpression):
    """Cast to a type"""

    cast = None

    def __init__(self, arg, typ=None):
        self.arg = arg
        if typ is not None:
            self.cast = '::' + typ

    def __sqlrepr__(self, db):
        return sqlrepr(self.arg, db) + self.cast


class JSONB(TYPECAST):
    """Cast to JSONB"""
    cast = "::jsonb"


class JSON(TYPECAST):
    """Cast to JSON"""
    cast = '::json'


class TEXT(TYPECAST):
    """Cast to text"""
    cast = '::text'


def JSON_GETITEM(json, key):
    return SQLOp("->", json, key)

def JSON_GETITEM_TEXT(json, key):
    return SQLOp("->>", json, key)

def JSON_PATH(json, keys):
    """keys is an SQL array"""
    return SQLOp("#>", json, PGArray(keys))

def JSON_PATH_TEXT(json, keys):
    """keys is an SQL array"""
    return SQLOp("#>>", json, PGArrayLiteral(keys))

def JSONB_SUPERSET(superset, subset):
    return SQLOp("@>", superset, subset)

def JSONB_SUBSET(subset, superset):
    return SQLOp("<@", subset, superset)

def JSONB_CONTAINS(jsonb, key):
    return SQLOp("?", jsonb, key)

def JSONB_CONTAINS_ANY(jsonb, keys):
    """keys is an AdditionSQL array"""
    return SQLOp("?|", jsonb, PGArray(keys))

def JSONB_CONTAINS_ALL(jsonb, keys):
    """keys is an SQL array"""
    return SQLOp("?&", jsonb, PGArray(keys))

def ARRAY_CONTAINS(arr, values):
    return SQLOp("@>", arr, PGArray(values))

def ARRAY_OVERLAPS(arr, values):
    return SQLOp("&&", arr, PGArray(values))


class JGET(object):
    """JSON field getter that JSONifies the second argument of comparisons.

    Normally it just gets a JSON key of a table field:

       >>> print(JGET("data", "key", table="Person").__sqlrepr__('postgres'))
       ((Person.data) -> ('key'))

    We can also pass a field object and omit the table:

       >>> print(JGET(Field("Person", "data"), "key").__sqlrepr__('postgres'))
       ((Person.data) -> ('key'))

    The right operand for comparison operators gets converted to JSON:

       >>> print((JGET("data", "key", table="Person") == {'foo': 'bar'}
       ...     ).__sqlrepr__('postgres'))
       (((Person.data) -> ('key')) = ('{"foo": "bar"}'::jsonb))

       >>> print((JGET("data", "key", table="Person") >= [True, False, None]
       ...     ).__sqlrepr__('postgres'))
       (((Person.data) -> ('key')) >= ('[true, false, null]'::jsonb))

    But not always (is this a good idea?):
    (adamG: no it's not a good idea, because -> returns jsonb which is never NULL
    see doctest_datetime_range)

       >>> print((JGET("data", "key", table="Person") == None
       ...     ).__sqlrepr__('postgres'))
       (((Person.data) -> ('key')) = ('null'::jsonb))

       >>> print((JGET("data", "key", table="Person") != None
       ...     ).__sqlrepr__('postgres'))
       (((Person.data) -> ('key')) <> ('null'::jsonb))
    """

    def __init__(self, field, selector, table=None):
        if table is not None:
            self.field = Field(table, field)
        else:
            self.field = field
        self.selector = selector

    def __lt__(self, other):
        return SQLOp("<", self, JSONB(json.dumps(other, sort_keys=True)))
    def __le__(self, other):
        return SQLOp("<=", self, JSONB(json.dumps(other, sort_keys=True)))
    def __gt__(self, other):
        return SQLOp(">", self, JSONB(json.dumps(other, sort_keys=True)))
    def __ge__(self, other):
        return SQLOp(">=", self, JSONB(json.dumps(other, sort_keys=True)))
    def __eq__(self, other):
        return SQLOp("=", self, JSONB(json.dumps(other, sort_keys=True)))
    def __ne__(self, other):
        return SQLOp("<>", self, JSONB(json.dumps(other, sort_keys=True)))
    def __and__(self, other):
        return SQLOp("AND", self, JSONB(json.dumps(other, sort_keys=True)))
    def __rand__(self, other):
        return SQLOp("AND", JSONB(json.dumps(other, sort_keys=True), self))
    def __or__(self, other):
        return SQLOp("OR", self, JSONB(json.dumps(other, sort_keys=True)))
    def __ror__(self, other):
        return SQLOp("OR", JSONB(json.dumps(other, sort_keys=True), self))
    def __invert__(self):
        return SQLPrefix("NOT", self)

    def __sqlrepr__(self, db):
        expr = JSON_GETITEM(self.field, self.selector)
        return sqlrepr(expr, db)


class NoTables(SQLExpression):
    """A dirty hack that fools the tablesUsedSet detection"""
    def __init__(self, expr):
        self.expr = expr

    def __sqlrepr__(self, db):
        return sqlrepr(self.expr, db)

    def tablesUsedImmediate(self, db):
        return []

    def tablesUsedSet(self, db):
        return set()

    def tablesUsed(self, db):
        return {}


class Function(SQLExpression):

    def __init__(self, fname, *args):
        self.fname = fname
        self.args = args

    def __sqlrepr__(self, db):
        args = [sqlrepr(arg, db) for arg in self.args]
        return "%s(%s)" % (self.fname, ', '.join(args))


class ARRAY_TO_STRING(Function):

    def __init__(self, array, sep):
        Function.__init__(self, 'array_to_string', array, sep)


class WithSubquery(SQLExpression):
    """Represents single subquery in WITH statement
    """
    def __init__(self, name, select, parameters=None):
        self.name = name
        self.select = select
        self.parameters = parameters

    def __sqlrepr__(self, db):
        params = ""
        if self.parameters:
            params = ', '.join(self.parameters)
            params = " (%s)" % params

        return "%s%s AS ( %s )" % (self.name, params,
                                  sqlrepr(self.select, db))


class With(SQLExpression):
    def __init__(self, subqueries, select, recursive=False):
        self.subqueries = subqueries
        self.select = select
        self.recursive = recursive

    def __sqlrepr__(self, db):
        subqs = ', '.join([sqlrepr(sq, db) for sq in self.subqueries])
        rec = " RECURSIVE" if self.recursive else ""
        return "WITH%s %s %s" % (rec, subqs, sqlrepr(self.select, db))


class _BetterUnion(Union):
    # We need to enclose queries we union into parenthesis, so queries can have
    # ORDER BY clause.
    def __sqlrepr__(self, db):
        return " UNION ".join(["( %s )" % str(sqlrepr(t, db))
                              for t in self.tables])

class UnionAll(Union):
    def __sqlrepr__(self, db):
        return " UNION ALL ".join(["( %s )" % str(sqlrepr(t, db))
                                  for t in self.tables])

# We can replace Union with _BetterUnion now, so all existing code uses it
Union = _BetterUnion

class ILIKE(LIKE):
    """Case-insensitive pair of LIKE

    ILIKE is a valid postgres keyword, but not implemented by sqlobject"""
    op = "ILIKE"
