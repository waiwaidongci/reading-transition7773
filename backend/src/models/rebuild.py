from sqlalchemy import Column,Integer,String,Text
from ..config.database import Base
class RebuildOutbox(Base):
    """事务性发件箱：与片段接收同事务提交，worker 处理后删除。崩溃后可重新投递。"""
    __tablename__='rebuild_outbox'
    id=Column(Integer,primary_key=True)
    head_id=Column(Integer,nullable=False)
    # 入箱时会话水位；worker 仅在仍为最新水位时落边，旧计算晚到不混用
    pending_revision=Column(Integer,nullable=False)
    attempts=Column(Integer,nullable=False,default=0)
    last_error=Column(Text,default='')
    created_at=Column(String(40),nullable=False)
class IdempotencyLedger(Base):
    """客户端幂等键：同键重试返回首次结果，不重复计数。"""
    __tablename__='idempotency_ledger'
    id=Column(Integer,primary_key=True)
    idempotency_key=Column(String(200),unique=True,nullable=False)
    response=Column(Text,nullable=False)
    created_at=Column(String(40),nullable=False)
