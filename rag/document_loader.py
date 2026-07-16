from pathlib import Path

import yaml

from rag.models import SourceDocument


SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
}


class DocumentLoader:
    def __init__(self, raw_documents_dir: Path):
        self.raw_documents_dir = raw_documents_dir.resolve()

    def load_all(self) -> list[SourceDocument]:
        if not self.raw_documents_dir.exists():
            raise FileNotFoundError(
                "No existe la carpeta de documentación: "
                f"{self.raw_documents_dir}"
            )

        documents: list[SourceDocument] = []

        for path in sorted(self.raw_documents_dir.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            documents.append(self._load_document(path))

        return documents

    def _load_document(self, path: Path) -> SourceDocument:
        raw_content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        metadata, content = self._parse_frontmatter(raw_content)

        relative_path = path.relative_to(
            self.raw_documents_dir
        ).as_posix()

        ecosystem = metadata.get(
            "ecosystem",
            path.parent.name,
        )

        return SourceDocument(
            source=relative_path,
            title=metadata.get("title", path.stem),
            content=content.strip(),
            ecosystem=str(ecosystem).lower(),
            source_type=metadata.get(
                "source_type",
                "technical_documentation",
            ),
            source_url=metadata.get("source_url", ""),
            metadata=metadata,
        )

    @staticmethod
    def _parse_frontmatter(
        raw_content: str,
    ) -> tuple[dict, str]:
        """
        Lee metadata YAML delimitada por --- al inicio del documento.
        """

        if not raw_content.startswith("---"):
            return {}, raw_content

        parts = raw_content.split("---", 2)

        if len(parts) != 3:
            return {}, raw_content

        _, metadata_text, content = parts

        try:
            metadata = yaml.safe_load(metadata_text) or {}
        except yaml.YAMLError:
            return {}, raw_content

        if not isinstance(metadata, dict):
            metadata = {}

        return metadata, content