"""Wire-level synthetic tests, no SDK credentials, network or real model responses."""

import json
import unittest

from consilium.adapters.api_codec import (
    MAX_BYTES,
    CodecError,
    StreamDecoder,
    decode,
    encode,
)
from consilium.core.contracts import FrozenInput, GenerationParameters, Message


def raw(obj):
    return json.dumps(obj, ensure_ascii=False).encode()


def envelope(provider, text="پاسخ English", finish=None, *, thought=False):
    if provider == "google":
        return {
            "responseId": "g-1",
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": text, "thought": thought}],
                    },
                    "finishReason": finish or "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 4,
                "candidatesTokenCount": 3,
                "totalTokenCount": 7,
            },
        }
    return {
        "id": "q-1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish or "stop",
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
    }


def event(obj):
    return b"data: " + raw(obj) + b"\n\n"


class ApiCodecTests(unittest.TestCase):
    def setUp(self):
        self.frozen = FrozenInput(
            messages=(
                Message(role="SYSTEM", content="system"),
                Message(role="USER", content=" فارسی\nEnglish "),
                Message(role="ASSISTANT", content="previous"),
                Message(role="USER", content="next"),
            ),
            parameters=GenerationParameters(temperature=0.5, max_output_tokens=32),
        )

    def test_google_wire_preserves_roles_unicode_and_limits(self):
        before = self.frozen.canonical_bytes()
        wire = encode("google", "fixture-model", self.frozen)
        obj = json.loads(wire.body)
        self.assertEqual(
            [c["role"] for c in obj["contents"]], ["user", "model", "user"]
        )
        self.assertEqual(obj["contents"][0]["parts"][0]["text"], " فارسی\nEnglish ")
        self.assertEqual(obj["generationConfig"]["maxOutputTokens"], 32)
        self.assertEqual(obj["systemInstruction"]["parts"], [{"text": "system"}])
        self.assertEqual(before, self.frozen.canonical_bytes())

    def test_qwen_wire_preserves_roles_parameters_and_stream_usage(self):
        obj = json.loads(
            encode("qwen", "fixture-model", self.frozen, streaming=True).body
        )
        self.assertEqual(obj["messages"][0], {"role": "system", "content": "system"})
        self.assertEqual(obj["max_tokens"], 32)
        self.assertEqual(obj["n"], 1)
        self.assertEqual(obj["stream_options"], {"include_usage": True})

    def test_invalid_models_providers_and_unsupported_seed_fail_before_send(self):
        for model in ("", "models/x", "x?key=secret", "a\nheader", "x" * 129):
            with self.assertRaises(CodecError):
                encode("google", model, self.frozen)
        with self.assertRaises(CodecError):
            encode("other", "m", self.frozen)
        frozen = self.frozen.model_copy(
            update={"parameters": GenerationParameters(seed=1)}
        )
        with self.assertRaises(CodecError):
            encode("google", "m", frozen)
        self.assertEqual(json.loads(encode("qwen", "m", frozen).body)["seed"], 1)

    def test_google_does_not_reorder_interleaved_system_messages(self):
        frozen = FrozenInput(
            messages=(
                Message(role="USER", content="u"),
                Message(role="SYSTEM", content="s"),
            )
        )
        with self.assertRaises(CodecError):
            encode("google", "m", frozen)

    def test_complete_both_providers_and_usage_unknown_is_not_zero(self):
        for provider in ("google", "qwen"):
            obs = decode(provider, raw(envelope(provider)))
            self.assertEqual(obs.state, "COMPLETE")
            self.assertEqual(obs.content, "پاسخ English")
            self.assertEqual(obs.total_tokens, 7)
            obj = envelope(provider)
            obj.pop("usageMetadata" if provider == "google" else "usage")
            self.assertIsNone(decode(provider, raw(obj)).total_tokens)

    def test_length_finish_is_partial_and_unknown_finish_not_complete(self):
        for provider, reason in (
            ("google", "MAX_TOKENS"),
            ("qwen", "length"),
            ("google", "NEW_REASON"),
        ):
            self.assertEqual(
                decode(provider, raw(envelope(provider, finish=reason))).state,
                "PARTIAL",
            )

    def test_empty_blocked_and_thought_only_responses_are_not_answers(self):
        self.assertEqual(
            decode("google", raw({"promptFeedback": {"blockReason": "SAFETY"}})).state,
            "NONE",
        )
        self.assertEqual(
            decode("google", raw(envelope("google", thought=True))).state, "NONE"
        )
        self.assertEqual(decode("qwen", raw(envelope("qwen", text=" "))).state, "NONE")

    def test_tool_calls_cannot_masquerade_as_text_answer(self):
        obj = envelope("qwen")
        obj["choices"][0]["message"]["tool_calls"] = [{"id": "tool"}]
        self.assertEqual(decode("qwen", raw(obj)).state, "INVALID")
        obj = envelope("google")
        obj["candidates"][0]["content"]["parts"].append({"functionCall": {"name": "x"}})
        self.assertEqual(decode("google", raw(obj)).state, "INVALID")

    def test_malformed_duplicate_nonfinite_and_oversized_json_fixed_errors(self):
        for body in (
            b"[]",
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b"\xff",
            b"{secret",
            b"a" * (MAX_BYTES + 1),
        ):
            with self.assertRaises(CodecError) as caught:
                decode("qwen", body)
            self.assertNotIn("secret", str(caught.exception))

    def test_multiple_candidates_bad_identity_usage_and_nontext_are_rejected(self):
        for provider in ("google", "qwen"):
            obj = envelope(provider)
            key = "candidates" if provider == "google" else "choices"
            obj[key] *= 2
            with self.assertRaises(CodecError):
                decode(provider, raw(obj))
        obj = envelope("qwen")
        obj["usage"]["prompt_tokens"] = True
        with self.assertRaises(CodecError):
            decode("qwen", raw(obj))
        obj = envelope("qwen")
        obj["id"] = "bad\nsecret"
        with self.assertRaises(CodecError):
            decode("qwen", raw(obj))
        obj = envelope("qwen")
        obj["choices"][0]["message"]["content"] = {"wrong": 1}
        with self.assertRaises(CodecError):
            decode("qwen", raw(obj))

    def stream_bytes(self, provider):
        if provider == "google":
            return event(envelope(provider, text="پاسخ"))
        return (
            event(
                {
                    "id": "q-1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "پاسخ"},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            + event(
                {
                    "id": "q-1",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
            + event({"id": "q-1", "choices": [], "usage": {"total_tokens": 7}})
            + b"data: [DONE]\n\n"
        )

    def test_stream_every_byte_split_unicode_crlf_comments_and_usage(self):
        for provider in ("google", "qwen"):
            data = b": keepalive\r\n\r\n" + self.stream_bytes(provider).replace(
                b"\n", b"\r\n"
            )
            for split in range(len(data) + 1):
                parser = StreamDecoder(provider)
                parser.feed(data[:split])
                parser.feed(data[split:])
                obs = parser.close()
                self.assertEqual(obs.state, "COMPLETE", (provider, split))
                self.assertEqual(obs.content, "پاسخ")
        parser = StreamDecoder("qwen")
        for byte in self.stream_bytes("qwen"):
            parser.feed(bytes([byte]))
        self.assertEqual(parser.close().total_tokens, 7)

    def test_missing_done_truncated_frames_and_interruption_preserve_partial(self):
        data = self.stream_bytes("qwen")
        for body in (data.replace(b"data: [DONE]\n\n", b""), data[:-4]):
            parser = StreamDecoder("qwen")
            parser.feed(body)
            self.assertEqual(parser.close().state, "PARTIAL")
        parser = StreamDecoder("google")
        parser.feed(self.stream_bytes("google"))
        self.assertEqual(parser.close(interrupted=True).state, "PARTIAL")

    def test_stream_id_change_extra_content_and_corruption_cannot_complete(self):
        for extra in (
            event({"id": "q-2", "choices": []}),
            event({"id": "q-1", "choices": [{"delta": {"content": "extra"}}]}),
            b"data: {secret\n\n",
        ):
            parser = StreamDecoder("qwen")
            parser.feed(self.stream_bytes("qwen").replace(b"data: [DONE]\n\n", b""))
            with self.assertRaises(CodecError):
                parser.feed(extra)
            self.assertEqual(parser.close().state, "PARTIAL")

    def test_stream_bounds_and_double_close(self):
        parser = StreamDecoder("google")
        with self.assertRaises(CodecError):
            parser.feed(b"x" * (MAX_BYTES + 1))
        self.assertEqual(parser.close().state, "NONE")
        with self.assertRaises(CodecError):
            parser.feed(b"")
        with self.assertRaises(CodecError):
            parser.close()

    def test_qwen_nullable_delta_role_matches_documented_stream(self):
        parser = StreamDecoder("qwen")
        parser.feed(
            event(
                {
                    "id": "q-1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": None, "content": "answer"},
                            "finish_reason": None,
                        }
                    ],
                }
            )
        )
        parser.feed(
            event(
                {
                    "id": "q-1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": None, "content": None},
                            "finish_reason": "stop",
                        }
                    ],
                }
            )
        )
        parser.feed(b"data: [DONE]\n\n")
        self.assertEqual(parser.close().state, "COMPLETE")
