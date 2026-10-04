import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from agent.graph import (
    assessment_graph,
    assess_understanding_node,
    extract_topic_node,
    get_llm,
    get_model,
    parse_assessment_result,
)


class _Response:
    def __init__(self, content: str):
        self.content = content


class _FakeLlm:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, _messages):
        return _Response(self.content)


class _SequenceLlm:
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)

    async def ainvoke(self, _messages):
        return _Response(next(self.responses))


class AssessmentResultTests(unittest.TestCase):
    def test_accepts_strict_valid_json(self):
        result = parse_assessment_result(
            '{"resolved": false, "hint_level": 2, "misconception": "base case"}'
        )

        self.assertFalse(result.resolved)
        self.assertEqual(result.hint_level, 2)

    def test_rejects_string_booleans_and_out_of_range_hints(self):
        with self.assertRaises(ValidationError):
            parse_assessment_result(
                '{"resolved": "false", "hint_level": 2, "misconception": ""}'
            )
        with self.assertRaises(ValidationError):
            parse_assessment_result(
                '{"resolved": false, "hint_level": 4, "misconception": ""}'
            )


class ProviderConfigurationTests(unittest.TestCase):
    def test_groq_uses_gpt_oss_120b_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_model("groq"), "openai/gpt-oss-120b")

    def test_groq_requires_an_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GROQ_API_KEY"):
                get_llm("groq")


class TopicTrackingTests(unittest.TestCase):
    def test_unknown_follow_up_preserves_current_topic(self):
        state = {
            "messages": [
                HumanMessage(content="Explain recursion"),
                AIMessage(content="What is a base case?"),
                HumanMessage(content="I think it stops at zero"),
            ],
            "topic": "recursion",
            "hint_level": 1,
            "misconception": "",
            "resolved": False,
            "llm": _FakeLlm("unknown"),
        }

        update = asyncio.run(extract_topic_node(state))

        self.assertEqual(update, {})

    def test_new_topic_resets_learning_state(self):
        state = {
            "messages": [
                HumanMessage(content="Explain recursion"),
                AIMessage(content="What is a base case?"),
                HumanMessage(content="Let's switch to hash tables"),
            ],
            "topic": "recursion",
            "hint_level": 3,
            "misconception": "base case",
            "resolved": True,
            "llm": _FakeLlm("hash tables"),
        }

        result = asyncio.run(assessment_graph.ainvoke(state))

        self.assertEqual(result["topic"], "hash tables")
        self.assertEqual(result["hint_level"], 0)
        self.assertEqual(result["misconception"], "")
        self.assertFalse(result["resolved"])

    def test_resolved_problem_resets_hint_level(self):
        state = {
            "messages": [
                HumanMessage(content="Explain recursion"),
                AIMessage(content="What does the base case do?"),
                HumanMessage(content="It stops the recursive calls."),
            ],
            "topic": "recursion",
            "hint_level": 3,
            "misconception": "base case",
            "resolved": False,
            "llm": _FakeLlm(
                '{"resolved": true, "hint_level": 3, "misconception": ""}'
            ),
        }

        update = asyncio.run(assess_understanding_node(state))

        self.assertTrue(update["resolved"])
        self.assertEqual(update["hint_level"], 0)
        self.assertEqual(update["misconception"], "")

    def test_async_graph_uses_request_scoped_llm(self):
        state = {
            "messages": [
                HumanMessage(content="Explain recursion"),
                AIMessage(content="What is a base case?"),
                HumanMessage(content="It stops the recursive calls"),
            ],
            "topic": "recursion",
            "hint_level": 1,
            "misconception": "",
            "resolved": False,
            "llm": _SequenceLlm(
                [
                    "same",
                    '{"resolved": false, "hint_level": 2, "misconception": "termination condition"}',
                ]
            ),
        }

        result = asyncio.run(assessment_graph.ainvoke(state))

        self.assertEqual(result["topic"], "recursion")
        self.assertEqual(result["hint_level"], 2)
        self.assertEqual(result["misconception"], "termination condition")


if __name__ == "__main__":
    unittest.main()
