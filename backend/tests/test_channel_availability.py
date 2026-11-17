"""Public catalogue parsing, unavailable sources and cache behavior; no paid calls."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import channel_availability as availability


class AvailabilityTest(unittest.TestCase):
    @staticmethod
    def group(skus, service_type="video_gen"):
        return {"serviceType": service_type, "groupName": "Seedance", "models": [
            {"modelKey": "sd_2.5_special_v1", "children": [
                {"modelName": "有参考视频", "billingSkus": skus}]}]}

    def test_video_only_distinct_specs_and_missing_rate_is_not_100(self):
        sku = {"modelType": "VIDEO", "billingSkuKey": "720", "modelAlias": "720p", "configured": True, "price": {"status": 1}}
        groups = [self.group([sku, {**sku, "billingSkuKey": "1080", "modelAlias": "1080p", "available": False, "successRate": 0},
                              {**sku, "billingSkuKey": "image", "modelType": "IMAGE"}]),
                  self.group([sku], "digital_human"), self.group([sku], "llm")]
        rows = availability.parse_kyy_groups(groups)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["model"], "sd_2.5_special_v1")
        self.assertEqual(rows[0]["variant"], "有参考视频 / 720p")
        self.assertEqual(rows[0]["status"], "available")
        self.assertIsNone(rows[0]["success_rate"])
        self.assertEqual(rows[1]["status"], "unavailable")
        self.assertEqual(rows[1]["success_rate"], 0)

    def test_unconfigured_and_missing_status(self):
        skus = [{"modelType": "VIDEO", "billingSkuKey": str(i), **fields} for i, fields in enumerate([
            {"configured": False}, {"configured": True, "price": None},
            {"configured": True, "price": {"status": 0}}, {}, {"available": True, "successRate": 97.5}])]
        rows = availability.parse_kyy_groups([self.group(skus)])
        self.assertEqual([r["status"] for r in rows], ["unavailable", "unavailable", "unavailable", "unknown", "available"])
        self.assertEqual(rows[-1]["success_rate"], 97.5)

    def test_meaicc_zero_rate_no_samples_and_unreported_model(self):
        rows = availability.parse_meaicc({"success": True, "data": [{"model_name": m} for m in ["failed", "empty", "unknown"]],
            "model_availability": {"failed": {"success_rate": 0, "sample_count": 12, "avg_duration": 0, "recent_statuses": ["FAILED"]},
                                   "empty": {"success_rate": 100, "sample_count": 0}}})
        self.assertEqual(rows[0]["success_rate"], 0)
        self.assertEqual(rows[0]["status"], "listed")
        self.assertEqual(rows[0]["recent_statuses"], ["FAILED"])
        self.assertIsNone(rows[1]["success_rate"])
        self.assertIsNone(rows[2]["success_rate"])
        for invalid in [True, -1, "NaN", "inf", "invalid", 101]:
            self.assertIsNone(availability.numeric(invalid, 100))

    def test_cache_force_refresh_failure_keeps_old_data_and_other_source(self):
        service = availability.AvailabilityService()
        with patch.object(availability, "fetch_kyy", return_value={"records": [{"id": "kyy"}]}) as kyy, \
             patch.object(availability, "fetch_meaicc", return_value={"records": [{"id": "old"}]}) as meaicc:
            first = service.snapshot()
            service.snapshot()
            self.assertEqual(kyy.call_count, 1)
            # A caller cannot mutate the server's cached data.
            first["providers"][0]["records"].clear()
            self.assertEqual(len(service.snapshot()["providers"][0]["records"]), 1)
            meaicc.side_effect = requests.Timeout()
            updated = {p["id"]: p for p in service.snapshot(force=True)["providers"]}
            self.assertFalse(updated["kyy"]["stale"])
            self.assertTrue(updated["meaicc"]["stale"])
            self.assertEqual(updated["meaicc"]["records"], [{"id": "old"}])
            self.assertIsNotNone(updated["meaicc"]["last_success_at"])
            self.assertEqual(kyy.call_count, 2)

    def test_first_source_failure_is_unknown_and_cache_expires(self):
        service = availability.AvailabilityService()
        with patch.object(availability, "fetch_kyy", side_effect=requests.Timeout()) as kyy, \
             patch.object(availability, "fetch_meaicc", return_value={"records": []}):
            provider = service.snapshot()["providers"][0]
            self.assertTrue(provider["stale"])
            self.assertEqual(provider["records"], [])
            self.assertIsNone(provider["last_success_at"])
            service.refreshed -= 301
            service.snapshot()
            self.assertEqual(kyy.call_count, 2)

    def test_kyy_public_tier_and_pagination(self):
        sku = {"modelType": "VIDEO", "billingSkuKey": "720", "modelAlias": "720p", "available": True}
        responses = [
            {"code": 0, "data": [{"tierId": "member", "sortNo": 3}, {"tierId": "first", "sortNo": 1, "tierName": "贴牌"}]},
            {"code": 0, "data": {"records": [self.group([sku])], "pages": 2}},
            {"code": 0, "data": {"records": [self.group([{**sku, "billingSkuKey": "1080"}])], "pages": 2}},
        ]
        with patch.object(availability, "public_json", side_effect=responses) as call:
            result = availability.fetch_kyy()
        self.assertEqual(result["tier_name"], "贴牌")
        self.assertEqual(len(result["records"]), 2)
        request = call.call_args.kwargs["json"]
        self.assertEqual(request, {"tierId": "first", "page": 2, "pageSize": 100, "modelType": "video_gen"})
        self.assertNotIn("Authorization", call.call_args.args[0].headers)
        with patch.object(availability, "public_json", return_value={"code": 401}):
            with self.assertRaises(ValueError):
                availability.fetch_kyy()


if __name__ == "__main__":
    unittest.main()
