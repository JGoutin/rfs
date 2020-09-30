"""Github object base class"""
from collections import ChainMap
from collections.abc import Mapping
from itertools import chain
from airfs._core.exceptions import (
    ObjectIsADirectoryError,
    ObjectNotASymlinkError,
    ObjectNotADirectoryError,
    ObjectNotFoundError,
)


class GithubObject(Mapping):
    """
    Github Object base class.

    Instances represent headers of an object this a specific spec. Instance are only
    generated by the "head" class-method that act as factory.

    Classes also allow navigating in the virtual file-system tree that represent the
    GitHub repositories.

    Args:
        client (airfs.storage.github._api.ApiV3): Client.
        spec (dict): Object spec.
        headers (dict): Known header values. Missing values will be get lazily from
            parents.
        name (str): Object name, if not already in spec.
    """

    #: Virtual file-system structure starting from this object class
    #: Contains dicts representing virtual folders and other _GithubObject subclasses
    #: that represent objects inside.
    STRUCT = None

    #: The specification "key" that represent this object
    KEY = None

    #: If specified, is a Git reference. True to use KEY value, str value to use a
    #: specific hardcoded value.
    REF = None

    #: API path to get objects of this GitHub class
    GET = None

    #: API path to get objects headers of this GitHub class
    HEAD = None

    #: Head result keys to keep
    HEAD_KEYS = set()

    #: Head result keys to move to dict root.
    #: dict key is key name, dict value is tuple of key path to follow
    HEAD_EXTRA = ()

    #: Keys to head from a parent class, key is key name, value is parent class
    HEAD_FROM = {}

    #: API path to list objects of this GitHub class
    LIST = None

    #: API key of objects names to list
    LIST_KEY = "name"

    #: Symlink like object pointing to the specified absolute path
    SYMLINK = None

    __slots__ = ("_client", "_spec", "_headers", "_header_updated")

    def __init__(self, client, spec, headers=None, name=None):
        self._client = client

        if name is not None:
            spec = spec.copy()
            spec[self.KEY] = name
        self._spec = spec

        if headers is None:
            self._headers = self.head_obj(self._client, self._spec)
            self._header_updated = True
        else:
            self._headers = headers
            self._header_updated = False

    def __getitem__(self, key):
        """
        Get a value from the object header.

        Args:
            key (str): Header key.

        Returns:
            object: Header value matching the key.
        """
        try:
            return self._headers[key]
        except KeyError:
            pass

        try:
            parent = self.HEAD_FROM[key]

        except KeyError:
            self._update_headers()

        else:
            self._update_headers_from_parent(parent)

        return self._headers[key]

    def __iter__(self):
        """
        Iterate over object header keys.

        Yields:
            str: keys
        """
        for key in chain(
            self.HEAD_KEYS, (key for key, _ in self.HEAD_EXTRA), self.HEAD_FROM
        ):
            yield key

    def __len__(self):
        """
        Header length.

        Returns:
            int: Length
        """
        return len(self.HEAD_KEYS) + len(self.HEAD_EXTRA) + len(self.HEAD_FROM)

    def __repr__(self):
        """
        Headers representation. Values that are lazily evaluated and are not yet
        evaluated are replaced by the "<Not evaluated yet>" string.

        Returns:
            str: repr value.
        """
        content = self._headers.copy()
        for key in self:
            content.setdefault(key, "<Not evaluated yet>")
        return repr(content)

    __str__ = __repr__

    def _update_spec_parent_ref(self, parent_key):
        """
        Update the spec with the parent reference.

        Args:
            parent_key (str): The parent key (parent_class.KEY).
        """
        self._update_headers()
        self._spec[parent_key] = self._headers[parent_key]

    def _update_headers(self):
        """
        Ensure current object headers are updated.
        """
        if not self._header_updated:
            headers = self.head_obj(self._client, self._spec)
            self._headers.update(headers)
            self._header_updated = True

    def _update_headers_from_parent(self, parent):
        """
        Ensure current object headers are updated with parent headers.

        Args:
            parent (airfs.storage.github._model_base.GithubObject subclass instance):
                Parent.
        """
        if parent.KEY not in self._spec and parent.KEY is not None:
            self._update_spec_parent_ref(parent.KEY)

        parent_headers = parent.head(self._client, self._spec)
        headers = self._headers
        for key, obj_cls in self.HEAD_FROM.items():
            if obj_cls == parent:
                headers[key] = parent_headers[key]

    @classmethod
    def next_model(cls, client, spec):
        """
        Get next model in the structure.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Partial object spec.

        Returns:
            _Model subclass: model.
        """
        cls = cls._get_cls(client, spec)  # noqa

        if cls.STRUCT is None:
            cls._set_key(spec, "/".join(spec["keys"]))
            spec["keys"].clear()
            spec["object"] = cls
            spec["content"] = cls
            return cls

        cls._update_key(spec)
        try:
            key = spec["keys"].popleft()
        except IndexError:
            spec["object"] = cls
            spec["content"] = cls.STRUCT
            return cls

        model = cls.STRUCT
        while isinstance(model, dict):
            model = cls._get_dict_model(key, model, spec)
            try:
                key = spec["keys"].popleft()
            except IndexError:
                return cls._get_latest_model(model, spec)

        spec["keys"].appendleft(key)
        spec["parent"] = cls
        return model.next_model(client, spec)

    @classmethod
    def _get_dict_model(cls, key, model, spec):
        """
        Get submodel of a dict.

        Args:
            key (str): Model key.
            model (dict): Current model.
            spec (dict): Partial object spec.

        Returns:
            _Model subclass or dict: Next model.
        """
        try:
            return model[key]
        except KeyError:
            raise ObjectNotFoundError(path=spec["full_path"])

    @classmethod
    def _update_key(cls, spec):
        """
        Update key in spec with current model.

        Args:
            spec (dict): Partial object spec.
        """
        if cls.KEY is not None:
            cls._set_key(spec, spec["keys"].popleft())
        elif cls.REF is not None:
            spec["ref"] = cls.REF

    @classmethod
    def _get_latest_model(cls, model, spec):
        """
        Get latest model when no more keys to evaluate.

        Args:
            model (_Model subclass): Current model
            spec (dict): Partial object spec.

        Returns:
            _Model subclass: Latest model.
        """
        if hasattr(model, "KEY") and model.KEY is not None:
            spec["content"] = model
            model = cls
        elif hasattr(model, "STRUCT"):
            spec["content"] = model.STRUCT
        else:
            # Is a dict
            spec["content"] = model
        spec["object"] = model
        return model

    @classmethod
    def _get_cls(cls, client, spec):
        """
        Get object class.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Partial object spec.

        Returns:
            _Model subclass: model.
        """
        return cls

    @classmethod
    def _set_key(cls, spec, value):
        """
        Set "KEY" value, and eventually "ref" value.

        Args:
            spec (dict): Partial object spec.
            value (str): Key value
        """
        spec[cls.KEY] = value
        if cls.REF:
            spec["ref"] = value

    @classmethod
    def list(cls, client, spec, first_level=False):
        """
        List objects of this GitHub class matching the spec.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.
            first_level (bool): It True, returns only first level objects.

        Yields:
            tuple: object name str, object header dict, has content bool
        """
        response = client.get_paged(cls.LIST.format(**spec))

        key = cls.LIST_KEY
        set_header = cls.set_header
        is_dir = cls.STRUCT is not None
        for headers in response:
            name = headers[key]
            yield name, cls(client, spec, set_header(headers), name), is_dir

    @classmethod
    def head_obj(cls, client, spec):
        """
        Head the object of this GitHub class matching the spec.

        Only return result directly from current object response as dict.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            dict: Object headers.
        """
        return cls.set_header(client.get(cls.HEAD.format(**spec))[0])

    @classmethod
    def head(cls, client, spec, headers=None):
        """
        Head the object of this GitHub class matching the spec.

        Returns a dict like object that can retrieve keys from this object response or
        its parents.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.
            headers (dict): Known header values. Missing values will be get lazily from
                parents.

        Returns:
            _GithubObject subclass instance: Object headers.
        """
        return cls(client, spec, headers)

    @classmethod
    def get_url(cls, client, spec):
        """
        Get the URL of the object of this GitHub class matching the spec.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            str: Object URL.
        """
        if cls.GET is None:
            raise ObjectIsADirectoryError(spec["full_path"])
        return cls.GET.format(**spec)

    @classmethod
    def set_header(cls, response):
        """
        Set object header from raw API response.

        Args:
            response (dict): Raw API response.

        Returns:
            dict: Object header.
        """
        head = {key: response[key] for key in (response.keys() & cls.HEAD_KEYS)}

        for key_name, key_path in cls.HEAD_EXTRA:
            value = response
            try:
                for key in key_path:
                    value = value[key]
            except KeyError:
                continue
            head[key_name] = value

        return head

    @classmethod
    def read_link(cls, client, spec):
        """
        Return the path linked by the symbolic link.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            str: Path.
        """
        if cls.SYMLINK is None:
            raise ObjectNotASymlinkError(path=spec["full_path"])

        target = cls.SYMLINK.format(**ChainMap(spec, cls.head(client, spec)))
        content = spec.get("content")
        if isinstance(cls.STRUCT, dict) and not isinstance(content, dict):
            for key, obj_cls in cls.STRUCT.items():
                if content == obj_cls:
                    return f"{target}/{key}"
        return target

    @classmethod
    def _raise_if_not_dir(cls, isdir, spec, client=None):
        """
        Raise exception if not a directory.

        Args:
            isdir (bool): True is a directory.
            spec (dict): Item spec.
            client (airfs.storage.github._api.ApiV3): Client. If present, also checks
                if exists if not a directory.

        Raises:
            airfs._core.exceptions.ObjectNotADirectoryError: Not a directory.
        """
        if not isdir:
            if client:
                # Check if exists
                cls.head_obj(client, spec)
            raise ObjectNotADirectoryError(path=spec["full_path"])
