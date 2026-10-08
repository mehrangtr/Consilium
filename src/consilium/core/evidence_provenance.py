"""Source dependence is explicit. Repeated reports do not create new observations."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

EvidenceKind = Literal['PLANNED', 'REPORTED', 'CODE_INSPECTED', 'EXECUTED', 'INDEPENDENT_REVIEW', 'UNKNOWN']
KINDS = frozenset({'PLANNED', 'REPORTED', 'CODE_INSPECTED', 'EXECUTED', 'INDEPENDENT_REVIEW', 'UNKNOWN'})


@dataclass(frozen=True)
class EvidenceSource:
    identifier: str
    kind: EvidenceKind
    parents: tuple[str, ...] = ()
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier or self.kind not in KINDS or len(self.parents) != len(set(self.parents)):
            raise ValueError('Invalid evidence source')
        if self.kind == 'REPORTED' and not self.parents:
            raise ValueError('Reported evidence requires its primary-source lineage')
        if self.artifact_sha256 is not None and (len(self.artifact_sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.artifact_sha256)):
            raise ValueError('Invalid evidence artifact digest')


def primary_sources(identifiers: tuple[str, ...], sources: Mapping[str, EvidenceSource]) -> frozenset[str]:
    leaves: set[str] = set()

    def visit(identifier: str, trail: frozenset[str]) -> None:
        if identifier in trail:
            raise ValueError('Circular evidence citation')
        if identifier not in sources:
            raise ValueError('Missing primary source')
        source = sources[identifier]
        if source.identifier != identifier:
            raise ValueError('Evidence registry key differs from its identifier')
        if not source.parents:
            leaves.add(identifier)
        for parent in source.parents:
            visit(parent, trail | {identifier})

    for identifier in identifiers:
        visit(identifier, frozenset())
    return frozenset(leaves)
