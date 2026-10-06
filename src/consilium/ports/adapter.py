"""Small capability-aware transport interface; no global provider state."""
from typing import Protocol, runtime_checkable

from consilium.core.contracts import AdapterCapabilities, AdapterRequest, DeliveryObservation, TransportResult


@runtime_checkable
class Adapter(Protocol):
    @property
    def capabilities(self) -> AdapterCapabilities: ...

    def send(self, request: AdapterRequest) -> TransportResult: ...

    def probe(self, request: AdapterRequest) -> DeliveryObservation: ...
