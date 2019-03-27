# coding=utf-8
"""Test pycosio.storage"""
from io import UnsupportedOperation as _UnsupportedOperation
from os import urandom as _os_urandom
from time import time as _time
from uuid import uuid4 as _uuid

import pytest as _pytest


def _urandom(size):
    """
    Return random generated bytes. But avoid to generate Null chars.

    Args:
        size (int):

    Returns:
        bytes: Generated bytes.
    """
    return _os_urandom(size).replace(b'\0', b'\x01')


class StorageTester:
    """
    Class that contain common set of tests for storage.

    Args:
        system (pycosio._core.io_system.SystemBase instance):
            System to test.
        raw_io (pycosio._core.io_raw.ObjectRawIOBase subclass):
            Raw IO class.
        buffered_io (pycosio._core.io_buffered.ObjectBufferedIOBase subclass):
            Buffered IO class.
        storage_mock (tests.storage_mock.ObjectStorageMock instance):
            Storage mock in use, if any.
        storage_info (dict): Storage information from pycosio.mount.
    """

    def __init__(self, system=None, raw_io=None, buffered_io=None,
                 storage_mock=None, unsupported_operations=None,
                 storage_info=None, system_parameters=None, root=None):

        if system is None:
            system = storage_info['system_cached']
        if raw_io is None:
            raw_io = storage_info['raw']
        if buffered_io is None:
            buffered_io = storage_info['buffered']
        if system_parameters is None and storage_info:
            system_parameters = storage_info['system_parameters']

        self._system_parameters = system_parameters or dict()
        self._system = system
        self._raw_io = raw_io
        self._buffered_io = buffered_io
        self._storage_mock = storage_mock
        self._unsupported_operations = unsupported_operations or tuple()

        # Get storage root
        if not root:
            root = system.roots[0]

        # Defines randomized names for locator and objects
        self.locator = self._get_id()
        self.locator_url = '/'.join((root, self.locator))
        self.base_dir_name = '%s/' % self._get_id()
        self.base_dir_path = '%s/%s' % (self.locator, self.base_dir_name)
        self.base_dir_url = root + self.base_dir_path

        # Run test sequence
        self._objects = set()
        self._to_clean = self._objects.add

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        from pycosio._core.exceptions import ObjectNotFoundError

        # Remove objects, and once empty the locator
        for obj in reversed(sorted(self._objects, key=str.lower)):
            self._objects.discard(obj)
            try:
                self._system.remove(obj, relative=True)
            except (ObjectNotFoundError, _UnsupportedOperation):
                continue

    def test_common(self):
        """
        Common set of tests
        """
        self._test_system_locator()
        self._test_system_objects()
        self._test_raw_io()
        self._test_buffered_io()
        # TODO: Add pycosio public functions tests

        # Only if mocked
        if self._storage_mock is not None:
            self._test_mock_only()

    def _is_supported(self, feature):
        """
        Return True if a feature is supported.

        Args:
            feature (str): Feature to support.

        Returns:
            bool: Feature is supported.
        """
        return feature not in self._unsupported_operations

    @staticmethod
    def _get_id():
        """
        Return an unique ID.

        Returns:
            str: id
        """
        return 'pycosio%s' % (str(_uuid()).replace('-', ''))

    def _test_raw_io(self):
        """
        Tests raw IO.
        """
        # TODO: Add: modes tests('a', 'x'), Random write access test.

        from os import SEEK_END

        size = 100
        file_name = 'raw_file0.dat'
        file_path = self.base_dir_path + file_name
        self._to_clean(file_path)
        content = _urandom(size)

        # Open file in write mode
        if self._is_supported('write'):
            file = self._raw_io(file_path, 'wb', **self._system_parameters)
            try:
                # Test: Write
                file.write(content)

                # Test: tell
                is_seekable = file.seekable()
                if is_seekable:
                    assert file.tell() == size,\
                        'Raw write, tell match writen size'
                else:
                    with _pytest.raises(_UnsupportedOperation):
                        file.tell()

                # Test: _flush
                file.flush()

            finally:
                file.close()

        else:
            is_seekable = False

            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                self._raw_io(file_path, 'wb', **self._system_parameters)

            # Create pre-existing file
            if self._storage_mock:
                self._storage_mock.put_object(
                    self.locator, self.base_dir_name + file_name, content)

        # Open file in read mode
        with self._raw_io(file_path, **self._system_parameters) as file:
            # Test: _read_all
            assert file.readall() == content, 'Raw read all, content match'
            assert file.tell() == size, 'Raw read all, tell match'

            assert file.seek(10) == 10, 'Raw seek 10 & read all, seek match'
            assert file.readall() == content[10:],\
                'Raw seek 10 & read all, content match'
            assert file.tell() == size,\
                'Raw seek 10 & read all, tell match'

            # Test: _read_range
            assert file.seek(0) == 0, 'Raw seek 0, seek match'
            buffer = bytearray(40)
            assert file.readinto(buffer) == 40,\
                'Raw read into, returned size match'
            assert bytes(buffer) == content[:40], 'Raw read into, content match'
            assert file.tell() == 40, 'Raw read into, tell match'

            buffer = bytearray(40)
            assert file.readinto(buffer) == 40,\
                'Raw read into from 40, returned size match'
            assert bytes(buffer) == content[40:80],\
                'Raw read into from 40, content match'
            assert file.tell() == 80, 'Raw read into from 40, tell match'

            buffer = bytearray(40)
            assert file.readinto(buffer) == 20,\
                'Raw read into partially over EOF, returned size match'
            assert bytes(buffer) == content[80:] + b'\0' * 20,\
                'Raw read into partially over EOF, content match'
            assert file.tell() == size,\
                'Raw read into partially over EOF, tell match'

            buffer = bytearray(40)
            assert file.readinto(buffer) == 0,\
                'Raw read into over EOF, returned size match'
            assert bytes(buffer) == b'\0' * 40,\
                'Raw read into over EOF, content match'
            assert file.tell() == size,\
                'Raw read into over EOF, tell match'

            file.seek(-10, SEEK_END)
            buffer = bytearray(20)
            assert file.readinto(buffer) == 10,\
                'Raw seek from end & read into, returned size match'
            assert bytes(buffer) == content[90:] + b'\0' * 10,\
                'Raw seek from end & read into, content match'
            assert file.tell() == size,\
                'Raw seek from end & read into, tell match'

        # Test: Append mode correctly append data
        if self._is_supported('write'):
            with self._raw_io(file_path, mode='ab',
                              **self._system_parameters) as file:
                file.write(content)

            with self._raw_io(file_path, **self._system_parameters) as file:
                assert file.readall() == content + content,\
                    'Raw append, previous content read'

        # Test: Seek out of file and write
        if is_seekable:
            with self._raw_io(file_path, 'wb',
                              **self._system_parameters) as file:
                file.seek(256)
                file.write(b'\x01')

            with self._raw_io(file_path, 'rb',
                              **self._system_parameters) as file:
                assert file.readall() == b'\0' * 256 + b'\x01',\
                    'Raw seek, null padding read'

    def _test_buffered_io(self):
        """
        Tests buffered IO.
        """
        # Set buffer size
        minimum_buffer_zize = 16 * 1024
        buffer_size = self._buffered_io.MINIMUM_BUFFER_SIZE
        if buffer_size < minimum_buffer_zize:
            buffer_size = minimum_buffer_zize

        # Test: write data, not multiple of buffer
        file_name = 'buffered_file0.dat'
        file_path = self.base_dir_path + file_name
        self._to_clean(file_path)
        size = int(4.5 * buffer_size)
        content = _urandom(size)

        if self._is_supported('write'):
            with self._buffered_io(file_path, 'wb', buffer_size=buffer_size,
                                   **self._system_parameters) as file:
                file.write(content)
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                self._buffered_io(file_path, 'wb', buffer_size=buffer_size,
                                  **self._system_parameters)

            # Create pre-existing file
            if self._storage_mock:
                self._storage_mock.put_object(
                    self.locator, self.base_dir_name + file_name, content)

        # Test: Read data, not multiple of buffer
        with self._buffered_io(file_path, 'rb', buffer_size=buffer_size,
                               **self._system_parameters) as file:
            assert content == file.read(),\
                'Buffered read, not multiple of buffer size'

        # Test: write data, multiple of buffer
        file_name = 'buffered_file1.dat'
        file_path = self.base_dir_path + file_name
        self._to_clean(file_path)
        size = int(5 * buffer_size)
        content = _urandom(size)

        if self._is_supported('write'):
            with self._buffered_io(file_path, 'wb', buffer_size=buffer_size,
                                   **self._system_parameters) as file:
                file.write(content)
        else:
            # Create pre-existing file
            if self._storage_mock:
                self._storage_mock.put_object(
                    self.locator, self.base_dir_name + file_name, content)

        # Test: Read data, multiple of buffer
        with self._buffered_io(file_path, 'rb', buffer_size=buffer_size,
                               **self._system_parameters) as file:
            assert content == file.read(),\
                'Buffered read, multiple of buffer size'

    def _test_system_locator(self):
        """
        Test system internals related to locators.
        """
        system = self._system

        # Test: Create locator
        if self._is_supported('mkdir'):
            system.make_dir(self.locator_url)
            self._to_clean(self.locator)
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                system.make_dir(self.locator_url)

            # Create a preexisting locator
            if self._storage_mock:
                self._storage_mock.put_locator(self.locator)

        # Test: Check locator listed
        if self._is_supported('listdir'):
            for name, header in system._list_locators():
                if name == self.locator and isinstance(header, dict):
                    break
            else:
                _pytest.fail('Locator "%s" not found' % self.locator)

            # Test: Check locator header return a mapping
            assert hasattr(system.head(path=self.locator), '__getitem__'), \
                'List locators, header is mapping'
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                system._list_locators()

        # Test: remove locator
        tmp_locator = self._get_id()
        self._to_clean(tmp_locator)
        if self._is_supported('mkdir'):
            system.make_dir(tmp_locator)
        elif self._storage_mock:
            self._storage_mock.put_locator(tmp_locator)

        if self._is_supported('remove'):
            if self._is_supported('listdir'):
                assert tmp_locator in [
                    name for name, _ in system._list_locators()],\
                    'Remove locator, locator exists'

            system.remove(tmp_locator)

            if self._is_supported('listdir'):
                assert tmp_locator not in [
                    name for name, _ in system._list_locators()],\
                    'Remove locator, locator not exists'
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                system.remove(tmp_locator)

    def _test_system_objects(self):
        """
        Test system internals related to objects.
        """
        from pycosio._core.exceptions import ObjectNotFoundError

        system = self._system

        if self._is_supported('mkdir'):
            # Create parent directory
            system.make_dir(self.base_dir_path)
            self._to_clean(self.base_dir_path)

            # Test: Make a directory (With trailing /)
            dir_name0 = 'directory0/'
            dir_path0 = self.base_dir_path + dir_name0
            system.make_dir(dir_path0)
            self._to_clean(dir_path0)
            if self._is_supported('listdir'):
                assert dir_path0 in self._list_objects_names(), \
                    'Create directory, exists (with "/")'

            # Test: Make a directory (Without trailing /)
            dir_name1 = 'directory1'
            dir_path1 = self.base_dir_path + dir_name1
            system.make_dir(dir_path1)
            dir_path1 += '/'
            self._to_clean(dir_path1)

            if self._is_supported('listdir'):
                assert dir_path1 in self._list_objects_names(), \
                    'Create directory, exists (without "/")'

                # Test: Listing empty directory
                assert len(tuple(system.list_objects(dir_path0))) == 0, \
                    'List objects, empty directory'

        # Write a sample file
        file_name = 'sample_1K.dat'
        file_path = self.base_dir_path + file_name
        self._to_clean(file_path)
        file_url = self.base_dir_url + file_name
        size = 1024
        content = _urandom(size)

        if self._is_supported('write'):
            with self._raw_io(file_path, mode='w',
                              **self._system_parameters) as file:
                # Write content
                file.write(content)

        elif self._storage_mock:
            # Create pre-existing file
            self._storage_mock.put_object(
                self.locator, self.base_dir_name + file_name, content)

        # Estimate creation time
        create_time = _time()

        # Test: Check file header
        assert hasattr(system.head(path=file_path), '__getitem__'), \
            'Head file, header is mapping'

        # Test: Check file size
        try:
            assert system.getsize(file_path) == size, \
                'Head file, size match'
        except _UnsupportedOperation:
            # May not be supported on all files, if supported
            if self._is_supported('getsize'):
                raise

        # Test: Check file modification time
        try:
            file_time = system.getmtime(file_path)
            if self._is_supported('write'):
                assert file_time == _pytest.approx(create_time, 2), \
                    'Head file, modification time match'
        except _UnsupportedOperation:
            # May not be supported on all files, if supported
            if self._is_supported('getmtime'):
                raise

        # Test: Check file creation time
        try:
            file_time = system.getctime(file_path)
            if self._is_supported('write'):
                assert file_time == _pytest.approx(create_time, 2), \
                    'Head file, creation time match'
        except _UnsupportedOperation:
            # May not be supported on all files, if supported
            if self._is_supported('getctime'):
                raise

        # Test: Check path and URL handling
        with self._raw_io(file_path, **self._system_parameters) as file:
            assert file.name == file_path, 'Open file, path match'

        with self._raw_io(file_url, **self._system_parameters) as file:
            assert file.name == file_url, 'Open file, URL match'

        # Write some files
        files = set()
        files.add(file_path)
        for i in range(10):
            file_name = 'file%d.dat' % i
            path = self.base_dir_path + file_name
            files.add(path)
            self._to_clean(path)
            if self._is_supported('write'):
                with self._raw_io(
                        path, mode='w', **self._system_parameters) as file:
                    file.flush()
            elif self._storage_mock:
                # Create pre-existing file
                self._storage_mock.put_object(
                    self.locator, self.base_dir_name + file_name, b'')

        # Test: List objects
        if self._is_supported('listdir'):
            objects = tuple(system.list_objects(self.locator))
            objects_list = set(
                '%s/%s' % (self.locator, name) for name, _ in objects)
            for file in files:
                assert file in objects_list, 'List objects, file name match'
            for _, header in objects:
                assert hasattr(header, '__getitem__'),\
                    'List objects, file header is mapping'

            # Test: List objects, with limited output
            max_request_entries = 5
            entries = len(tuple(system.list_objects(
                max_request_entries=max_request_entries)))
            assert entries == max_request_entries, \
                'List objects, Number of entries match'

            # Test: List objects, no objects found
            with _pytest.raises(ObjectNotFoundError):
                list(system.list_objects(
                    self.base_dir_path + 'dir_not_exists/'))

            # Test: List objects on locator root, no objects found
            with _pytest.raises(ObjectNotFoundError):
                list(system.list_objects(self.locator + '/dir_not_exists/'))

            # Test: List objects, locator not found
            with _pytest.raises(ObjectNotFoundError):
                list(system.list_objects(self._get_id()))

        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                list(system.list_objects(self.base_dir_path))

        # Test: copy
        copy_path = file_path + '.copy'
        self._to_clean(copy_path)
        if self._is_supported('copy'):
            system.copy(file_path, copy_path)
            assert system.getsize(copy_path) == size, 'Copy file, size match'
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                system.copy(file_path, copy_path)

        # Test: Normal file is not symlink
        assert not system.islink(file_path), 'Symlink, file is not symlink'

        # Test: Symlink
        if self._is_supported('symlink'):
            link_path = self.base_dir_path + 'symlink'
            # TODO: Tests once create symlink implemented

            # Test: Is symlink
            #assert system.islink(link_path)
            #assert system.islink(header=system.head(link_path)

        # Test: Remove file
        if self._is_supported('remove'):
            if self._is_supported('listdir'):
                assert file_path in self._list_objects_names(), \
                    'Remove file, file exists'
            system.remove(file_path)
            if self._is_supported('listdir'):
                assert file_path not in self._list_objects_names(), \
                    'Remove file, file not exists'
        else:
            # Test: Unsupported
            with _pytest.raises(_UnsupportedOperation):
                system.remove(file_path)

    def _test_mock_only(self):
        """
        Tests that can only be performed on mocks
        """
        file_name = 'mocked.dat'

        # Create a file
        file_path = self.base_dir_path + file_name
        self._to_clean(file_path)
        content = _urandom(20)

        if self._is_supported('write'):
            with self._raw_io(
                    file_path, mode='w', **self._system_parameters) as file:
                file.write(content)
                file.flush()
        elif self._storage_mock:
            # Create pre-existing file
            self._storage_mock.put_object(
                self.locator, self.base_dir_name + file_name, content)

        # Test: Read not block other exceptions
        with self._storage_mock.raise_server_error():
            with _pytest.raises(self._storage_mock.base_exception):
                self._raw_io(file_path, **self._system_parameters).read(10)

    def _list_objects_names(self):
        """
        List objects names.

        Returns:
            set of str: objects names.
        """
        return set('%s/%s' % (self.locator, name)
                   for name, _ in self._system.list_objects(self.locator))


def test_user_storage(storage_test_kwargs):
    """
    Test specified storage.

    Test cases are automatically generated base on user configuration,
    see "tests.conftest.pytest_generate_tests"

    Args:
        storage_test_kwargs (dict): Storage test keyword arguments.
    """
    # Get list of unsupported operations
    from importlib import import_module
    module = import_module('tests.test_storage_%s' %
                           storage_test_kwargs['storage_info']['storage'])
    try:
        unsupported_operations = module.UNSUPPORTED_OPERATIONS
    except AttributeError:
        unsupported_operations = None

    # Run tests
    with StorageTester(
            unsupported_operations=unsupported_operations,
            **storage_test_kwargs) as tester:
        tester.test_common()
