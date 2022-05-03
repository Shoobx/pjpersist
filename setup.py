"""Setup
"""
import os
from setuptools import setup, find_packages


def read(*rnames):
    with open(os.path.join(os.path.dirname(__file__), *rnames), 'rb') as f:
        return f.read().decode('utf-8')


def alltests():
    import os
    import sys
    import unittest
    # use the zope.testrunner machinery to find all the
    # test suites we've put under ourselves
    import zope.testrunner.find
    import zope.testrunner.options
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
    args = sys.argv[:]
    defaults = ["--test-path", here]
    options = zope.testrunner.options.get_options(args, defaults)
    suites = list(zope.testrunner.find.find_suites(options))
    return unittest.TestSuite(suites)


TESTS_REQUIRE = [
    'zope.testrunner',
    'zope.app.testing',
    'zope.testing',
    'ZODB',
    'mock',
   ]


setup(
    name='pjpersist',
    version='3.0.2',
    author="Shoobx Team",
    author_email="dev@shoobx.com",
    url='https://github.com/Shoobx/pjpersist',
    description="PostgreSQL/JSONB Persistence Backend",
    long_description=(
        read('src', 'pjpersist', 'README.txt')
        + '\n\n' +
        read('CHANGES.rst')
    ),
    license="ZPL 2.1",
    keywords="postgres jsonb persistent",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Framework :: ZODB',
        'License :: OSI Approved :: Zope Public License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
    ],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    data_files=[('pjpersist', ['README.rst'])],  # in order to test it with tox
    extras_require = dict(
        test=TESTS_REQUIRE,
        zope=(
            'zope.container',
        ),
    ),
    install_requires=[
        'future',
        'persistent',
        'transaction',
        'repoze.lru',
        'psycopg2',
        'simplejson',
        'setuptools',
        'sqlobject',
        'zope.dottedname',
        'zope.interface',
        'zope.schema',
        'zope.exceptions >=3.7.1',  # required for extract_stack
    ],
    include_package_data=True,
    zip_safe=False,
    entry_points='''
    [console_scripts]
    profile = pjpersist.tests.performance:main
    json_speed_test = pjpersist.tests.json_speed_test:main
    ''',
    tests_require=TESTS_REQUIRE,
    test_suite='__main__.alltests',
)
