import hashlib
import re

from rag.models import DocumentChunk, SourceDocument


HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+)$",
    re.MULTILINE,
)


class MarkdownChunker:
    def __init__(
        self,
        chunk_size_words: int = 180,
        overlap_words: int = 30,
    ):
        if chunk_size_words <= 0:
            raise ValueError(
                "chunk_size_words debe ser mayor a cero."
            )

        if overlap_words < 0:
            raise ValueError(
                "overlap_words no puede ser negativo."
            )

        if overlap_words >= chunk_size_words:
            raise ValueError(
                "overlap_words debe ser menor que chunk_size_words."
            )

        self.chunk_size_words = chunk_size_words
        self.overlap_words = overlap_words

    def chunk_documents(
        self,
        documents: list[SourceDocument],
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        for document in documents:
            chunks.extend(self.chunk_document(document))

        return chunks

    def chunk_document(
        self,
        document: SourceDocument,
    ) -> list[DocumentChunk]:
        sections = self._split_sections(document.content)

        chunks: list[DocumentChunk] = []
        chunk_index = 0

        for section_name, section_content in sections:
            words = section_content.split()

            if not words:
                continue

            step = (
                self.chunk_size_words
                - self.overlap_words
            )

            for start in range(0, len(words), step):
                end = start + self.chunk_size_words
                selected_words = words[start:end]

                if not selected_words:
                    continue

                body = " ".join(selected_words)

                text = (
                    f"Título: {document.title}\n"
                    f"Sección: {section_name}\n\n"
                    f"{body}"
                )

                chunk_id = self._build_chunk_id(
                    source=document.source,
                    section=section_name,
                    chunk_index=chunk_index,
                    text=text,
                )

                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        text=text,
                        source=document.source,
                        title=document.title,
                        section=section_name,
                        ecosystem=document.ecosystem,
                        source_type=document.source_type,
                        source_url=document.source_url,
                        chunk_index=chunk_index,
                    )
                )

                chunk_index += 1

                if end >= len(words):
                    break

        return chunks

    @staticmethod
    def _split_sections(
        content: str,
    ) -> list[tuple[str, str]]:
        matches = list(
            HEADING_PATTERN.finditer(content)
        )

        if not matches:
            return [("Documento", content.strip())]

        sections: list[tuple[str, str]] = []

        preface = content[:matches[0].start()].strip()

        if preface:
            sections.append(
                ("Introducción", preface)
            )

        for index, match in enumerate(matches):
            section_name = match.group(2).strip()
            section_start = match.end()

            if index + 1 < len(matches):
                section_end = matches[index + 1].start()
            else:
                section_end = len(content)

            section_content = content[
                section_start:section_end
            ].strip()

            if section_content:
                sections.append(
                    (section_name, section_content)
                )

        return sections

    @staticmethod
    def _build_chunk_id(
        *,
        source: str,
        section: str,
        chunk_index: int,
        text: str,
    ) -> str:
        raw_value = (
            f"{source}|{section}|{chunk_index}|{text}"
        )

        digest = hashlib.sha256(
            raw_value.encode("utf-8")
        ).hexdigest()

        return digest[:24]