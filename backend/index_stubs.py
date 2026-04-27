"""Pickle-safe fallback index classes for offline or failed builds."""


class NullRetriever:
    def retrieve(self, _: str):
        return []


class NullIndex:
    def as_retriever(self, **kwargs):
        return NullRetriever()
