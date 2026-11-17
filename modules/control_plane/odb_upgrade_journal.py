"""Strict, single-writer upgrade history. Never reads or changes an ODB."""
from __future__ import annotations

import json
import os
from pathlib import Path

from modules.common.json_io import save_json_mapping


class UpgradeJournal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._owner = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.with_suffix(self.path.suffix + '.lock').open('a+b')
        try:
            if stream.tell() == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            stream.close()
            raise
        self._owner = stream

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        # A damaged journal is not empty history.
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or payload.get('schemaVersion') != 1:
            raise ValueError('升级记录版本无效')
        records = payload.get('operations')
        if not isinstance(records, list):
            raise ValueError('升级记录列表无效')
        ids, requests = set(), set()
        for item in records:
            self._validate(item)
            if item['operationId'] in ids or item['clientRequestId'] in requests:
                raise ValueError('升级记录含重复标识')
            ids.add(item['operationId'])
            requests.add(item['clientRequestId'])
        return records

    @staticmethod
    def _validate(item):
        if not isinstance(item, dict) or any(key.startswith('_') for key in item):
            raise ValueError('升级记录结构无效')
        if item.get('schemaVersion') != 1 or item.get('kind') != 'odb.upgrade':
            raise ValueError('升级记录类型无效')
        for field in ('operationId', 'clientRequestId', 'createdAt', 'updatedAt'):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError('升级记录标识或时间无效')
        if type(item.get('version')) is not int or item['version'] < 1:
            raise ValueError('升级记录修订号无效')
        if item.get('status') not in {'queued', 'running', 'cancelling', 'failed', 'cancelled', 'succeeded'}:
            raise ValueError('升级记录状态无效')
        preview, progress = item.get('preview'), item.get('progress')
        if not isinstance(preview, dict) or not isinstance(progress, dict):
            raise ValueError('升级记录预览或进度无效')
        entries = preview.get('entries')
        if not isinstance(entries, list) or not entries or any(
            not isinstance(entry, dict) or not isinstance(entry.get('sourcePath'), str) or not entry['sourcePath']
            for entry in entries
        ):
            raise ValueError('升级记录源文件无效')
        if (type(progress.get('completed')) is not int or type(progress.get('total')) is not int
            or progress['total'] != len(entries) or not 0 <= progress['completed'] <= progress['total']
            or not isinstance(progress.get('currentFile'), str)):
            raise ValueError('升级记录进度越界')
        if not isinstance(item.get('results'), list) or any(not isinstance(r, dict) for r in item['results']):
            raise ValueError('升级记录回执无效')
        expected = {os.path.normcase(str(Path(entry['sourcePath']).resolve())) for entry in entries}
        returned = set()
        for receipt in item['results']:
            if not isinstance(receipt.get('source_path'), str) or not isinstance(receipt.get('status'), str):
                raise ValueError('升级记录回执字段无效')
            key = os.path.normcase(str(Path(receipt['source_path']).resolve()))
            if key not in expected or key in returned:
                raise ValueError('升级记录回执含其他文件或重复文件')
            returned.add(key)
        if item['status'] == 'succeeded' and (returned != expected or any(r['status'] != 'upgraded' for r in item['results'])):
            raise ValueError('升级成功记录缺少完整成功回执')
        if not isinstance(item.get('logs'), list) or any(not isinstance(s, str) for s in item['logs']):
            raise ValueError('升级记录日志无效')
        if item.get('error') is not None and (not isinstance(item['error'], dict)
            or not isinstance(item['error'].get('code'), str) or not isinstance(item['error'].get('message'), str)):
            raise ValueError('升级记录错误信息无效')

    def save(self, records: list[dict]):
        if self._owner is None:
            raise OSError('升级记录写入锁已关闭')
        save_json_mapping(self.path, {'schemaVersion': 1, 'operations': records})

    def close(self):
        if self._owner is not None:
            self._owner.close()  # OS also releases ownership after a process crash.
            self._owner = None
