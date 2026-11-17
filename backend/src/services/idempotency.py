"""客户端幂等：同 idempotency_key 的重试返回首次响应，不重复落片段、不重复计数。"""
import json
from sqlalchemy import select
from ..models.rebuild import IdempotencyLedger
from ..utils.serialization import now
def replay(db,key):
    if not key:return None
    led=db.scalar(select(IdempotencyLedger).where(IdempotencyLedger.idempotency_key==key))
    if led:return json.loads(led.response)
    return None
def store(db,key,payload):
    if not key:return
    db.add(IdempotencyLedger(idempotency_key=key,response=json.dumps(payload,ensure_ascii=False),created_at=now()))
