from dataclasses import dataclass, field


@dataclass
class SourceDocument:
    """
    Documento completo antes del chunking.
    """

    source: str
    title: str
    content: str
    ecosystem: str
    source_type: str
    source_url: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentChunk:
    """
    Fragmento que será convertido en embedding.
    """

    chunk_id: str
    text: str
    source: str
    title: str
    section: str
    ecosystem: str
    source_type: str
    source_url: str
    chunk_index: int

    def to_metadata(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "section": self.section,
            "ecosystem": self.ecosystem,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "chunk_index": self.chunk_index,
        }