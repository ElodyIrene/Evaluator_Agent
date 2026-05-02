from pathlib import Path
import re

path = Path("app/rag/embeddings.py")
text = path.read_text(encoding="utf-8")

old = '''    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents."""
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
            encoding_format="float",
        )

        return [item.embedding for item in response.data]
'''

new = '''    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents.

        DashScope embedding API has a small batch size limit, so we send
        documents in batches of 10.
        """
        if not texts:
            return []

        batch_size = 10
        embeddings: List[List[float]] = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
                encoding_format="float",
            )

            embeddings.extend(item.embedding for item in response.data)

        return embeddings
'''

if old not in text:
    raise SystemExit("ERROR: target embed_documents function was not found")

text = text.replace(old, new)

path.write_text(text, encoding="utf-8")

print("OK: DashScope embed_documents now batches requests by 10")
