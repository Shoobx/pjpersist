"""Setup
"""
import os
from setuptools import setup, find_packages


def read(*rnames):
    text = open(os.path.join(os.path.dirname(__file__), *rnames)).read()
    return unicode(text, 'utf-8').encode('ascii', 'xmlcharrefreplace')


setup(
    name='pjpersist',
    version='1.0.0',
    author="Shoobx Team",
    author_email="dev@shoobx.com",
    url='https://github.com/Shoobx/pjpersist',
    description="PostgreSQL/JSONB Persistence Backend",
    long_description=(
        read('src', 'pjpersist', 'README.txt')
        + '\n\n' +
        read('CHANGES.txt')
    ),
    license="ZPL 2.1",
    keywords="postgres jsonb persistent",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Framework :: ZODB',
        'License :: OSI Approved :: Zope Public License',
        'Natural Language :: English',
        'Operating System :: OS Independent'],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    extras_require = dict(
        test=(
            'zope.app.testing',
            'zope.testing',
            'ZODB3',
            'mock'
        ),
        zope=(
            'zope.container',
        ),
    ),
    install_requires=[
        'persistent',
        'transaction >=1.1.0',
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
)
