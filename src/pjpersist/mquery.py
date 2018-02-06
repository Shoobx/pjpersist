##############################################################################
#
# Copyright (c) 2014 Zope Foundation and Contributors.
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
"""Mongo-like queries for PJ"""

import json
from pjpersist import sqlbuilder as sb
from pjpersist import serialize


class Converter(object):
    """Translator for MongoDB queries -> sqlbuilder expressions.

    The resultant expressions can be used as WHERE clauses in queries.

    This implements only a subset of the query language.
    """

    simplified = False

    def __init__(self, table, field):
        self.table = table
        self.field = field

    def convert(self, query):
        clauses = []
        doc = sb.Field(self.table, self.field)
        for key, value in sorted(query.items()):
            accessor = self.getField(doc, key, json=True)
            # some values, esp. datetime must go through PJ serialize
            pjvalue = serialize.ObjectWriter(None).get_state(value)
            jvalue = json.dumps(pjvalue, sort_keys=True)

            if key == '_id':
                jvalue = value

            if key in ('$and', '$or', '$nor', '$startswith'):
                if not isinstance(value, (list, tuple)):
                    raise ValueError("Argument must be a list: %r" % value)
                oper = {
                    '$and': sb.AND,
                    '$or': sb.OR,
                    '$nor': lambda *items: sb.NOT(sb.OR(*items)),
                    '$startswith': sb.STARTSWITH  # special case for a $regex
                }[key]
                clauses.append(oper(*(self.convert(expr) for expr in value)))
            elif isinstance(value, dict):
                for operator, operand in sorted(value.items()):
                    clauses.append(
                        self.operator_expr(
                            operator, doc, key, operand))
            else:
                # Scalar -- equality or array membership
                if self.simplified or key == '_id':
                    # Let's ignore the membership case for test clarity
                    clauses.append(accessor == jvalue)
                else:
                    options = [
                        accessor == jvalue,
                        sb.JSONB_SUBSET(sb.JSONB(json.dumps([pjvalue])),
                                        accessor)
                    ]
                    if value is None:
                        options.append(sb.ISNULL(accessor))
                    clauses.append(sb.OR(*options))
        return sb.AND(*clauses)

    def getField(self, field, key, json=False):
        if isinstance(field, sb.SQLConstant):
            # hack for $elemMatch
            accessor = field
        elif key == '_id':
            accessor = sb.Field(self.table, 'id')
        elif json:
            if '.' not in key:
                accessor = sb.JSON_GETITEM(field, key)
            else:
                accessor = sb.JSON_PATH(field, key.split("."))
        else:
            if '.' not in key:
                accessor = sb.JSON_GETITEM_TEXT(field, key)
            else:
                accessor = sb.JSON_PATH_TEXT(field, key.split("."))

        return accessor

    def operator_expr(self, operator, field, key, op2):
        op1 = self.getField(field, key, json=True)
        # some values, esp. datetime must go through PJ serialize
        pjvalue = serialize.ObjectWriter(None).get_state(op2)
        op2j = json.dumps(pjvalue, sort_keys=True)

        if key == '_id':
            op2j = op2

        if operator == '$gt':
            return op1 > op2j
        if operator == '$lt':
            return op1 < op2j
        if operator == '$gte':
            return op1 >= op2j
        if operator == '$lte':
            return op1 <= op2j
        if operator == '$ne':
            return op1 != op2j
        if operator == '$in':
            if not op2:
                # SQL burps on empty lists with IN:
                return False
            # The $in operator in Mongo is pretty powerful, since it
            # implements the classic "in" (contains) and the "any" operator.
            # There is an optimization for strings:
            #      sb.JSONB_CONTAINS_ANY(op1, [unicode(e) for e in op2])
            ops = [sb.IN(op1, [sb.JSONB(json.dumps(el)) for el in op2])]
            ops += [sb.JSONB_SUPERSET(op1, json.dumps(el)) for el in op2]
            return sb.OR(*ops)
        if operator == '$nin':
            if not op2:
                # SQL burps on empty lists with IN:
                return True
            # The $nin operator in Mongo is pretty powerful, since it
            # implements the classic "not in" (not contains) and the "not any"
            # operator.
            # There is an optimization for strings:
            #      sb.JSONB_CONTAINS_ANY(op1, [unicode(e) for e in op2])
            ops = [sb.IN(op1, [sb.JSONB(json.dumps(el)) for el in op2]),]
            ops += [sb.JSONB_SUPERSET(op1, json.dumps(el)) for el in op2]
            return sb.NOT(sb.OR(*ops))
        if operator == '$not':
            # MongoDB's rationalization for this operator:
            # it matches when op1 does not pass the condition
            # or when op1 is not set at all.
            return sb.OR(
                sb.ISNULL(op1),
                sb.NOT(sb.AND(
                    *(self.operator_expr(operator2, field, key, op3)
                      for operator2, op3 in op2.items())
                )))
        if operator == '$size':
            return sb.func.jsonb_array_length(op1) == op2
        if operator == '$exists':
            return sb.ISNOTNULL(op1) if op2 else sb.ISNULL(op1)
        if operator == '$any':
            return sb.JSONB_CONTAINS_ANY(op1, op2)
        if operator == '$nany':
            return sb.NOT(sb.JSONB_CONTAINS_ANY(op1, op2))
        if operator == '$all':
            return sb.JSONB_SUPERSET(op1, op2j)
        if operator == '$elemMatch':
            op1 = sb.NoTables(op1)
            # SELECT data FROM tbl WHERE EXISTS (
            #          SELECT value
            #          FROM jsonb_array_elements(data -> 'arr')
            #          WHERE value < '3' AND value >= '2'
            # );
            return sb.EXISTS(
                sb.Select(
                    ['value'],
                    staticTables=[sb.func.jsonb_array_elements(op1)],
                    where=sb.NoTables(sb.AND(*(
                        sb.AND(*(
                            self.operator_expr(operator2, sb.SQLConstant('value'), key, op3)
                            for operator2, op3 in query.items()
                        ))
                        for query in op2
                    )))
                )
            )
        if operator == '$startswith':
            return sb.STARTSWITH(sb.TEXT(op1), op2)
        if operator == '$regex':
            return sb.RLIKE(sb.TEXT(op1), op2)
        else:
            raise ValueError("Unrecognized operator %s" % operator)
