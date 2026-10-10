"""P09 synthetic pages only; no authentication or live response certification."""

import hashlib
import unittest
from uuid import uuid4

from pydantic import ValidationError

from consilium.core.browser_probe import BrowserBinding, BrowserContext
from consilium.core.browser_watch import BrowserWatch, PageMessage, PageSnapshot


class BrowserWatchTests(unittest.TestCase):
    def setUp(self):
        self.binding = BrowserBinding(
            connection_id=uuid4(),
            connection_revision=0,
            account_binding_id=uuid4(),
            conversation_binding_id=uuid4(),
            model_id="fixture",
        )
        self.context = BrowserContext(
            authentication="AUTHENTICATED",
            evidence=("a" * 64,),
            account_binding_id=self.binding.account_binding_id,
            conversation_binding_id=self.binding.conversation_binding_id,
            model_id="fixture",
        )
        self.old = PageMessage(message_id=uuid4(), role="USER", text="old")
        self.user = PageMessage(message_id=uuid4(), role="USER", text="پرسش تازه")
        self.answer = PageMessage(
            message_id=uuid4(),
            role="ASSISTANT",
            text="پاسخ",
            reply_to=self.user.message_id,
        )
        self.base = self.page(0, (self.old,))
        self.watch = BrowserWatch(
            self.binding, self.base, hashlib.sha256(self.user.text.encode()).hexdigest()
        )

    def page(self, sequence, messages, **kw):
        return PageSnapshot(
            sequence=sequence,
            context=kw.pop("context", self.context),
            messages=messages,
            full_history=kw.pop("full_history", True),
            evidence_hash="b" * 64,
            **kw,
        )

    def test_correlated_partial_then_complete_and_closed_cannot_resend(self):
        self.assertEqual(
            self.watch.observe(self.page(1, (self.old, self.user, self.answer))),
            "PARTIAL",
        )
        final = self.answer.model_copy(
            update={
                "text": "پاسخ کامل",
                "complete": True,
                "completion_evidence": ("c" * 64,),
            }
        )
        self.assertEqual(
            self.watch.observe(self.page(2, (self.old, self.user, final))), "COMPLETE"
        )
        with self.assertRaises(ValueError):
            self.watch.observe(self.page(3, (self.old, self.user, final)))

    def test_old_same_prompt_is_not_new_delivery_evidence(self):
        base = self.page(0, (self.user,))
        w = BrowserWatch(self.binding, base, self.watch.prompt_hash)
        self.assertEqual(w.observe(self.page(1, (self.user,))), "NONE")
        self.assertIsNone(w.user_id)

    def test_partial_is_preserved_after_logout_or_history_loss(self):
        for changes in (
            {"full_history": False},
            {
                "context": BrowserContext(
                    authentication="SIGNED_OUT", evidence=("d" * 64,)
                )
            },
        ):
            w = BrowserWatch(self.binding, self.base, self.watch.prompt_hash)
            w.observe(self.page(1, (self.old, self.user, self.answer)))
            self.assertEqual(
                w.observe(self.page(2, (self.old, self.user, self.answer), **changes)),
                "PARTIAL",
            )
            self.assertEqual(w.content, "پاسخ")
            self.assertTrue(w.stopped)

    def test_model_account_or_conversation_change_stops(self):
        for field, value in (
            ("model_id", "other"),
            ("account_binding_id", uuid4()),
            ("conversation_binding_id", uuid4()),
        ):
            w = BrowserWatch(self.binding, self.base, self.watch.prompt_hash)
            w.observe(
                self.page(
                    1,
                    (self.old, self.user, self.answer),
                    context=self.context.model_copy(update={field: value}),
                )
            )
            self.assertIsNone(w.content)
            self.assertTrue(w.stopped)

    def test_stale_snapshot_and_edited_prior_transcript_stop(self):
        for page in (
            self.page(0, (self.old,)),
            self.page(1, (self.old.model_copy(update={"text": "edited"}),)),
        ):
            w = BrowserWatch(self.binding, self.base, self.watch.prompt_hash)
            w.observe(page)
            self.assertTrue(w.stopped)
            self.assertEqual(w.state, "NONE")

    def test_wrong_prompt_parent_and_multiple_answers_do_not_complete(self):
        for messages in (
            (self.old, self.user.model_copy(update={"text": "other"}), self.answer),
            (self.old, self.user, self.answer.model_copy(update={"reply_to": uuid4()})),
            (
                self.old,
                self.user,
                self.answer,
                self.answer.model_copy(update={"message_id": uuid4()}),
            ),
        ):
            w = BrowserWatch(self.binding, self.base, self.watch.prompt_hash)
            w.observe(self.page(1, messages))
            self.assertEqual(w.state, "NONE")
            self.assertTrue(w.stopped)

    def test_replaced_shrunk_or_disappeared_answer_preserves_partial(self):
        for messages in (
            (self.old, self.user),
            (self.old, self.user, self.answer.model_copy(update={"text": "پ"})),
            (
                self.old,
                self.user,
                self.answer.model_copy(update={"message_id": uuid4()}),
            ),
        ):
            w = BrowserWatch(self.binding, self.base, self.watch.prompt_hash)
            w.observe(self.page(1, (self.old, self.user, self.answer)))
            self.assertEqual(w.observe(self.page(2, messages)), "PARTIAL")
            self.assertEqual(w.content, "پاسخ")
            self.assertTrue(w.stopped)

    def test_interruption_and_invalid_completion_or_duplicate_ids(self):
        self.assertEqual(self.watch.interrupt(), "NONE")
        self.assertTrue(self.watch.stopped)
        with self.assertRaises(ValidationError):
            self.answer.model_copy(update={"complete": True})
        with self.assertRaises(ValidationError):
            self.page(1, (self.user, self.user))
