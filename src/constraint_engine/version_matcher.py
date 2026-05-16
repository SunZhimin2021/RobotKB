from __future__ import annotations

from packaging.version import Version
from packaging.specifiers import SpecifierSet


class VersionMatcher:
    """SemVer range matching using PEP 440 specifiers."""

    @staticmethod
    def version_in_range(version: str, range_spec: str | None) -> bool:
        """Return True if version satisfies range_spec.

        Args:
            version: Version string, e.g. "5.10.5".
            range_spec: Comma-separated PEP 440 specifiers, e.g. ">=5.10,<6.0".
                        None or empty string means no constraint (always True).
        """
        if not range_spec:
            return True
        spec = SpecifierSet(range_spec)
        return Version(version) in spec

    @staticmethod
    def is_compatible(
        doc_ros_version: str | None,
        constraint_ros_version: str | None,
    ) -> bool:
        """Return True if doc_ros_version matches constraint_ros_version.

        None on either side means no constraint — always compatible.
        Comparison is exact (case-sensitive string equality).
        """
        if constraint_ros_version is None or doc_ros_version is None:
            return True
        return doc_ros_version == constraint_ros_version
