from sqlalchemy import Column,Integer,String,ForeignKey,UniqueConstraint,Index
from ..config.database import Base
from ..config.settings import CONFIG
class Fragment(Base):
    __tablename__='session_fragments'
    __table_args__=(
        UniqueConstraint('source_id','session_key','position','revision',name='uq_fragment_revision'),
        Index('ix_fragment_lookup','source_id','session_key','position'),
    )
    id=Column(Integer,primary_key=True)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    session_key=Column(String(160),nullable=False)
    position=Column(Integer,nullable=False)
    revision=Column(Integer,nullable=False)
    chapter=Column(String(600),nullable=True)
    # alive=墓碑标记：False 表示该 (position,revision) 已被撤回
    alive=Column(Integer,nullable=False,default=1)
    client_ref=Column(String(160),nullable=False,default='')
    created_at=Column(String(40),nullable=False)
