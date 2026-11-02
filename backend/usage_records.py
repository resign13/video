"""Generation accounting retained independently of temporary video files."""
import calendar
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import sqlite3
import time
from urllib.parse import urlparse

CN_TIME = timezone(timedelta(hours=8))
KYY_MODES = {"luxvid_videos_async", "zcb_veo_videos_async", "seedance25_videos_async",
             "seedance_model_center_videos_async", "kyy_model_center_videos_async", "seedance_special_videos_async"}


def expires_after_three_months(timestamp):
    date = datetime.fromtimestamp(timestamp, CN_TIME)
    month = date.year * 12 + date.month - 1 + 3
    year, index = divmod(month, 12)
    return date.replace(year=year, month=index + 1,
                        day=min(date.day, calendar.monthrange(year, index + 1)[1])).timestamp()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def mask_key(value):
    value = str(value or "")
    if not value:
        return "未配置 Key"
    return value[:6] + "…" + value[-4:] if len(value) > 12 else "已记录（隐藏）"


def extract_provider_usage(payload, request_mode, existing_unit=None):
    values = {}
    for candidate in (payload, payload.get("data"), payload.get("result")):
        if isinstance(candidate, dict):
            values.update({key: value for key, value in candidate.items() if value is not None})
    fields = {}
    for key in ("actualDuration", "actual_duration"):
        actual = number(values.get(key))
        if actual is not None and actual > 0:
            fields["provider_video_seconds"] = float(actual)
            break
    for key in ("amount", "cost", "fee"):
        amount = number(values.get(key))
        if amount is not None:
            unit = values.get("currency") or values.get("cost_unit") or existing_unit
            if not unit:
                unit = "积分" if key == "amount" and request_mode in {
                    "seedance25_videos_async", "seedance_model_center_videos_async", "kyy_model_center_videos_async"
                } else "渠道原始单位"
            fields.update(provider_cost_amount=str(amount), provider_cost_unit=str(unit)[:40])
            break
    if values.get("status") is not None:
        fields["provider_status"] = str(values["status"]).lower().split(":", 1)[0].strip()
    return fields


class UsageRecords:
    def __init__(self, database_path):
        self.database_path = database_path

    @staticmethod
    def initialize(connection):
        connection.execute("""CREATE TABLE IF NOT EXISTS generation_usage (
            task_id TEXT PRIMARY KEY, created_ts REAL NOT NULL, expires_ts REAL NOT NULL,
            provider TEXT NOT NULL, provider_name TEXT NOT NULL, api_key_snapshot TEXT NOT NULL,
            key_label TEXT NOT NULL, model TEXT NOT NULL, requested_seconds REAL NOT NULL,
            actual_seconds REAL, cost_amount TEXT, cost_unit TEXT,
            status TEXT NOT NULL, provider_status TEXT NOT NULL, remote_task_id TEXT NOT NULL,
            updated_ts REAL NOT NULL)""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_generation_usage_expires ON generation_usage(expires_ts)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_generation_usage_created ON generation_usage(created_ts DESC)")

    def save(self, connection, task):
        if not task.get("usage_tracking"):
            return
        created = float(task["created_ts"])
        if expires_after_three_months(created) <= time.time():
            return
        host = urlparse(task.get("api_base", "")).hostname or "unknown"
        provider = "kyy" if task.get("request_mode") in KYY_MODES else host
        name = {"kyy": "客易云", "api.meaicc.com": "MEAICC", "api.sudashuiapi.com": "苏打水",
                "api.aiclub.cv": "AIClub", "zexitongxue.com": "泽熙同学"}.get(provider, host)
        requested = number(task.get("seconds"))
        connection.execute("""INSERT INTO generation_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
            actual_seconds=COALESCE(excluded.actual_seconds,generation_usage.actual_seconds),
            cost_amount=COALESCE(excluded.cost_amount,generation_usage.cost_amount),
            cost_unit=COALESCE(excluded.cost_unit,generation_usage.cost_unit),
            status=excluded.status, provider_status=excluded.provider_status,
            remote_task_id=excluded.remote_task_id, updated_ts=excluded.updated_ts""",
            (task["id"], created, expires_after_three_months(created), provider, name,
             "" if task.get("usage_key_unknown") else task.get("api_key", ""),
             "旧任务 Key 未留存" if task.get("usage_key_unknown") else mask_key(task.get("api_key")), task.get("model_family", ""),
             float(requested) if requested is not None else 0, task.get("provider_video_seconds"),
             task.get("provider_cost_amount"), task.get("provider_cost_unit"), task.get("status", "queued"),
             task.get("provider_status", ""), str(task.get("remote_task_id") or ""), time.time()))

    def connect(self):
        connection = sqlite3.connect(str(self.database_path), timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def purge(self, now=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("DELETE FROM generation_usage WHERE expires_ts<=?", (time.time() if now is None else now,))

    def list(self, provider="kyy", key="", start="", end="", page=1, page_size=50):
        conditions, parameters = ["expires_ts> ?"], [time.time()]
        if provider:
            conditions.append("provider=?")
            parameters.append(provider)
        if key:
            conditions.append("key_label LIKE ?")
            parameters.append("%" + key + "%")
        for value, operator, next_day in ((start, ">=", False), (end, "<", True)):
            if value:
                date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=CN_TIME)
                if next_day:
                    date += timedelta(days=1)
                conditions.append(f"created_ts{operator}?")
                parameters.append(date.timestamp())
        if start and end and start > end:
            raise ValueError("开始日期不能晚于结束日期")
        where = " AND ".join(conditions)
        with closing(self.connect()) as connection:
            # Only explicit public columns may leave the server. The full key stays in SQLite.
            columns = "task_id,created_ts,expires_ts,provider,provider_name,key_label,model,requested_seconds,actual_seconds,cost_amount,cost_unit,status,provider_status,remote_task_id"
            rows = connection.execute(f"SELECT {columns} FROM generation_usage WHERE {where} ORDER BY created_ts DESC,task_id LIMIT ? OFFSET ?",
                                      parameters + [page_size, (page - 1) * page_size]).fetchall()
            total = connection.execute(f"SELECT COUNT(*) FROM generation_usage WHERE {where}", parameters).fetchone()[0]
            aggregate = connection.execute(f"SELECT requested_seconds,actual_seconds,cost_amount,cost_unit,status,provider_status FROM generation_usage WHERE {where}", parameters)
            seconds, generated, priced, totals = 0.0, 0, 0, {}
            for row in aggregate:
                if row["provider_status"] in ("completed", "success", "succeeded", "done") or row["status"] == "completed":
                    generated += 1
                    seconds += row["actual_seconds"] if row["actual_seconds"] is not None else row["requested_seconds"]
                if row["cost_amount"] is not None:
                    priced += 1
                    unit = row["cost_unit"] or "渠道原始单位"
                    totals[unit] = totals.get(unit, Decimal(0)) + Decimal(row["cost_amount"])
            providers = connection.execute("SELECT DISTINCT provider,provider_name FROM generation_usage WHERE expires_ts>? ORDER BY provider_name", (time.time(),)).fetchall()
        return {"records": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size,
                "providers": [dict(row) for row in providers],
                "summary": {"generated_count": generated, "generated_seconds": round(seconds, 3), "with_cost": priced,
                            "without_cost": total - priced, "cost_totals": [{"unit": unit, "amount": str(amount)} for unit, amount in sorted(totals.items())]}}
