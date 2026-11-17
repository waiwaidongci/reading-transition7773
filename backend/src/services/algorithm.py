from collections import Counter
import hashlib,json
from .domain_validation import validate_parameters
def calculate(records,parameters,global_base=None):
    """会话内一阶转移计数。

    records: [{'values': {'session':..., 'path': 'a>b>c'}}, ...] 每行一个完整会话。
    global_base: 可选 {'total_edges','incoming':{...}}，用于相对全局基率提升；
                 缺省时退化为本批内部基率（保持旧整行数据口径可读）。
    只统计同一会话内相邻章节；缺口在构建 records 前已断开，禁止跨缺口/跨会话拼接。
    """
    p=validate_parameters(parameters);edges=Counter();outgoing=Counter();incoming=Counter();sessions=set()
    for r in records:
        v=r['values'];sid=v['session']
        if sid in sessions:raise ValueError('会话编号重复，请将一个完整会话保存在同一行')
        sessions.add(sid);path=[s.strip() for s in v['path'].split('>')]
        for a,b in zip(path,path[1:]):edges[a,b]+=1;outgoing[a]+=1;incoming[b]+=1
    total=sum(edges.values())
    if total==0:raise ValueError('没有相邻章节转移；单章会话不形成接续边')
    # 全局基率：优先使用来自已发布边表的口径，保证提升度相对全量已发布样本
    if global_base and global_base.get('total_edges',0)>0:
        base_incoming=global_base['incoming'];base_total=global_base['total_edges']
        base_source='global_published'
    else:
        base_incoming=incoming;base_total=total;base_source='batch_internal'
    rows=[]
    for (a,b),count in edges.items():
        if count<p['min_count']:continue
        prob=count/outgoing[a];base=base_incoming.get(b,0)/base_total
        if base<=0:lift=0.0
        else:lift=prob/base
        rows.append({'from':a,'to':b,'count':count,'conditional_probability':prob,'target_base_rate':base,'lift':lift,'support':count/total})
    rows.sort(key=lambda r:(-r['lift'],-r['count'],r['from'],r['to']));rows=rows[:p['top_n']]
    return {'summary':[{'label':'独立会话','value':len(records)},{'label':'有效接续边','value':total},{'label':'达标规则','value':len(rows)},{'label':'章节数','value':len(set(outgoing)|set(incoming))}], 'rows':rows,'columns':['from','to','count','conditional_probability','target_base_rate','lift','support'],'chart':[{'label':r['from']+' → '+r['to'],'value':r['lift']} for r in rows[:12]],'target_counts':dict(incoming),'outgoing_counts':dict(outgoing),'base_rate_source':base_source,'explanation':'P(下一章=b | 当前章=a)=边a→b次数/从a出发总次数；目标基率='+('所有已发布会话接续边中到达b次数/全局总边数' if base_source=='global_published' else '本批接续边中到达b次数/本批总边数')+'；提升度=条件概率/目标基率。位置缺口两侧不连边，无跨会话拼接，无因果推断。','checksum':hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'seed':42}
