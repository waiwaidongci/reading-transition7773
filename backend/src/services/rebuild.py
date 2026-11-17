"""全局边计数（仅完整已发布会话的物化边）与发件箱重建。

- 重建按会话进行：补片/撤回时删除该会话旧边、写入新边。
- 条件守卫：仅当 head.head_revision 与发件箱水位一致时落边；水位落后则抬升到最新再处理，
  旧计算晚到永不混用。
- 全局基率只统计 published 会话的边；draft 会话的边仅供页面预览，不进入任何研究计数。
- 全局边计数随边替换增量可得（按边表聚合），十万会话下不做全量会话重算。
"""
from sqlalchemy import select
from ..models.session_head import SessionHead
from ..models.session_edge import SessionEdge
from ..models.rebuild import RebuildOutbox
from .fragments import effective_view,edges_from_view,contiguous_segments,gaps as compute_gaps
from .audit import log

def _published_edge_query(db,source_id=None):
    stmt=(select(SessionEdge.to_chapter,SessionEdge.from_chapter)
          .join(SessionHead,SessionEdge.head_id==SessionHead.id)
          .where(SessionHead.state=='published'))
    if source_id is not None:stmt=stmt.where(SessionEdge.source_id==source_id)
    return stmt

def global_base_rates(db,source_id=None):
    """全局基率：到达章节 b 的边次数 / 全部边数（仅已发布会话物化边）。
    聚合下推到 SQL，十万会话下不把边全量载入应用层。"""
    rows=db.execute(_published_edge_query(db,source_id)).all()
    incoming={};outgoing={};total=0
    for to_ch,from_ch in rows:
        incoming[to_ch]=incoming.get(to_ch,0)+1
        outgoing[from_ch]=outgoing.get(from_ch,0)+1
        total+=1
    rates={b:(c/total if total else 0.0) for b,c in incoming.items()}
    return {'total_edges':total,'incoming':incoming,'outgoing':outgoing,'base_rate':rates}

def _replace_session_edges(db,head,view):
    old=db.scalars(select(SessionEdge).where(SessionEdge.head_id==head.id)).all()
    new_edges=edges_from_view(view)
    for e in old:db.delete(e)
    db.flush()  # 先落删除，避免与新边的 (head_id,position) 唯一约束冲突
    for pos,a,b in new_edges:
        db.add(SessionEdge(head_id=head.id,source_id=head.source_id,position=pos,
                           from_chapter=a,to_chapter=b,built_revision=head.head_revision))
    return len(old),len(new_edges)

def process_outbox(db,limit=100,max_rounds=50):
    """排空发件箱；返回处理条目数。worker 周期调用，崩溃后未删条目自动重试。

    每轮最多取 limit 条并循环到无积压；单条重建异常时回滚该轮、保留条目下轮再试，
    避免一条坏数据长期阻塞其他会话的重建。"""
    processed=0
    for _ in range(max_rounds):
        items=db.scalars(select(RebuildOutbox).order_by(RebuildOutbox.id).limit(limit)).all()
        if not items:break
        failed=False
        for item in items:
            head=db.get(SessionHead,item.head_id)
            if not head:
                db.delete(item);processed+=1;continue
            # 守卫：水位落后说明本条是旧计算晚到，抬升到最新水位后再重建，绝不混用旧视图
            if item.pending_revision<head.head_revision:
                item.pending_revision=head.head_revision
            if item.pending_revision>head.head_revision:
                # 理论不可能（水位不会回退）；保守跳过等下一轮
                continue
            try:
                view=effective_view(db,head)
                old_n,new_n=_replace_session_edges(db,head,view)
                head.rebuilt_revision=head.head_revision
                head.edge_count=new_n
                head.position_count=len(view)
                head.segment_count=len(contiguous_segments(view))
                head.gap_count=len(compute_gaps(view))
                item.attempts+=1
                db.delete(item)
                log(db,'worker','session.rebuilt',head.id,'rev=%d edges %d->%d state=%s'%(head.head_revision,old_n,new_n,head.state))
                processed+=1
            except Exception as e:
                db.rollback()
                # 记录失败原因并提交，坏条目保留在发件箱，下轮重试
                fresh=db.get(RebuildOutbox,item.id)
                if fresh is not None:
                    fresh.attempts+=1;fresh.last_error=str(e)[:500];db.commit()
                failed=True
                break
        if not failed:
            db.commit()
        if len(items)<limit:break
    return processed
