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


def patch_ujson_into_psycopg2():
    # Use fast json parser.
    try:
        import ujson
    except ImportError:
        return

    # patch decoding
    from psycopg2.extras import register_default_json, register_default_jsonb
    register_default_json(globally=True, loads=ujson.loads)
    register_default_jsonb(globally=True, loads=ujson.loads)

    # patch encoding
    from psycopg2 import _json
    _json.json = ujson
