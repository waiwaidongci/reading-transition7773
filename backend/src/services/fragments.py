"""片段接收、撤回与按最新有效修订重建会话。

修订语义：
- 片段以 (source, session, position, revision) 唯一；同版本异值拒收（409）。
- 高修订覆盖同位置旧值；tombstone（撤回）使该位置在该修订起失效。
- 有效视图只取每个位置“最新且存活”的修订；按位置排序。
接缝规则：仅当位置 pos 与 pos+1 都有效时才连一条边；缺口两侧不连边。
崩溃恢复：片段/会话头/发件箱在同一事务提交；worker 处理发件箱后才删条。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models.fragment import Fragment
from ..models.session_head import SessionHead
from ..models.session_edge import SessionEdge
from ..models.rebuild import RebuildOutbox
from ..utils.serialization import now
from .sources import source_or_404
from .audit import log
from . import idempotency as idem

MAX_POSITION=100000
MAX_CHAPTER=600

def _validate_chapter(value):
    if not isinstance(value,str):
        raise HTTPException(422,'章节内容必须是字符串')
    value=value.strip()
    if not value or len(value)>MAX_CHAPTER:
        raise HTTPException(422,'章节内容不能为空且最多 %d 字符'%MAX_CHAPTER)
    return value

def _get_or_create_head(db,source_id,session_key):
    head=db.scalar(select(SessionHead).where(SessionHead.source_id==source_id,SessionHead.session_key==session_key))
    created=False
    if not head:
        head=SessionHead(source_id=source_id,session_key=session_key,head_revision=0,
                         state='draft',published_revision=0,published_path=[],
                         rebuilt_revision=0,edge_count=0,updated_at=now())
        db.add(head);db.flush();created=True
    return head,created

def _enqueue(db,head_id,revision):
    # 同会话已有未处理条目则提升其水位，避免堆积；worker 按最新水位重建
    existing=db.scalar(select(RebuildOutbox).where(RebuildOutbox.head_id==head_id))
    if existing:
        existing.pending_revision=max(existing.pending_revision,revision)
    else:
        db.add(RebuildOutbox(head_id=head_id,pending_revision=revision,attempts=0,last_error='',created_at=now()))

def _apply_op(db,head,position,revision,chapter,tombstone,client_ref):
    if not isinstance(position,int) or position<0 or position>MAX_POSITION:
        raise HTTPException(422,'位置 position 需为 0 至 %d 的整数'%MAX_POSITION)
    if not isinstance(revision,int) or revision<1:
        raise HTTPException(422,'修订号 revision 需为不小于 1 的整数')
    dup=db.scalar(select(Fragment).where(Fragment.source_id==head.source_id,
                                         Fragment.session_key==head.session_key,
                                         Fragment.position==position,
                                         Fragment.revision==revision))
    if dup:
        same=(dup.alive==0) if tombstone else (dup.alive==1 and dup.chapter==chapter)
        if not same:
            raise HTTPException(409,'位置 %d 修订 %d 已存在不同内容，同版本异值拒收'%(position,revision))
        return False  # 幂等：同版本同值/同撤回，重复投递不计数
    # 同修订可覆盖多个位置；每位置取最高修订的视图天然保证乱序旧值不覆盖新值
    if tombstone:
        db.add(Fragment(source_id=head.source_id,session_key=head.session_key,position=position,
                        revision=revision,chapter=None,alive=0,client_ref=client_ref,created_at=now()))
    else:
        db.add(Fragment(source_id=head.source_id,session_key=head.session_key,position=position,
                        revision=revision,chapter=chapter,alive=1,client_ref=client_ref,created_at=now()))
    head.head_revision=max(head.head_revision,revision)
    head.state='draft'
    head.updated_at=now()
    return True

def ingest(db,user,source_id,payload):
    """payload: {session, operations:[{position,revision,chapter?,tombstone?}], idempotency_key?}"""
    source_or_404(db,source_id)
    idem_key=(payload.get('idempotency_key') or '').strip()
    cached=idem.replay(db,idem_key)
    if cached is not None:
        cached['replayed']=True
        return cached
    session_key=payload.get('session')
    if not isinstance(session_key,str) or not session_key.strip() or len(session_key)>160:
        raise HTTPException(422,'会话编号 session 不能为空且最多160字符')
    session_key=session_key.strip()
    ops=payload.get('operations')
    if not isinstance(ops,list) or not ops or len(ops)>2000:
        raise HTTPException(422,'operations 需为 1–2000 条片段操作')
    head,_=_get_or_create_head(db,source_id,session_key)
    changed=False
    norm=[]
    for op in ops:
        if not isinstance(op,dict):raise HTTPException(422,'每个操作必须是对象')
        tombstone=bool(op.get('tombstone',False))
        chapter=None if tombstone else _validate_chapter(op.get('chapter'))
        norm.append((op.get('position'),op.get('revision'),chapter,tombstone))
    # 批内同 (position,revision) 冲突先拦截
    seen=set()
    for position,revision,_,_ in norm:
        key=(position,revision)
        if key in seen:raise HTTPException(422,'批内存在重复的位置/修订组合 %s'%(key,))
        seen.add(key)
    for position,revision,chapter,tombstone in norm:
        if _apply_op(db,head,position,revision,chapter,tombstone,idem_key):
            changed=True
    if changed:
        db.flush()
        _enqueue(db,head.id,head.head_revision)
        log(db,user,'fragment.ingested',head.id,'%s rev=%d ops=%d'%(session_key,head.head_revision,len(norm)))
    result={'session':session_key,'head_revision':head.head_revision,'state':head.state,
            'applied':changed,'queued_rebuild':changed,'replayed':False}
    idem.store(db,idem_key,result)
    try:
        db.commit()
    except IntegrityError:
        # 并发提交：同幂等键或同 (position,revision) 被另一事务抢先落库
        db.rollback()
        if idem_key:
            cached=idem.replay(db,idem_key)
            if cached is not None:
                cached['replayed']=True;return cached
        raise HTTPException(409,'并发修订冲突：相同位置/修订已被接收，请核对后用更高修订号重试')
    return result

def effective_view(db,head):
    """返回每个位置最新且存活的章节：{position: chapter}，依据全部已接收片段。"""
    frags=db.scalars(select(Fragment).where(Fragment.source_id==head.source_id,
                                            Fragment.session_key==head.session_key)).all()
    latest={}
    for f in frags:
        cur=latest.get(f.position)
        if cur is None or f.revision>cur[0]:
            latest[f.position]=(f.revision,f.alive,f.chapter)
    return {pos:chapter for pos,(rev,alive,chapter) in latest.items() if alive==1}

def contiguous_segments(view):
    """把有效位置切成严格连续段；每段返回章节有序列表。缺口处分段。"""
    if not view:return []
    positions=sorted(view)
    segments=[];current=[view[positions[0]]]
    for prev,pos in zip(positions,positions[1:]):
        if pos==prev+1:
            current.append(view[pos])
        else:
            segments.append(current);current=[view[pos]]
    segments.append(current)
    return segments

def edges_from_view(view):
    """仅位置连续的相邻章节连边；缺口两侧不连。返回 [(position, from, to), ...]。"""
    out=[]
    for pos in sorted(view):
        nxt=pos+1
        if nxt in view:
            out.append((pos,view[pos],view[nxt]))
    return out

def gaps(view):
    """返回缺口描述：每个缺失位置区间。"""
    if not view:return []
    positions=sorted(view);gaps_list=[]
    for prev,pos in zip(positions,positions[1:]):
        if pos>prev+1:
            gaps_list.append({'after_position':prev,'missing_from':prev+1,'missing_to':pos-1})
    return gaps_list

def list_session_heads(db,source_id):
    source_or_404(db,source_id)
    heads=db.scalars(select(SessionHead).where(SessionHead.source_id==source_id).order_by(SessionHead.id)).all()
    # 十万会话列表：直接读重建时冗余的结构计数，不逐会话扫描片段
    out=[]
    for h in heads:
        out.append({'id':h.id,'session':h.session_key,'head_revision':h.head_revision,
                    'published_revision':h.published_revision,'state':h.state,
                    'rebuilt_revision':h.rebuilt_revision,'edge_count':h.edge_count,
                    'fragment_positions':h.position_count,'segment_count':h.segment_count,
                    'gap_count':h.gap_count,'published_path':h.published_path,
                    'complete':h.state=='published' and h.gap_count==0 and h.position_count>0})
    return out

def _head_summary(db,h):
    view=effective_view(db,h)
    segs=contiguous_segments(view)
    return {'id':h.id,'session':h.session_key,'head_revision':h.head_revision,
            'published_revision':h.published_revision,'state':h.state,
            'rebuilt_revision':h.rebuilt_revision,'edge_count':h.edge_count,
            'effective_positions':sorted(view),'fragment_positions':len(view),
            'segments':segs,'gaps':gaps(view),'published_path':h.published_path,
            'complete':h.state=='published' and not gaps(view) and bool(view)}

def session_detail(db,source_id,session_key):
    source_or_404(db,source_id)
    h=db.scalar(select(SessionHead).where(SessionHead.source_id==source_id,SessionHead.session_key==session_key))
    if not h:raise HTTPException(404,'未找到该会话的片段')
    frags=db.scalars(select(Fragment).where(Fragment.source_id==source_id,
                                            Fragment.session_key==session_key).order_by(Fragment.position,Fragment.revision)).all()
    summary=_head_summary(db,h)
    summary['fragments']=[{'position':f.position,'revision':f.revision,'chapter':f.chapter,
                           'alive':bool(f.alive),'tombstone':f.alive==0,'client_ref':f.client_ref,
                           'created_at':f.created_at} for f in frags]
    edges=db.scalars(select(SessionEdge).where(SessionEdge.head_id==h.id).order_by(SessionEdge.position)).all()
    summary['edges']=[{'position':e.position,'from':e.from_chapter,'to':e.to_chapter,
                       'built_revision':e.built_revision} for e in edges]
    return summary

def publish(db,user,source_id,session_key):
    source_or_404(db,source_id)
    h=db.scalar(select(SessionHead).where(SessionHead.source_id==source_id,SessionHead.session_key==session_key))
    if not h:raise HTTPException(404,'未找到该会话的片段')
    if h.head_revision!=h.rebuilt_revision:
        raise HTTPException(409,'会话仍有未完成的重建，请等待发件箱处理后再发布')
    view=effective_view(db,h)
    if not view:raise HTTPException(422,'会话没有任何有效片段，无法发布')
    segs=contiguous_segments(view)
    h.published_path=segs
    h.published_revision=h.head_revision
    h.state='published'
    h.updated_at=now()
    log(db,user,'session.published',h.id,'%s rev=%d'%(session_key,h.head_revision))
    db.commit()
    return _head_summary(db,h)
