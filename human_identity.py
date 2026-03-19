import base64
import getpass
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


PRIVATE_KEY_FILE = "PRIVATEkey.human"
PUBLIC_KEY_FILE = "publickey.human"
PRIVATE_KEY_BACKUP_FILE = "PRIVATEkey.human.backup"
KEY_ALGORITHM = "ed25519"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class HumanIdentityManager:
    def __init__(
        self,
        private_key_path: str = PRIVATE_KEY_FILE,
        public_key_path: str = PUBLIC_KEY_FILE,
        backup_key_path: str = PRIVATE_KEY_BACKUP_FILE,
    ):
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        self.backup_key_path = backup_key_path

    def exists(self) -> bool:
        return os.path.exists(self.private_key_path) and os.path.exists(self.public_key_path)

    def ensure_identity_interactive(self, console) -> dict[str, Any]:
        if self.exists():
            return self.load_public_metadata()

        console.print(
            "[bold yellow]No human cryptographic identity found.[/bold yellow]\n"
            "A new Ed25519 keypair will be created so your work can be signed and later rated on the ledger."
        )
        console.print(
            "[dim]Critical note:[/dim] this proves control of this keypair. "
            "It does not by itself prove unique humanity."
        )

        password = None
        backup_password = None

        password_choice = input("Protect PRIVATEkey.human with a password? [y/N]: ").strip().lower()
        if password_choice in {"y", "yes"}:
            password = self._prompt_password(confirm=True, label="PRIVATEkey.human")
            console.print(
                "[yellow]You chose password protection. You will need that password each time a task receipt is signed.[/yellow]"
            )

        backup_choice = input("Create a password-protected PRIVATEkey.human.backup? [y/N]: ").strip().lower()
        if backup_choice in {"y", "yes"}:
            backup_password = self._prompt_password(confirm=True, label="PRIVATEkey.human.backup")

        metadata = self.generate_identity(password=password, backup_password=backup_password)
        console.print(
            f"[green]Human identity created.[/green] Fingerprint: {metadata['fingerprint']}\n"
            f"[dim]Public key written to {self.public_key_path}. Private key written to {self.private_key_path}.[/dim]"
        )
        return metadata

    def generate_identity(self, password: str | None = None, backup_password: str | None = None) -> dict[str, Any]:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        public_key_b64 = base64.b64encode(public_key_bytes).decode("ascii")
        fingerprint = self._fingerprint(public_key_bytes)
        created_at = _utc_now_iso()

        self._write_private_key(self.private_key_path, private_key, password=password)
        if backup_password:
            self._write_private_key(self.backup_key_path, private_key, password=backup_password)

        metadata = {
            "version": 1,
            "algorithm": KEY_ALGORITHM,
            "public_key": public_key_b64,
            "fingerprint": fingerprint,
            "created_at": created_at,
        }
        with open(self.public_key_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        self._restrict_permissions(self.public_key_path, 0o644)
        return metadata

    def load_public_metadata(self) -> dict[str, Any]:
        with open(self.public_key_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def sign_task_receipt(self, receipt: dict[str, Any], console=None) -> dict[str, Any]:
        signature = self._sign_bytes(_canonical_json(receipt), console=console)
        metadata = self.load_public_metadata()
        return {
            "algorithm": KEY_ALGORITHM,
            "signature": signature,
            "public_key": metadata["public_key"],
            "fingerprint": metadata["fingerprint"],
        }

    def sign_message(self, message: str, console=None) -> str:
        return self._sign_bytes(message.encode("utf-8"), console=console)

    def _sign_bytes(self, payload: bytes, console=None) -> str:
        password = None
        if self.is_password_protected():
            if console:
                console.print("[dim]PRIVATEkey.human is password protected. Password required for signing.[/dim]")
            password = self._prompt_password(confirm=False, label="PRIVATEkey.human")

        private_key = self.load_private_key(password=password)
        signature = private_key.sign(payload)
        return base64.b64encode(signature).decode("ascii")

    def build_signed_task_receipt(self, task, result: str, completed_at: str, console=None) -> dict[str, Any]:
        metadata = self.load_public_metadata()
        receipt = {
            "version": 1,
            "task_id": task.id,
            "caller_id": task.caller_id,
            "title": task.title,
            "goal_id": getattr(task, "goal_id", None),
            "goal_label": getattr(task, "goal_label", None),
            "capability_required": task.capability_required,
            "deadline_minutes": getattr(task, "deadline_minutes", None),
            "priority": getattr(task, "priority", None),
            "proof_required": bool(getattr(task, "proof_required", False)),
            "success_criteria": getattr(task, "success_criteria", None),
            "created_at": task.created_at,
            "completed_at": completed_at,
            "result_sha256": hashlib.sha256(result.encode("utf-8")).hexdigest(),
            "description_sha256": hashlib.sha256(task.description.encode("utf-8")).hexdigest(),
            "context_sha256": hashlib.sha256((task.context or "").encode("utf-8")).hexdigest(),
            "human_public_key": metadata["public_key"],
            "human_fingerprint": metadata["fingerprint"],
        }
        signature_bundle = self.sign_task_receipt(receipt, console=console)
        return {
            "receipt": receipt,
            "signature": signature_bundle["signature"],
            "algorithm": signature_bundle["algorithm"],
            "human_public_key": signature_bundle["public_key"],
            "human_fingerprint": signature_bundle["fingerprint"],
        }

    def load_private_key(self, password: str | None = None) -> Ed25519PrivateKey:
        with open(self.private_key_path, "rb") as f:
            pem_data = f.read()
        private_key = serialization.load_pem_private_key(
            pem_data,
            password=password.encode("utf-8") if password else None,
        )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("PRIVATEkey.human is not an Ed25519 private key")
        return private_key

    def is_password_protected(self) -> bool:
        with open(self.private_key_path, "rb") as f:
            data = f.read()
        return b"ENCRYPTED PRIVATE KEY" in data

    @staticmethod
    def verify_signed_receipt(signed_receipt: dict[str, Any]) -> bool:
        receipt = signed_receipt["receipt"]
        signature = base64.b64decode(signed_receipt["signature"])
        public_key_bytes = base64.b64decode(signed_receipt["human_public_key"])
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        try:
            public_key.verify(signature, _canonical_json(receipt))
            return True
        except InvalidSignature:
            return False

    @staticmethod
    def verify_message_signature(public_key_b64: str, message: str, signature_b64: str) -> bool:
        try:
            signature = base64.b64decode(signature_b64)
            public_key_bytes = base64.b64decode(public_key_b64)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(signature, message.encode("utf-8"))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    def _write_private_key(self, path: str, private_key: Ed25519PrivateKey, password: str | None = None):
        encryption = (
            serialization.BestAvailableEncryption(password.encode("utf-8"))
            if password else serialization.NoEncryption()
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        with open(path, "wb") as f:
            f.write(pem)
        self._restrict_permissions(path, 0o600)

    def _prompt_password(self, confirm: bool, label: str) -> str:
        first = getpass.getpass(f"Enter password for {label}: ")
        if not confirm:
            return first
        second = getpass.getpass(f"Confirm password for {label}: ")
        if first != second:
            raise ValueError("Passwords did not match.")
        if not first:
            raise ValueError("Password cannot be empty.")
        return first

    def _fingerprint(self, public_key_bytes: bytes) -> str:
        digest = hashlib.sha256(public_key_bytes).hexdigest()
        return "sha256:" + digest

    def _restrict_permissions(self, path: str, mode: int):
        try:
            os.chmod(path, mode)
        except OSError:
            pass
