=======
CHANGES
=======


2.0.1 (2020-10-13)
------------------

- Fixed persisting tuple keyed dicts. Persisting such objects worked,
  but reading failed.


2.0.0 (2020-06-02)
------------------

- Drop Python 2.7 and 3.6 support, add 3.8.

- Remove buildout support.

- Support for nested flushing. In complex use cases it can happen that during
  serialization of an object, a query is made to look up another object. That
  in turn causes a flush, resulting in a flush inside a flush. The `flush()`
  method did not expect that behavior and failed if the inner flush would
  flush objects that the outer flush had already handled.


1.7.2 (2020-02-10)
------------------

- Optimization: do not dig in `data` when we have a native field for
  `_pj_mapping_key`, should allow creating indexes for lookup


1.7.1 (2019-06-19)
------------------

- Fixed an edge case when the serializer gets a mapping with a key `dict_data`.
  Reading such object failed.

- Fixed an edge case with the serializer, when an object's state living
  in a persistent object became 'empty'. Basically the state was just
  `{'_py_persistent_type': 'SomeClass'}`
  `SomeClass.__setstate__` was not called, thus the object could miss
  attributes. Like a subclass of `UserDict` would miss the `data` attribute.

- Removed checking for 0x00 chars in dict keys. Turns out PostGreSQL just
  can not store 0x00.

1.7.0 (2019-05-29)
------------------

- Support for sub-second datetime and time resolution during serialization.

- Add `use_cache` argument to `PJContainer._load_one()` to support ignoring
  the cache. (This became handy if a container keeps track of multiple
  versions of an item and you try to load all old revisions.)


1.6.0 (2019-05-29)
------------------

- Make `id` and `data` column name configurable via `_pj_id_column` and
  `_pj_data_column` attributes in `PJContainer`, respectively.

- Auto-assign a name to objects when using `PJContainer`, not just
  `IdNamesPJContainer`.


1.5.0 (2018-10-10)
------------------

- Support for Python 3.7. Removed Python 3.5 testing from tox.


1.4.1 (2018-09-13)
------------------

- No need to log in tpc_finish.


1.4.0 (2018-09-13)
------------------

- Implemented skipping tpc_prepare when DM has no writes.
  We found out that AWS Aurora is dog slow at the moment on tpc_prepare.
  When the DataManager has no writes, there's no need to call tpc_prepare.
  See `CALL_TPC_PREPARE_ON_NO_WRITE_TRANSACTION`, by default True for backwards
  compatibility.

- Added ability to log whether the transaction had writes.
  See `LOG_READ_WRITE_TRANSACTION`, by default False


1.3.2 (2018-04-19)
------------------

- More precise flushing of datamanager to avoid unnecessary database
  writes.


1.3.1 (2018-04-11)
------------------

- Enabled concurrent adds to IdNamesPJContainer by eliminating a query
  that was causing transaction conflicts.

1.3.0 (2018-03-22)
------------------

- Python 3 compatibility fixes
- More efficient PJContainer.values() implementation


1.2.2 (2017-12-12)
------------------

- Need to protect all DB calls against `DatabaseDisconnected`


1.2.1 (2017-12-12)
------------------

- `psycopg2.OperationalError` and `psycopg2.InterfaceError` will be caught
  on SQL command execution and reraised as `DatabaseDisconnected`


1.2.0 (2017-10-24)
------------------

- Added a new helper function to link subobject to main doc object. This is
  needed when a custom `__getstate__()` and `__setstate__()` is implemented. A
  detailed example is provided.

- Implemented `flush_hint` argument for `IDataManager.execute()` to allow
  flushing only some objects during query. `flush_hints` is a list table names
  that need to be flushed for the query to return a correct result.

- The Zope-specific containers use the `flush_hint` to only flush objects they
  manage when a query is run on the container.

- While flushing objects, every main document object is now only flushed
  once. Before that fix, any subobject would cause its doc object to be dumped
  again.

Note: These optimizations provide a 15% performance improvements in real-world
applications.


1.1.2 (2017-09-14)
------------------

- Make sure changed objects aren't `_p_changed` anymore after commit.


1.1.1 (2017-07-03)
------------------

- Nothing changed yet.


1.0.0 (2017-03-18)
------------------

- Initial Public Release

- Project forked from mongopersist to work with PostGreSQL and JSONB data
  type. The main motiviation is the ability to utilize PostGreSQL's great
  transactional support.

