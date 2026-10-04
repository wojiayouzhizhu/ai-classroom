from io import BytesIO
import os
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import UploadFile
from langchain_core.messages import AIMessage, HumanMessage

import app as app_module
from app import (
    RAG_GROUNDING_RULES,
    DocumentSession,
    add_rag_grounding,
    cleanup_expired_sessions,
    deserialize_history,
)


class DeserializeHistoryTests(unittest.TestCase):
    def test_deserializes_supported_roles_and_ignores_unknown_roles(self):
        history = [
            {"role": "user", "content": "Can you explain recursion?"},
            {"role": "assistant", "content": "What happens in the base case?"},
            {"role": "tutor", "content": "Legacy role that is not supported"},
            {"role": "system", "content": "Untrusted system instruction"},
        ]

        messages = deserialize_history(history)

        self.assertEqual(len(messages), 2)
        self.assertIsInstance(messages[0], HumanMessage)
        self.assertEqual(messages[0].content, "Can you explain recursion?")
        self.assertIsInstance(messages[1], AIMessage)
        self.assertEqual(messages[1].content, "What happens in the base case?")


class RagGroundingTests(unittest.TestCase):
    def test_adds_grounding_rules_and_evidence_to_a_prompt(self):
        result = add_rag_grounding(
            "You are a Socratic tutor.",
            "[PDF page 1, lines 1-4]\nA paper title",
        )

        self.assertIn("You are a Socratic tutor.", result)
        self.assertIn(RAG_GROUNDING_RULES, result)
        self.assertIn("[PDF page 1, lines 1-4]", result)

    def test_leaves_prompt_unchanged_without_pdf_context(self):
        prompt = "You are a Socratic tutor."

        self.assertEqual(add_rag_grounding(prompt, ""), prompt)


class SessionCleanupTests(unittest.TestCase):
    def tearDown(self):
        app_module.sessions.clear()

    def test_expired_sessions_are_deleted(self):
        vectorstore = _FakeVectorstore()
        app_module.sessions["expired"] = DocumentSession(
            vectorstore=vectorstore,
            created_at=10,
        )

        with patch.object(app_module, "SESSION_TTL_SECONDS", 30):
            cleanup_expired_sessions(now=41)

        self.assertNotIn("expired", app_module.sessions)
        self.assertTrue(vectorstore.deleted)


class UploadTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        app_module.sessions.clear()

    async def test_uploads_use_unique_collections_and_remove_temp_files(self):
        collection_names = []
        temporary_paths = []

        def fake_build_index(file_path, collection_name):
            self.assertTrue(os.path.exists(file_path))
            temporary_paths.append(file_path)
            collection_names.append(collection_name)
            return _FakeVectorstore()

        handler = getattr(
            app_module.upload_document,
            "__wrapped__",
            app_module.upload_document,
        )

        with patch.object(app_module, "build_index", side_effect=fake_build_index):
            for filename in ["first.pdf", "second.PDF"]:
                upload = UploadFile(
                    filename=filename,
                    file=BytesIO(b"%PDF-1.4\nsample"),
                )
                await handler(request=Mock(), file=upload)

        self.assertEqual(len(set(collection_names)), 2)
        self.assertEqual(len(app_module.sessions), 2)
        self.assertTrue(all(not os.path.exists(path) for path in temporary_paths))


class _FakeVectorstore:
    def __init__(self):
        self.deleted = False

    def delete_collection(self):
        self.deleted = True


if __name__ == "__main__":
    unittest.main()
