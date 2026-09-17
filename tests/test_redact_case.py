from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "redact_case.py"
SPEC = importlib.util.spec_from_file_location("redact_case", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RedactionTests(unittest.TestCase):
    def test_redacts_identifiers_and_preserves_calculation_values(self) -> None:
        original = {
            "case_name": "张三的真实借款",
            "amount_received": 30000,
            "borrower": {
                "borrower_name": "张三",
                "id_number": "110105199001011234",
                "phone": "13812345678",
                "bank_account": "6222021234567890123",
            },
            "entities": [
                {"id": "bank", "name": "真实银行股份有限公司", "role": "lender"},
                {"id": "collector", "name": "真实催收公司", "role": "collector"},
            ],
            "balance_claims": [
                {"date": "2026-01-01", "amount": 34567.89, "party": "真实催收公司"}
            ],
            "source": "真实银行股份有限公司发送至foo@example.com，文件位于/Users/example/Desktop/张三合同.pdf",
        }

        redacted = MODULE.redact_case(original)
        rendered = str(redacted)

        self.assertEqual(redacted["case_name"], "脱敏案例")
        self.assertEqual(redacted["amount_received"], 30000)
        self.assertEqual(redacted["balance_claims"][0]["amount"], 34567.89)
        self.assertEqual(redacted["entities"][0]["name"], "放款机构1")
        self.assertEqual(redacted["balance_claims"][0]["party"], "催收服务方1")
        for secret in ("张三", "110105199001011234", "13812345678", "6222021234567890123", "foo@example.com", "/Users/example"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(original["entities"][0]["name"], "真实银行股份有限公司")


if __name__ == "__main__":
    unittest.main()
