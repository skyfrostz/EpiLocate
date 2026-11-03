"""Generated-only numeric metadata preview; no asset URL or medical rendering."""
import html
import json


def render_metadata_review(artifact):
    if artifact.evidence != 'GENERATED':
        raise ValueError('GENERATED_PREVIEW_ONLY_REAL_MEDICAL_DISPLAY_NOT_AUTHORIZED')
    esc = lambda v: html.escape(str(v), quote=True)
    rows, responses, slices = [], [], []
    for c in artifact.cases:
        rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (
            c.source_group, c.lineage, c.prediction_scope, c.bag_logits,
            f'{c.target.class_id} / {c.target.class_label} / {c.target.policy}',
            c.slice_signed_contribution_status, c.spatial.status,
            c.expert_slice_reference, c.expert_pixel_reference, c.candidate_status, c.absence_of_lesions))+'</tr>')
        if c.slice_contributions is not None:
            sc=c.slice_contributions
            for i, raw in enumerate(sc.class_dot_products):
                slices.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (
                    c.source_group,i,c.native_indices[i],raw[0]/8,raw[1]/8,
                    (raw[c.target.class_id]-raw[c.target.contrast_class])/8,c.expert_slice_reference))+'</tr>')
        for r in c.responses:
            responses.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (
                c.source_group,r.name,r.method,r.action,r.area_percent,r.target_margin,
                r.raw_bag_squared_loss,r.K2_component_squared_loss))+'</tr>')
    headers = ['来源组','模型谱系','预测范围','病例 logits','固定目标类别/策略','切片 signed 贡献',
               '空间声明','医生切片参考','医生区域参考','候选状态','病灶不存在结论']
    response_headers = ['来源组','响应','方法','操作','面积 %','target margin','原 BAG 平方损失','K²组件平方损失']
    table = lambda hs, rs, tag: '<div class="scroll"><table id="'+tag+'"><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in hs)+'</tr></thead><tbody>'+''.join(rs)+'</tbody></table></div>'
    payload=json.dumps(artifact.model_dump(mode='json'),ensure_ascii=False,allow_nan=False)
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'">
<title>生成数据 · 研究元数据接口检查</title><style>body{font:15px/1.6 system-ui;color:#24394b;background:#f1f5f9;margin:0}main{max-width:1100px;padding:24px;margin:auto}h1{font-size:24px}h2{font-size:18px}table{border-collapse:collapse;background:white;min-width:900px;width:100%}td,th{border:1px solid #ced8e1;padding:9px;text-align:left}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}.notice{border-left:4px solid #2452a0;padding:12px;background:white}</style><main>
<h1>生成数据 · 研究元数据接口检查</h1><p class="notice">GENERATED · 只测试数值元数据。没有真实影像、空间图或产品验收。</p>
<p id="semantics">病例分数、切片 signed 贡献、7×7 signed 图和 positive 派生显示分别记录。positive = max(signed margin, 0)，仅用于显示，不重建 logits。Normal_SOURCE 目标解释正常来源类别，不能标为感染病灶。可靠候选为空不等于无病灶；未配对医生参考显示 UNKNOWN。</p>'''+ '<h2>'+esc(artifact.kind)+'</h2>'+table(headers,rows,'cases')+'<p>切片表使用 signed raw/8 的 BAG 加数；求和后另加有效 bias。正半轴派生不参与重建。</p>'+table(['来源组','固定位置','native Z','class0 raw/8','class1 raw/8','固定目标 margin raw/8','医生切片参考'],slices,'slices')+('<p id="labels">'+esc(artifact.labels.model_dump())+'</p>' if artifact.labels else '')+table(response_headers,responses,'responses')+'<h2>方法限制</h2><ul id="limits">'+''.join('<li>'+esc(v)+'</li>' for v in artifact.method_limits)+'</ul><details><summary>查看元数据来源及声明（不访问所列路径）</summary><pre id="provenance">'+esc(payload)+'</pre></details><footer>临床有效性 NOT_ESTABLISHED；旧MVP技术PASS与本检查分开，人工DEFERRED，医院冻结NOT_RUN。</footer></main></html>'
