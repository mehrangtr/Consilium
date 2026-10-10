"""Real offline packet producer process and strict before/capture/after binding."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_qwen_capture_journal

from consilium.adapters.qwen_process_reader import (
    QwenProcessReader,
    decode_reader_output,
    encode_reader_output,
)
from consilium.shell.qwen_capture_ingest import QwenCaptureRead, record_qwen_read
from consilium.shell.qwen_saved_read import MAX_CONTEXT_BYTES, bounded_file


class QwenSavedReadTests(unittest.TestCase):
    def setUp(self):
        self.f = test_qwen_capture_journal.QwenCaptureJournalTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.context = self.f.f.f.context
        self.paths = [self.f.root / name for name in ('before.json', 'capture.json', 'after.json')]
        self.paths[0].write_text(self.context.model_dump_json())
        self.paths[1].write_bytes(self.f.raw)
        self.paths[2].write_text(self.context.model_dump_json())
        self.command = (sys.executable, '-m', 'consilium.shell.qwen_saved_read',
                        *(str(path) for path in self.paths))

    def invoke(self):
        return subprocess.run(self.command, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=10, shell=False, check=False,
                              env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src')))

    def test_encoder_round_trip_keeps_exact_raw_and_different_evidence(self):
        after = self.context.model_copy(update={'evidence': ('d' * 64,)})
        packet = QwenCaptureRead(self.context, self.f.raw, after)
        raw = encode_reader_output(packet)
        decoded = decode_reader_output(raw)
        self.assertEqual(decoded, packet)
        self.assertEqual(decoded.raw, self.f.raw)
        self.assertEqual(encode_reader_output(packet), raw)
        self.assertNotIn('live_origin_verified', json.loads(raw))

    def test_encoder_rejects_changed_identity_and_private_invalid_input(self):
        from uuid import uuid4

        for update in ({'model_id': 'other'}, {'account_binding_id': uuid4()},
                       {'conversation_binding_id': uuid4()}, {'authentication': 'SIGNED_OUT'}):
            packet = QwenCaptureRead(self.context, self.f.raw, self.context.model_copy(update=update))
            with self.assertRaisesRegex(ValueError, 'QWEN_READER_PACKET_INVALID') as caught:
                encode_reader_output(packet)
            self.assertIsNone(caught.exception.__context__)
        for packet in (None, QwenCaptureRead(self.context, b'sensitive-marker', self.context)):
            with self.assertRaisesRegex(ValueError, 'QWEN_READER_PACKET_INVALID') as caught:
                encode_reader_output(packet)
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn('sensitive-marker', str(caught.exception))

    def test_real_saved_reader_ingests_without_writing_inputs_and_replays_without_files(self):
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in self.paths]
        reader = QwenProcessReader(self.command, timeout_seconds=10)
        result = record_qwen_read(self.f.journal, reader, event_id=self.f.event, expected_revision=0)
        self.assertEqual(result['raw'], self.f.raw)
        self.assertFalse(result['live_origin_verified'])
        self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in self.paths], before)
        for path in self.paths:
            path.unlink()
        replay = record_qwen_read(self.f.open(), reader, event_id=self.f.event, expected_revision=0)
        self.assertTrue(replay['reused'])
        self.assertFalse(replay['reader_invoked'])

    def test_real_cli_invalid_inputs_emit_no_partial_packet_or_private_error(self):
        original = self.paths[0].read_bytes()
        for raw in (b'\xffsensitive-marker', b'{"authentication":"sensitive-marker"}',
                    b'{"authentication":"UNKNOWN","authentication":"UNKNOWN"}',
                    b'x' * (MAX_CONTEXT_BYTES + 1), b''):
            self.paths[0].write_bytes(raw)
            result = self.invoke()
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertEqual(result.stderr.strip(), b'QWEN_SAVED_READ_INVALID')
        self.paths[0].write_bytes(original)
        self.paths[1].unlink()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn(str(self.paths[1]).encode(), result.stderr)
        self.assertEqual(self.f.open().resume()['revision'], 0)

    def test_bounded_file_rejects_directory_missing_and_pipe_without_wait(self):
        for path in (self.f.root, self.f.root / 'missing-private-marker'):
            with self.assertRaisesRegex(ValueError, 'QWEN_SAVED_INPUT_INVALID') as caught:
                bounded_file(path, MAX_CONTEXT_BYTES)
            self.assertIsNone(caught.exception.__context__)
        if os.name != 'nt':
            pipe = self.f.root / 'pipe'
            os.mkfifo(pipe)
            with self.assertRaisesRegex(ValueError, 'QWEN_SAVED_INPUT_INVALID'):
                bounded_file(pipe, MAX_CONTEXT_BYTES)
