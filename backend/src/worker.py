import json,time,logging
from redis import Redis
from sqlalchemy import select
from .config.database import Session
from .config.settings import REDIS_URL,ARTIFACT_DIR
from .models.run import Run
from .models import source,record,user,note,audit
from .services.algorithm import calculate
from .services.audit import log
from .services.export import csv_response
from .services.rebuild import process_outbox
queue=Redis.from_url(REDIS_URL)
ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
def execute(id):
    with Session() as db:
        r=db.get(Run,id)
        if not r or r.state!='queued':return
        r.state='running';db.commit()
        try:
            # 计数依据来自冻结快照；排队后的补传/撤回不影响本次结果
            global_base=(r.snapshot or {}).get('frozen_global_base')
            result=calculate(r.snapshot['records'],r.parameters,global_base=global_base)
            json.dumps(result,allow_nan=False)
            r.result=result;r.state='completed'
            response=csv_response(result,'run.csv')
            (ARTIFACT_DIR/f'run-{r.id}.csv').write_bytes(response.body)
            log(db,'worker','run.completed',r.id)
        except Exception as e:
            logging.exception('analysis failed');r.state='failed';r.error=str(e)[:2000]
            log(db,'worker','run.failed',r.id,r.error)
        db.commit()
def drain_outbox():
    try:
        with Session() as db:process_outbox(db)
    except Exception:logging.exception('outbox rebuild failed; will retry')
def main():
    while True:
        (ARTIFACT_DIR/'heartbeat').write_text(str(time.time()))
        # 每轮先处理片段重建发件箱（含崩溃后未完成条目），再取分析任务
        drain_outbox()
        value=queue.blpop('analysis:queue',timeout=2)
        if value:execute(int(value[1]))
if __name__=='__main__':main()
