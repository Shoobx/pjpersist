import datetime
import pprint
import random


DTIMES = [
    datetime.datetime(2013,1,22,18,59),
    datetime.datetime(1987,2,2,8,31),
    datetime.datetime(1949,6,25,23,50),
    datetime.datetime(1918,3,3,8,35),
    datetime.datetime(1980,7,23,8,6),
    datetime.datetime(2011,11,1,16,26),
    datetime.datetime(1911,1,17,4,24),
    datetime.datetime(1975,7,22,4,44),
    datetime.datetime(1914,5,17,9,37),
    None,
    datetime.datetime(1936,12,16,10,38),
    datetime.datetime(1930,12,12,3,58),
    datetime.datetime(1995,1,23,9,59),
    datetime.datetime(1923,6,2,15,5),
    datetime.datetime(1967,3,1,13,42),
    datetime.datetime(1966,7,22,17,30),
    datetime.datetime(2005,7,13,17,18),
    datetime.datetime(1912,1,9,15,4),
    datetime.datetime(1983,6,27,3,56),
    None,
]

WORDSFILE = '/usr/share/dict/words'
WORDS = [line.strip() for line in open(WORDSFILE, 'r')]

TYPES = ('c', 'dt', 'i', 'b', 'd', 'l')
DEPTH = 0
MAXDEPTH = 5


def get_c():
    key = "'"
    while "'" in key:
        key = random.choice(WORDS)
    return key


def get_dt():
    return random.choice(DTIMES)


def get_i():
    return random.randint(0, 10000)


def get_b():
    return random.choice([True, False])


def get_d(size=5):
    global DEPTH
    DEPTH += 1
    rv = {}
    if DEPTH <= MAXDEPTH:
        for i in xrange(size):
            key = get_c()
            rv[key] = get_random_type()
    DEPTH -= 1
    return rv


def get_l():
    global DEPTH
    DEPTH += 1
    if DEPTH <= MAXDEPTH:
        ln = random.randint(0, 5)
        rv = [get_random_type() for i in xrange(ln)]
    else:
        rv = []
    DEPTH -= 1
    return rv


def get_random_type():
    value_type = random.choice(TYPES)
    getter = globals()['get_%s' % value_type]
    value = getter()
    return value


def main():
    #print '{'

    v = get_d(200)
    pprint.pprint(v)

    #for i in xrange(10):
    #    key = get_c()
    #    value_type = random.choice(TYPES)
    #    getter = globals()['get_%s' % value_type]
    #    value = getter()
    #    print "  '%s': %r," % (key, value)
    #
    #print '}'

if __name__ == '__main__':
    main()
