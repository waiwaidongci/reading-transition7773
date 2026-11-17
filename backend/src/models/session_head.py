from sqlalchemy import Column,Integer,String,JSON,ForeignKey,UniqueConstraint
from ..config.database import Base
from ..config.settings import CONFIG
class SessionHead(Base):
    __tablename__='reading_session_heads'
    __table_args__=(UniqueConstraint('source_id','session_key',name='uq_session_head'),)
    id=Column(Integer,primary_key=True)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    session_key=Column(String(160),nullable=False)
    # 已接收的最高修订水位（含撤回）
    head_revision=Column(Integer,nullable=False,default=0)
    # draft=有未发布的工作修订；published=当前有效视图已发布
    state=Column(String(20),nullable=False,default='draft')
    # 已发布视图对应的最高修订；小于 head_revision 即存在未发布补传
    published_revision=Column(Integer,nullable=False,default=0)
    # 发布时的连续章节（仅位置连续段，缺口处断开）
    published_path=Column(JSON,nullable=False,default=list)
    # 最近一次重建所依据的水位；用于旧计算晚到守卫
    rebuilt_revision=Column(Integer,nullable=False,default=0)
    edge_count=Column(Integer,nullable=False,default=0)
    # 重建时冗余的结构信息，列表页免逐会话扫描片段
    segment_count=Column(Integer,nullable=False,default=0)
    gap_count=Column(Integer,nullable=False,default=0)
    position_count=Column(Integer,nullable=False,default=0)
    updated_at=Column(String(40),nullable=False)
