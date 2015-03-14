"""
taken from: http://justinfx.com/2012/07/25/python-2-7-3-serializer-speed-comparisons/
"""

import json
import pprint
from timeit import timeit

from pjpersist.tests import random_data
from pjpersist import testing
from pjpersist import serialize


DATA_ORIG = {
    'words': """
        Lorem ipsum dolor sit amet, consectetur adipiscing
        elit. Mauris adipiscing adipiscing placerat.
        Vestibulum augue augue,
        pellentesque quis sollicitudin id, adipiscing.
        """,
    'list': range(100),
    'dict': dict((str(i), 'a') for i in xrange(100)),
    'int': 100,
    'float': 100.123456
}

testing.setUpSerializers(None)
DATA_BIGDICT = serialize.ObjectWriter(None).get_state(random_data.BIGDICT)
DATA_HUGEDICT = serialize.ObjectWriter(None).get_state(random_data.HUGEDICT)

DATA = DATA_HUGEDICT

LOOPS = 1000

setup = "d=%r" % DATA

setup_pickle    = '%s ; import cPickle ; src = cPickle.dumps(d)' % setup
setup_pickle2   = '%s ; import cPickle ; src = cPickle.dumps(d, 2)' % setup
setup_json      = '%s ; import json; src = json.dumps(d)' % setup
setup_msgpack   = '%s ; src = msgpack.dumps(d)' % setup

tests = [
    # (title, setup, enc_test, dec_test)
    ('pickle (ascii)', 'import pickle; %s' % setup_pickle, 'pickle.dumps(d, 0)', 'pickle.loads(src)'),
    ('pickle (binary)', 'import pickle; %s' % setup_pickle2, 'pickle.dumps(d, 2)', 'pickle.loads(src)'),
    ('cPickle (ascii)', 'import cPickle; %s' % setup_pickle, 'cPickle.dumps(d, 0)', 'cPickle.loads(src)'),
    ('cPickle (binary)', 'import cPickle; %s' % setup_pickle2, 'cPickle.dumps(d, 2)', 'cPickle.loads(src)'),
    ('json', 'import json; %s' % setup_json, 'json.dumps(d)', 'json.loads(src)'),
    ('simplejson', 'import simplejson; %s' % setup_json, 'simplejson.dumps(d)', 'simplejson.loads(src)'),
    #('python-cjson-1.0.5', 'import cjson; %s' % setup_json, 'cjson.encode(d)', 'cjson.decode(src)'),
    ('ujson', 'import ujson; %s' % setup_json, 'ujson.dumps(d)', 'ujson.loads(src)'),
    #('yajl 0.3.5', 'import yajl; %s' % setup_json, 'yajl.dumps(d)', 'yajl.loads(src)'),
    #('msgpack-python-0.3.0', 'import msgpack; %s' % setup_msgpack, 'msgpack.dumps(d)', 'msgpack.loads(src)'),
]

def main():
    enc_table = []
    dec_table = []

    print("Running tests (%d LOOPS each)" % LOOPS)
    print("Data repr length: %d" % len(setup))

    for title, mod, enc, dec in tests:
        print(title)

        print("  [Encode]", enc)
        result = timeit(enc, mod, number=LOOPS)
        enc_table.append([title, result])

        print("  [Decode]", dec)
        result = timeit(dec, mod, number=LOOPS)
        dec_table.append([title, result])

    enc_table.sort(key=lambda x: x[1])
    enc_table.insert(0, ['Package', 'Seconds'])

    for x in enc_table:
        x[0] = x[0].ljust(20)

    dec_table.sort(key=lambda x: x[1])
    dec_table.insert(0, ['Package', 'Seconds'])

    for x in dec_table:
        x[0] = x[0].ljust(20)

    print("\nData repr length: %d" % len(setup))
    print("\nEncoding Test (%d LOOPS)" % LOOPS)
    pprint.pprint(enc_table)

    print("\nDecoding Test (%d LOOPS)" % LOOPS)
    pprint.pprint(dec_table)


results = """
results with DATA_ORIG:
------------------------
Encoding Test (15000 LOOPS)
[['Package             ', 'Seconds'],
 ['ujson               ', 0.15531587600708008],
 ['cPickle (binary)    ', 0.18461894989013672],
 ['json                ', 0.4842488765716553],
 ['simplejson          ', 0.6233742237091064],
 ['cPickle (ascii)     ', 0.9148178100585938],
 ['pickle (ascii)      ', 8.630627870559692],
 ['pickle (binary)     ', 8.879431009292603]]

Decoding Test (15000 LOOPS)
[['Package             ', 'Seconds'],
 ['cPickle (binary)    ', 0.23794102668762207],
 ['ujson               ', 0.24951386451721191],
 ['simplejson          ', 0.41387104988098145],
 ['cPickle (ascii)     ', 0.7791750431060791],
 ['json                ', 0.9328320026397705],
 ['pickle (binary)     ', 3.062810182571411],
 ['pickle (ascii)      ', 9.76430606842041]]

results with DATA_BIGDICT:
----------------------------
Encoding Test (15000 LOOPS)
[['Package             ', 'Seconds'],
 ['ujson               ', 0.18154096603393555],
 ['cPickle (binary)    ', 0.33770203590393066],
 ['json                ', 0.38971710205078125],
 ['simplejson          ', 0.6901121139526367],
 ['cPickle (ascii)     ', 0.928969144821167],
 ['pickle (ascii)      ', 6.54378604888916],
 ['pickle (binary)     ', 7.975723028182983]]

Decoding Test (15000 LOOPS)
[['Package             ', 'Seconds'],
 ['ujson               ', 0.23072004318237305],
 ['cPickle (binary)    ', 0.26100707054138184],
 ['simplejson          ', 0.2880890369415283],
 ['cPickle (ascii)     ', 0.4758889675140381],
 ['json                ', 0.891761064529419],
 ['pickle (binary)     ', 3.5709359645843506],
 ['pickle (ascii)      ', 6.168566942214966]]

results with DATA_HUGEDICT:
---------------------------
Data repr length: 37184

Encoding Test (1000 LOOPS)
[['Package             ', 'Seconds'],
 ['ujson               ', 0.28696608543395996],
 ['json                ', 0.49742913246154785],
 ['cPickle (binary)    ', 0.5122489929199219],
 ['simplejson          ', 0.9091768264770508],
 ['cPickle (ascii)     ', 1.2010438442230225],
 ['pickle (ascii)      ', 8.14183497428894],
 ['pickle (binary)     ', 10.854649066925049]]

Decoding Test (1000 LOOPS)
[['Package             ', 'Seconds'],
 ['ujson               ', 0.4056370258331299],
 ['cPickle (binary)    ', 0.41997385025024414],
 ['simplejson          ', 0.44395899772644043],
 ['cPickle (ascii)     ', 0.71999192237854],
 ['json                ', 1.1725149154663086],
 ['pickle (binary)     ', 4.6916890144348145],
 ['pickle (ascii)      ', 7.210031986236572]]

"""
