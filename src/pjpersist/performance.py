##############################################################################
#
# Copyright (c) 2012 Zope Foundation and Contributors.
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
"""PJ Persistence Performance Test"""
from __future__ import absolute_import
import logging
import optparse
import os
import persistent
import psycopg2
import random
import sys
import tempfile
import time
import transaction
import cPickle
import cProfile

from pjpersist import datamanager
from pjpersist import testing
from pjpersist.zope import container

import zope.container
import zope.container.btree
import ZODB
import ZODB.FileStorage

PJLOGGER = logging.getLogger('pjpersist.table')


MULTIPLE_CLASSES = True
PROFILE = False
PROFILE_OUTPUT = '/tmp/cprofile'
LOG_SQL = False
BIGDATA = True


class People(container.AllItemsPJContainer):
    _p_pj_table = 'people'
    _pj_table = 'person'
    _pj_mapping_key = 'name'

class Address(persistent.Persistent):
    _p_pj_table = 'address'

    def __init__(self, city):
        self.city = city

class Person(persistent.Persistent, container.PJContained):
    _p_pj_table = 'person'
    _p_pj_store_type = True

    name = None
    age = None
    address = None
    data = None

    def __init__(self, name, age):
        self.name = name
        self.age = age
        self.address = Address('Boston %i' %age)
        # let's have some data for JSON
        if BIGDATA:
            self.data = BIGDICT

    def __repr__(self):
        return '<%s %s @ %s [%s]>' %(
            self.__class__.__name__, self.name, self.age, self.__name__)

class Person2(Person):
    pass


class PerformanceBase(object):
    personKlass = None
    person2Klass = None
    profile_output = None

    def printResult(self, text, t1, t2, count=None):
        dur = t2-t1
        text += ':'
        ops = ''
        if count:
            ops = "%d ops/second" % (count / dur)

        print '%-25s %.4f secs %s' % (text, dur, ops)

        PJLOGGER.debug('=========== done: %s', text)

    def insertPeople(self, options):
        pass

    def getPeople(self, options):
        pass

    def slow_read(self, people, peopleCnt):
        # Profile slow read
        transaction.begin()
        t1 = time.time()
        if PROFILE:
            cProfile.runctx(
                '[people[name].name for name in people]', globals(), locals(),
                filename=self.profile_output+'_slow_read')
        else:
            [people[name].name for name in people]
        t2 = time.time()
        transaction.commit()
        self.printResult('Slow Read', t1, t2, peopleCnt)

    def read_list(self, people, peopleCnt):
        # Profile fast read (values)
        transaction.begin()
        t1 = time.time()
        if PROFILE:
            cProfile.runctx(
                '[p for p in list(people)]', globals(), locals(),
                filename=self.profile_output+'_read_list')
        else:
            [p for p in list(people)]
        t2 = time.time()
        transaction.commit()
        self.printResult('Read (list)', t1, t2, peopleCnt)

    def read_list_values(self, people, peopleCnt):
        # Profile fast read (values)
        transaction.begin()
        t1 = time.time()
        if PROFILE:
            cProfile.runctx(
                '[p for p in list(people.values())]', globals(), locals(),
                filename=self.profile_output+'_read_list_values')
        else:
            [p for p in list(people.values())]
        t2 = time.time()
        transaction.commit()
        self.printResult('Read (list.values)', t1, t2, peopleCnt)

    def fast_read_values(self, people, peopleCnt):
        # Profile fast read (values)
        transaction.begin()
        t1 = time.time()
        if PROFILE:
            cProfile.runctx(
                '[person.name for person in people.values()]', globals(), locals(),
                filename=self.profile_output+'_fast_read_values')
        else:
            [person.name for person in people.values()]
        t2 = time.time()
        transaction.commit()
        self.printResult('Fast Read (values)', t1, t2, peopleCnt)

    def fast_read(self, people, peopleCnt):
        # Profile fast read
        transaction.begin()
        t1 = time.time()
        if PROFILE:
            cProfile.runctx(
                '[person.name for person in people.find()]', globals(), locals(),
                filename=self.profile_output+'_fast_read')
        else:
            [person.name for person in people.find()]
        t2 = time.time()
        transaction.commit()
        self.printResult('Fast Read (find)', t1, t2, peopleCnt)

    def object_caching(self, people, peopleCnt):
        # Profile object caching
        transaction.begin()
        # cache warmup
        [person.name for person in people.values()]
        t1 = time.time()
        [person.name for person in people.values()]
        #cProfile.runctx(
        #    '[person.name for person in people.values()]', globals(), locals())
        t2 = time.time()
        transaction.commit()
        self.printResult('Fast Read (caching x2)', t1, t2, peopleCnt*2)

        transaction.begin()
        # cache warmup
        [person.name for person in people.values()]
        t1 = time.time()
        [person.name for person in people.values()]
        [person.name for person in people.values()]
        #cProfile.runctx(
        #    '[person.name for person in people.values()]', globals(), locals())
        t2 = time.time()
        transaction.commit()
        self.printResult('Fast Read (caching x3)', t1, t2, peopleCnt*3)

    def modify(self, people, peopleCnt):
        # Profile modification
        t1 = time.time()
        def modify():
            for person in list(people.values()):
                person.name += 'X'
                person.age += 1
            transaction.commit()
        if PROFILE:
            cProfile.runctx(
                'modify()', globals(), locals(),
                filename=self.profile_output+'_modify')
        else:
            modify()
        t2 = time.time()
        self.printResult('Modification', t1, t2, peopleCnt)

    def delete(self, people, peopleCnt):
        # Profile deletion
        t1 = time.time()
        for name in people.keys():
            if PROFILE:
                cProfile.runctx(
                    'del people[name]', globals(), locals(),
                    filename=self.profile_output+'_delete')
            else:
                del people[name]
        transaction.commit()
        t2 = time.time()
        self.printResult('Deletion', t1, t2, peopleCnt)

    def run_basic_crud(self, options):
        people = self.insertPeople(options)

        peopleCnt = len(people)

        people = self.getPeople(options)
        self.slow_read(people, peopleCnt)

        people = self.getPeople(options)
        self.read_list(people, peopleCnt)

        people = self.getPeople(options)
        self.read_list_values(people, peopleCnt)

        people = self.getPeople(options)
        self.fast_read_values(people, peopleCnt)

        people = self.getPeople(options)
        self.fast_read(people, peopleCnt)

        people = self.getPeople(options)
        self.object_caching(people, peopleCnt)

        if options.modify:
            people = self.getPeople(options)
            self.modify(people, peopleCnt)

        if options.delete:
            people = self.getPeople(options)
            self.delete(people, peopleCnt)


def getConnection(database=None):
    return psycopg2.connect(
        database=database or 'template1',
        host='localhost', port=5432,
        user='pjpersist', password='pjpersist')


class PerformancePJ(PerformanceBase):
    personKlass = Person
    person2Klass = Person2

    profile_output = PROFILE_OUTPUT + '_pj_'

    def insertPeople(self, options):
        if options.reload:
            connroot = getConnection()
            with connroot.cursor() as cur:
                cur.execute('END;')
                cur.execute('DROP DATABASE IF EXISTS performance;')
                cur.execute('CREATE DATABASE performance;')
            connroot.commit()

            datamanager.PJ_AUTO_CREATE_TABLES = False
            if LOG_SQL:
                testing.log_sql_to_file('/tmp/pjpersist.table.log')

            conn = getConnection('performance')

            dm = datamanager.PJDataManager(conn)

            dm.create_tables(('people', 'person', 'address'))
            dm.root._init_table()
            dm._new_obj_cache._ensure_db_objects()

            # this speeds up slow_read around TWICE
            #with conn.cursor() as cur:
            #    cur.execute('END;')
            #    cur.execute(
            #        "CREATE INDEX data_name ON person ((data->>('name')));")

            dm.root['people'] = people = People()
            transaction.commit()

            def insert():
                for idx in xrange(options.size):
                    klass = (self.personKlass if (MULTIPLE_CLASSES and idx % 2)
                             else self.person2Klass)
                    people[None] = klass('Mr Number %.5i' % idx,
                                         random.randint(0, 100))

            # Profile inserts
            t1 = time.time()
            if PROFILE:
                cProfile.runctx(
                    'insert()', globals(), locals(),
                    filename=self.profile_output+'_insert')
            else:
                insert()
            transaction.commit()
            t2 = time.time()
            self.printResult('Insert', t1, t2, options.size)
        else:
            people = dm.root['people']

        return people

    def getPeople(self, options):
        conn = getConnection('performance')

        dm = datamanager.PJDataManager(conn)
        people = dm.root['people']
        return people


class PeopleZ(zope.container.btree.BTreeContainer):
    pass

class AddressZ(persistent.Persistent):

    def __init__(self, city):
        self.city = city

class PersonZ(persistent.Persistent, zope.container.contained.Contained):

    def __init__(self, name, age):
        self.name = name
        self.age = age
        self.address = AddressZ('Boston %i' %age)

    def __repr__(self):
        return '<%s %s @ %i [%s]>' %(
            self.__class__.__name__, self.name, self.age, self.__name__)

class Person2Z(Person):
    pass


class PerformanceZODB(PerformanceBase):
    personKlass = PersonZ
    person2Klass = Person2Z

    profile_output = PROFILE_OUTPUT + '_zodb_'

    def insertPeople(self, options):
        folder = tempfile.gettempdir()
        #folder = './'  # my /tmp is a tmpfs
        fname = os.path.join(folder, 'performance_data.fs')
        if options.reload:
            try:
                os.remove(fname)
            except:
                pass
        fs = ZODB.FileStorage.FileStorage(fname)
        self.db = ZODB.DB(fs)
        conn = self.db.open()

        root = conn.root()

        if options.reload:
            root['people'] = people = PeopleZ()
            transaction.commit()

            # Profile inserts
            transaction.begin()
            t1 = time.time()
            for idx in xrange(options.size):
                klass = (self.personKlass if (MULTIPLE_CLASSES and idx % 2)
                         else self.person2Klass)
                name = 'Mr Number %.5i' % idx
                people[name] = klass(name, random.randint(0, 100))
            transaction.commit()
            t2 = time.time()
            self.printResult('Insert', t1, t2, options.size)
        else:
            people = root['people']

        return people

    def getPeople(self, options):
        conn = self.db.open()

        root = conn.root()
        people = root['people']

        return people

    def fast_read(self, people, peopleCnt):
        pass


parser = optparse.OptionParser()
parser.usage = '%prog [options]'

parser.add_option(
    '-s', '--size', action='store', type='int',
    dest='size', default=1000,
    help='The amount of objects to use.')

parser.add_option(
    '--no-reload', action='store_false',
    dest='reload', default=True,
    help='A flag, when set, causes the DB not to be reloaded.')

parser.add_option(
    '--no-modify', action='store_false',
    dest='modify', default=True,
    help='A flag, when set, causes the data not to be modified.')

parser.add_option(
    '--no-delete', action='store_false',
    dest='delete', default=True,
    help='A flag, when set, causes the data not to be deleted at the end.')


def main(args=None):
    # Parse command line options.
    if args is None:
        args = sys.argv[1:]
    options, args = parser.parse_args(args)

    print 'PJ ---------------'
    PerformancePJ().run_basic_crud(options)
    print 'ZODB  ---------------'
    PerformanceZODB().run_basic_crud(options)


import datetime
BIGDICT = {'Alcestis': 'mantilla',
 'arraignments': True,
 'bosh': 6909,
 'chant': 6785,
 'garbanzo': {'Armenian': True,
              'benign': {'easygoing': {'basted': 'counterpoint',
                                       'nonpolluting': 'Gretchen',
                                       'ointment': {'Talleyrand': False,
                                                    'comparably': 'hedgehog',
                                                    'goiter': 6895,
                                                    'medalist': {},
                                                    'pinked': False},
                                       'replication': datetime.datetime(1918, 3, 3, 8, 35),
                                       'ripsaw': 4316},
                         'interaction': datetime.datetime(1980, 7, 23, 8, 6),
                         'renaissances': datetime.datetime(2013, 1, 22, 18, 59),
                         'revision': True,
                         'substantiates': {'Pepsi': True,
                                           'affords': 5854,
                                           'buckskins': 'legalize',
                                           'syphilis': False,
                                           'underdeveloped': True}},
              'pennants': {'armadillo': {'Condillac': 'Equuleus',
                                         'Orly': datetime.datetime(1911, 1, 17, 4, 24),
                                         'civvies': 9109,
                                         'hilly': datetime.datetime(2013, 1, 22, 18, 59),
                                         'nurture': 1718},
                           'comers': 322,
                           'furtherance': {'Brahe': datetime.datetime(1980, 7, 23, 8, 6),
                                           'Whitehead': False,
                                           'joysticks': {'drinker': 6444,
                                                         'gamed': 'hosing',
                                                         'larkspur': 3430,
                                                         'prepaid': 'unspoiled',
                                                         'stockpile': datetime.datetime(1923, 6, 2, 15, 5)},
                                           'snarls': 'meditates',
                                           'studding': {'Botticelli': 8214,
                                                        'Uruguayans': 830,
                                                        'illicitness': 7397,
                                                        'rosin': False,
                                                        'underskirts': False}},
                           'immodestly': 4678,
                           'kleptomania': 'pounced'},
              'sachet': {'bankrolls': True,
                         'breeding': 9051,
                         'failure': datetime.datetime(1975, 7, 22, 4, 44),
                         'imposed': 'avenged',
                         'undeceived': {'festal': 3225,
                                        'intermezzi': 1484,
                                        'poor': False,
                                        'reprinted': datetime.datetime(1918, 3, 3, 8, 35),
                                        'sleepwalkers': 'embarrassing'}},
              'tryst': True},
 'inaugural': {'Horacio': datetime.datetime(1923, 6, 2, 15, 5),
               'Utopians': True,
               'chimeras': datetime.datetime(1967, 3, 1, 13, 42),
               'domed': 3535,
               'member': False},
 'lava': 'Domingo',
 'potash': 7166,
 'spoils': False,
 'subteens': False}
