"""GitHub releases related objects"""
from airfs._core.exceptions import ObjectNotFoundError
from airfs.storage.github._model_archive import Archive
from airfs.storage.github._model_git import Commit, Tag, Tree
from airfs.storage.github._model_base import GithubObject


class ReleaseAsset(GithubObject):
    """GitHub release asset"""

    KEY = "asset"
    GET = "https://github.com/{owner}/{repo}/releases/download/{tag}/{asset}"
    HEAD_KEYS = {"size", "download_count", "created_at", "updated_at", "content_type"}
    HEAD_FROM = {"sha": Tag}

    @classmethod
    def list(cls, client, spec):
        """
        List assets of a release.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            generator of tuple: object name str, object header dict, directory bool
        """
        cls._raise_if_not_dir(spec.get("asset"), spec)

        for asset in cls._parent_release(client, spec)["assets"]:
            name = asset["name"]
            yield name, cls(client, spec, cls.set_header(asset), name), False

    @classmethod
    def head_obj(cls, client, spec):
        """
        Get asset headers.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            dict: Object headers.
        """
        name = spec["asset"]
        for asset in cls._parent_release(client, spec)["assets"]:
            if asset["name"] == name:
                return cls.set_header(asset)

        raise ObjectNotFoundError("No such file or directory: '%s'" % spec["full_path"])

    @classmethod
    def get_url(cls, client, spec):
        """
        Get asset URL.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            str: Object headers.
        """
        if "tag" not in spec:
            spec["tag"] = cls._parent_release(client, spec)["tag_name"]
        return cls.GET.format(spec)

    @classmethod
    def _parent_release(cls, client, spec):
        """
        Get the parent release

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            dict: Release raw headers.
        """
        return client.get(Release.HEAD.format(**spec))[0]


class ReleaseArchive(Archive):
    """GitHub release archive"""

    HEAD_FROM = {"pushed_at": Tag, "sha": Tag}

    @classmethod
    def list(cls, client, spec):
        """
        List archives for all branches and tags.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            generator of tuple: object name str, object header dict, directory bool
        """
        cls._raise_if_not_dir(spec.get("archive"), spec)

        tag = spec.get("tag", "latest")
        for ext in (".tar.gz", ".zip"):
            name = tag + ext
            yield name, cls(client, spec, name=name), False

    @classmethod
    def head_obj(cls, client, spec):
        """
        Get archive headers.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            dict: Object headers.
        """
        cls._latest_release(client, spec)
        return Archive(client, spec)

    def _update_spec_parent_ref(self, parent_key):
        """
        Update the spec with the parent reference.

        Args:
            parent_key (str): The parent key (parent_class.KEY).
        """
        # Should only occur with "LatestRelease", "tag" is already known with "Release"
        self._latest_release(self._client, self._spec)

    @staticmethod
    def _latest_release(client, spec):
        """
        Get the tag and archive name of the latest release.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.
        """
        if "tag" not in spec:
            spec["tag"] = LatestRelease.get_tag(client, spec)
            spec["archive"] = spec["archive"].replace("latest", spec["tag"])


class Release(GithubObject):
    """GitHub release"""

    KEY = "tag"
    CTIME = "created_at"
    LIST = "/repos/{owner}/{repo}/releases"
    LIST_KEY = "tag_name"
    HEAD = "/repos/{owner}/{repo}/releases/tags/{tag}"
    HEAD_KEYS = {"prerelease", "created_at", "published_at", "name"}
    HEAD_FROM = {"sha": Tag, "tree_sha": Commit}
    STRUCT = {
        "assets": ReleaseAsset,
        "tree": Tree,
        "archive": ReleaseArchive,
    }


class LatestRelease(Release):
    """Latest GitHub release, with fallback to HEAD"""

    KEY = None
    HEAD = "/repos/{owner}/{repo}/releases/latest"
    SYMLINK = "github://{owner}/{repo}/releases/{tag}"

    @classmethod
    def get_tag(cls, client, spec):
        """
        Get the tag matching the latest release.

        Args:
            client (airfs.storage.github._api.ApiV3): Client.
            spec (dict): Item spec.

        Returns:
            str: Tag.
        """
        return client.get(cls.HEAD.format(**spec))[0]["tag_name"]


class ReleaseDownload(GithubObject):
    """
    GitHub release downloads only

    To handle "https://github.com/:owner/:repo/releases/download/:tag/:asset_name"
    """

    KEY = "tag"
    CTIME = "created_at"
    LIST = "/repos/{owner}/{repo}/releases"
    LIST_KEY = "tag_name"
    HEAD = "/repos/{owner}/{repo}/releases/tags/{tag}"
    HEAD_KEYS = {"prerelease", "created_at", "published_at", "name"}
    HEAD_FROM = {"sha": Tag, "tree_sha": Commit}
    STRUCT = ReleaseAsset