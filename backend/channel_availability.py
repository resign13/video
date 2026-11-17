"""Read the same public video catalogues used by the two provider status pages."""
import copy
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests


REFRESH_SECONDS = 300
MEAICC_SOURCE = "https://api.meaicc.com/pricing"
KYY_SOURCE = "https://www.globalaiopc.com/zh/default/allModels"
KYY_PUBLIC_API = "https://zcbservice.aizfw.cn/kyyAccountCenter"
TIMEOUT = (5, 15)


def numeric(value, maximum=None):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(result) or result < 0 or (maximum is not None and result > maximum):
        return None
    return result


def public_json(session, method, url, **kwargs):
    response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid provider response")
    return data


def parse_meaicc(data):
    if data.get("success") is False or not isinstance(data.get("data"), list):
        raise ValueError("Invalid MEAICC catalogue")
    stats = data.get("model_availability") or {}
    records = []
    for item in data["data"]:
        name = item.get("model_name")
        if not name:
            continue
        status = stats.get(name) or {}
        sample_count = numeric(status.get("sample_count"))
        records.append({
            "id": name, "model": name, "group": "MEAICC", "variant": "",
            "description": item.get("description") or "",
            # Being listed is separate from a promise that a new request will succeed.
            "status": "listed", "success_rate": numeric(status.get("success_rate"), 100) if sample_count != 0 else None,
            "sample_count": sample_count, "avg_duration_seconds": numeric(status.get("avg_duration")),
            "recent_statuses": [str(value).upper() for value in (status.get("recent_statuses") or [])][-10:],
            "window": "24 小时",
        })
    return records


def parse_kyy_groups(groups):
    records, seen = [], set()

    def walk(node, group, model, path):
        for sku in node.get("billingSkus") or []:
            if str(sku.get("modelType", "")).upper() not in ("VIDEO", "VIDEO_GEN"):
                continue
            identity = sku.get("billingSkuKey") or sku.get("systemModelId")
            if not identity or identity in seen:
                continue
            seen.add(identity)
            available = sku.get("available")
            if not isinstance(available, bool):
                price = sku.get("price")
                if sku.get("configured") is False:
                    available = False
                elif sku.get("configured") is True and price is None:
                    available = False
                elif sku.get("configured") is True and isinstance(price, dict) and "status" in price:
                    available = str(price["status"]) != "0"
                else:
                    available = None
            records.append({
                "id": identity, "model": model, "group": group,
                "variant": " / ".join(path + [sku.get("modelAlias") or sku.get("modelName") or identity]),
                "description": sku.get("modelDesc") or sku.get("description") or "",
                "status": "available" if available is True else ("unavailable" if available is False else "unknown"),
                # The official page defaults a missing rate to 100. Keep it unknown here.
                "success_rate": numeric(sku.get("successRate"), 100), "sample_count": None,
                "avg_duration_seconds": None, "recent_statuses": [], "window": "官方未注明统计周期",
            })
        for child in node.get("children") or []:
            walk(child, group, model, path + [child.get("modelName") or child.get("modelKey") or ""])

    for group in groups:
        if str(group.get("serviceType", "")).lower() != "video_gen":
            continue
        for node in group.get("models") or []:
            walk(node, group.get("groupName") or "", node.get("modelKey") or node.get("modelName") or "", [])
    return records


def fetch_meaicc():
    with requests.Session() as session:
        data = public_json(session, "GET", "https://api.meaicc.com/api/pricing")
    return {"records": parse_meaicc(data)}


def kyy_data(payload):
    if payload.get("code") not in (0, 200):
        raise ValueError("KYY public catalogue unavailable")
    return payload.get("data")


def fetch_kyy():
    with requests.Session() as session:
        session.headers.update({"platform": "6", "oemCode": "dj", "Content-Type": "application/json"})
        tiers = kyy_data(public_json(session, "POST", KYY_PUBLIC_API + "/account/admin/opc/price-tier/public-list",
                                     json={"page": 1, "pageSize": 50}))
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("No public KYY tier")
        valid_tiers = [item for item in tiers if item.get("tierId")]
        if not valid_tiers:
            raise ValueError("No public KYY tier")
        tier = min(valid_tiers, key=lambda item: item.get("sortNo") or 0)
        groups, page = [], 1
        while True:
            data = kyy_data(public_json(session, "POST", KYY_PUBLIC_API + "/account/admin/opc/price-tier/model-tree",
                json={"tierId": tier["tierId"], "page": page, "pageSize": 100, "modelType": "video_gen"}))
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError("Invalid KYY video catalogue")
            groups.extend(data["records"])
            if page >= int(data.get("pages") or 1):
                break
            page += 1
    return {"records": parse_kyy_groups(groups), "tier_name": tier.get("tierName") or ""}


class AvailabilityService:
    def __init__(self):
        self.lock = threading.Lock()
        self.providers = {}
        self.refreshed = None

    def snapshot(self, force=False):
        with self.lock:
            if force or self.refreshed is None or time.monotonic() - self.refreshed >= REFRESH_SECONDS:
                fetchers = {"kyy": ("客易云", KYY_SOURCE, fetch_kyy), "meaicc": ("MEAICC", MEAICC_SOURCE, fetch_meaicc)}
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = {key: executor.submit(config[2]) for key, config in fetchers.items()}
                    for key, (name, source, _) in fetchers.items():
                        provider = {"id": key, "name": name, "source_url": source, "checked_at": time.time()}
                        try:
                            provider.update(futures[key].result())
                            provider.update(last_success_at=time.time(), stale=False, error="")
                        except (requests.RequestException, ValueError, TypeError, KeyError):
                            previous = self.providers.get(key, {})
                            provider.update(records=previous.get("records", []), tier_name=previous.get("tier_name", ""),
                                last_success_at=previous.get("last_success_at"), stale=True, error="获取失败，请稍后刷新")
                        self.providers[key] = provider
                self.refreshed = time.monotonic()
            return {"providers": copy.deepcopy(list(self.providers.values())), "refresh_seconds": REFRESH_SECONDS}


def status_text(row):
    return {"available": "可用", "unavailable": "维护中", "listed": "官方在列", "unknown": "未知"}.get(row.get("status"), "未知")


SERVICE = AvailabilityService()
