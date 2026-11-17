from sqlalchemy import Column,Integer,String,ForeignKey,UniqueConstraint,Index
from ..config.database import Base
from ..config.settings import CONFIG
class SessionEdge(Base):
    """按会话物化的连续相邻边；缺口两侧不连边。补片/撤回时整会话替换。"""
    __tablename__='session_edges'
    __table_args__=(
        UniqueConstraint('head_id','position',name='uq_edge_position'),
        Index('ix_edge_pair','from_chapter','to_chapter'),
    )
    id=Column(Integer,primary_key=True)
    head_id=Column(Integer,ForeignKey('reading_session_heads.id'),nullable=False)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    position=Column(Integer,nullable=False)
    from_chapter=Column(String(600),nullable=False)
    to_chapter=Column(String(600),nullable=False)
    # 该边依据的会话修订水位；旧计算晚到时用于守卫
    built_revision=Column(Integer,nullable=False,default=0)
