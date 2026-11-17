from sqlalchemy import select
from fastapi import HTTPException
from redis import Redis
from ..config.settings import REDIS_URL
from ..models.run import Run
from ..models.session_head import SessionHead
from ..utils.serialization import row,now
from .sources import source_or_404,list_records
from .rebuild import global_base_rates
from .domain_validation import validate_parameters
from .audit import log
queue=Redis.from_url(REDIS_URL)
def get_run(db,id):
    r=db.get(Run,id)
    if not r:raise HTTPException(404,'未找到分析任务')
    return r
def _published_fragment_records(db,source_id):
    """只取完整已发布会话；published_path 是按连续段切分的章节列表。
    每个连续段作为该会话内一条路径，缺口天然断开，不跨缺口连边。"""
    heads=db.scalars(select(SessionHead).where(SessionHead.source_id==source_id,SessionHead.state=='published')).all()
    records=[];frozen_sessions=[]
    for h in heads:
        segments=h.published_path or []
        if not segments:continue
        # 完整=无缺口（单段）；多段意味着仍有缺口，不满足“完整已发布”，不纳入研究
        if len(segments)!=1:continue
        path=segments[0]
        records.append({'values':{'session':h.session_key,'path':'>'.join(path)}})
        frozen_sessions.append({'session':h.session_key,'revision':h.published_revision,'path':path})
    return records,frozen_sessions
def create_run(db,user,data):
    s=source_or_404(db,data.source_id)
    legacy=list_records(db,s.id)  # 旧整行数据，保持可读、可计算
    frag_records,frozen_sessions=_published_fragment_records(db,s.id)
    records=legacy+frag_records
    if not records:raise HTTPException(422,'至少录入1个完整阅读会话（整行或完整已发布片段会话）后才能执行')
    try: params=validate_parameters(data.parameters)
    except ValueError as e:raise HTTPException(422,str(e))
    # 计数依据：冻结时刻的已发布边表全局基率；排队后补传不改变本快照
    base=global_base_rates(db,s.id)
    r=Run(source_id=s.id,name=data.name,parameters=params,
          snapshot={'source':row(s),'records':records,
                    'legacy_record_count':len(legacy),
                    'fragment_session_count':len(frag_records),
                    'frozen_fragment_sessions':frozen_sessions,
                    'frozen_global_base':base,
                    'frozen_at':now()},
          created_at=now(),state='queued')
    db.add(r);db.flush();log(db,user,'run.queued',r.id,data.name);db.commit()
    try:queue.rpush('analysis:queue',r.id)
    except Exception:
        r.state='failed';r.error='队列暂不可用，请重新创建任务';db.commit();raise HTTPException(503,r.error)
    return row(r)
def list_runs(db):
    return [{k:v for k,v in row(r).items() if k not in ('snapshot','result')} for r in db.scalars(select(Run).order_by(Run.id.desc()))]
