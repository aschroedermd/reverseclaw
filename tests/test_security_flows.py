import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from human_identity import HumanIdentityManager
from registry_server.ledger_store import LedgerStore
from registry_server.server import require_ledger_admin_token


class SecurityFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        self.identity = HumanIdentityManager(
            private_key_path=str(tmp / "PRIVATEkey.human"),
            public_key_path=str(tmp / "publickey.human"),
            backup_key_path=str(tmp / "PRIVATEkey.human.backup"),
        )
        self.metadata = self.identity.generate_identity()
        self.store = LedgerStore(
            db_path=str(tmp / "ledger.db"),
            evidence_retention_hours=1,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _verified_session(self):
        session = self.store.start_verification(
            "Test Human",
            self.metadata["public_key"],
            self.metadata["fingerprint"],
        )
        self.store.complete_verification(session["id"], {"success": True})
        return session

    def test_message_signature_roundtrip(self):
        message = "reverseclaw-ledger-register:test:challenge"
        signature = self.identity.sign_message(message)
        self.assertTrue(
            HumanIdentityManager.verify_message_signature(
                self.metadata["public_key"],
                message,
                signature,
            )
        )
        self.assertFalse(
            HumanIdentityManager.verify_message_signature(
                self.metadata["public_key"],
                message + ":tampered",
                signature,
            )
        )

    def test_ledger_registration_requires_valid_proof_signature(self):
        session = self._verified_session()
        with self.assertRaisesRegex(ValueError, "Proof-of-possession signature is invalid"):
            self.store.register_human_key(
                {
                    "name": "Test Human",
                    "url": "https://example.com",
                    "capabilities": ["research"],
                    "tagline": "hello",
                    "public_key": self.metadata["public_key"],
                    "fingerprint": self.metadata["fingerprint"],
                    "verification_id": session["id"],
                    "proof_signature": self.identity.sign_message("wrong-challenge"),
                }
            )

    def test_ledger_registration_accepts_valid_proof_signature(self):
        session = self._verified_session()
        profile = self.store.register_human_key(
            {
                "name": "Test Human",
                "url": "https://example.com",
                "capabilities": ["research"],
                "tagline": "hello",
                "public_key": self.metadata["public_key"],
                "fingerprint": self.metadata["fingerprint"],
                "verification_id": session["id"],
                "proof_signature": self.identity.sign_message(session["proof_message"]),
            }
        )
        self.assertEqual(profile["fingerprint"], self.metadata["fingerprint"])

    def test_ledger_admin_token_is_required(self):
        original = os.environ.get("LEDGER_ADMIN_TOKEN")
        try:
            os.environ["LEDGER_ADMIN_TOKEN"] = "secret-token"
            request = SimpleNamespace(headers={"Authorization": "Bearer wrong-token"})
            with self.assertRaises(HTTPException) as ctx:
                require_ledger_admin_token(request)
            self.assertEqual(ctx.exception.status_code, 401)

            request = SimpleNamespace(headers={"Authorization": "Bearer secret-token"})
            require_ledger_admin_token(request)
        finally:
            if original is None:
                os.environ.pop("LEDGER_ADMIN_TOKEN", None)
            else:
                os.environ["LEDGER_ADMIN_TOKEN"] = original


if __name__ == "__main__":
    unittest.main()
