import asyncio
import json
import time
from typing import Any


class FakeRedis:
    """实现本轮服务所用 SET NX、TTL、GET/DEL 和 Lua 等效语义的 FakeRedis。"""

    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float | None]] = {}
        self.lists: dict[str, list[str]] = {}
        self.lock = asyncio.Lock()
        self.set_calls: list[tuple[str, dict[str, Any]]] = []
        self.eval_calls: list[tuple[str, tuple[Any, ...]]] = []

    def _purge(self, key: str) -> None:
        item = self.values.get(key)
        if item is not None and item[1] is not None and item[1] <= time.monotonic():
            self.values.pop(key, None)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False, **kwargs: Any) -> bool:
        async with self.lock:
            self._purge(key)
            self.set_calls.append((key, {'ex': ex, 'nx': nx, **kwargs}))
            if nx and key in self.values:
                return False
            self.values[key] = (value, time.monotonic() + ex if ex is not None else None)
            return True

    async def get(self, key: str) -> str | None:
        async with self.lock:
            self._purge(key)
            value = self.values.get(key)
            return value[0] if value else None

    async def exists(self, key: str) -> int:
        """按 Redis EXISTS 语义返回键数量。"""
        async with self.lock:
            self._purge(key)
            return int(key in self.values)

    async def delete(self, key: str) -> int:
        async with self.lock:
            self._purge(key)
            return int(self.values.pop(key, None) is not None)

    async def rpush(self, key: str, value: str) -> int:
        """追加队列元素。"""
        async with self.lock:
            self.lists.setdefault(key, []).append(value)
            return len(self.lists[key])

    async def lpop(self, key: str) -> str | None:
        """原子弹出队首元素。"""
        async with self.lock:
            values = self.lists.get(key, [])
            return values.pop(0) if values else None

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """按 Redis 负索引语义裁剪列表。"""
        async with self.lock:
            values = self.lists.get(key, [])
            size = len(values)
            first = start if start >= 0 else max(0, size + start)
            last = end if end >= 0 else size + end
            self.lists[key] = values[first : last + 1] if first <= last else []
            return True

    async def ttl(self, key: str) -> int:
        async with self.lock:
            self._purge(key)
            value = self.values.get(key)
            if value is None or value[1] is None:
                return -1
            return max(0, int(value[1] - time.monotonic()))

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:  # noqa: PLR0911, PLR0912
        async with self.lock:
            self.eval_calls.append((script, args))
            key = args[0]
            self._purge(key)
            if 'INCR' in script and 'EXPIRE' in script:
                current = int(self.values.get(key, ('0', None))[0]) + 1
                ttl = int(args[1])
                expiry = time.monotonic() + ttl
                self.values[key] = (str(current), expiry)
                return [current, ttl]
            if 'codeHash' in script and 'KEYS[3]' in script:
                value = self.values.get(key)
                tombstone_key = args[1]
                payload_key = args[2]
                if value is None:
                    self._purge(tombstone_key)
                    consumed = self.values.get(payload_key)
                    if consumed is not None:
                        try:
                            consumed_payload = json.loads(consumed[0])
                        except json.JSONDecodeError:
                            consumed_payload = None
                        if isinstance(consumed_payload, dict) and consumed_payload.get('codeHash') != args[3]:
                            return -3
                    return -4 if tombstone_key in self.values else None
                try:
                    payload = json.loads(value[0])
                except json.JSONDecodeError:
                    return -2
                if str(payload.get('version')) != str(args[4]) or payload.get('codeHash') != args[3]:
                    return -3
                self.values.pop(key, None)
                self.values[tombstone_key] = (str(args[5]), time.monotonic() + int(args[6]))
                self.values[payload_key] = (value[0], time.monotonic() + int(args[6]))
                return value[0]
            if 'codeHash' in script:
                value = self.values.get(key)
                if value is None:
                    return None
                try:
                    payload = json.loads(value[0])
                except json.JSONDecodeError:
                    return -2
                if str(payload.get('version')) != str(args[2]) or payload.get('codeHash') != args[1]:
                    return -3
                self.values.pop(key, None)
                return value[0]
            value = self.values.get(key)
            if value is None:
                return -1
            current = json.loads(value[0])
            expected = json.loads(args[2])
            if value[1] is None or value[1] <= time.monotonic():
                self.values.pop(key, None)
                return -5
            if str(current.get('version')) != str(args[1]):
                return -2
            if current.get('status') not in expected:
                return -3
            self.values[key] = (args[3], value[1])
            return 1
