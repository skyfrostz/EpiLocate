"""Build an isolated restricted candidate; never touch legacy source or dist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def replace_once(raw,old,new):
    if raw.count(old)!=1:raise ValueError('DEMO_SOURCE_SEAM_DRIFT: '+old[:60])
    return raw.replace(old,new)


def prepare(destination,policy):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    source=ROOT/'frontend'
    shutil.copytree(source/'src',destination/'src',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(source/'public',destination/'public')
    for name in ('index.html','package.json','package-lock.json','vite.config.ts','vitest.config.ts','tsconfig.json','tsconfig.app.json','tsconfig.node.json'):
        shutil.copyfile(source/name,destination/name)
    (destination/'node_modules').symlink_to((source/'node_modules').resolve(),target_is_directory=True)
    # Keep tsc incremental state in this candidate, never in the shared node_modules.
    for name in ('tsconfig.app.json','tsconfig.node.json'):
        p=destination/name;p.write_text(p.read_text().replace('./node_modules/.tmp/','./.tsbuild/'))
    for target,name in [('src/router/index.ts','router.ts'),('src/views/DemoIndexView.vue','DemoIndexView.vue'),('src/tests/demo64.spec.ts','demo64.spec.ts')]:
        shutil.copyfile(source/'demo-candidate'/name,destination/target)
    rows=[{k:r[k] for k in ('case_index','case_id','slice_id','job_id','result_id','input_sha256')} for r in policy['records']]
    (destination/'src/demo-history.ts').write_text('export const demoRows = '+json.dumps(rows)+'\nexport const demoModel = '+json.dumps(policy['model'])+'\n')
    p=destination/'src/layout/AppShell.vue';raw=p.read_text()
    start="const navigation = [{ path: '/', label: '概览', icon: 'overview' }, { path: '/cases', label: '病例中心', icon: 'cases' }, { path: '/jobs', label: '任务记录', icon: 'jobs' }, { path: '/system', label: '系统状态', icon: 'system' }, { path: '/preferences', label: '显示偏好', icon: 'settings' }]"
    p.write_text(replace_once(raw,start,"const navigation = [{ path: '/', label: '历史结果', icon: 'overview' }, { path: '/preferences', label: '显示偏好', icon: 'settings' }]"))
    p=destination/'src/views/ResultDetailView.vue';raw=p.read_text()
    replacements=[
        ('<NextAlgorithmResult v-if="result.kind === \'ALGORITHM\'" :result="result" />\n      <template v-else>','<template>'),
        ("import NextAlgorithmResult from '../components/NextAlgorithmResult.vue'","import { demoRows, demoModel } from '../demo-history'"),
        ("const result = computed(() => results.current?.result_id === resultId.value ? results.current : null)","const result = computed(() => {\n  const value = results.current\n  const expected = demoRows.find(row => row.result_id === resultId.value)\n  return value && expected && value.result_id === expected.result_id && value.case_id === expected.case_id && value.slice_id === expected.slice_id && value.job_id === expected.job_id && value.kind === 'OCCLUSION' && value.contract_version === '2.0' && value.model_id === demoModel.model_id && value.model_version === demoModel.checkpoint_sha256 && value.preprocessing_version === demoModel.preprocessing_version && value.protocol_id === demoModel.protocol_id && value.provenance.input_sha256 === expected.input_sha256 ? value : null\n})"),
        ('const selectedScale = ref<16 | 32 | 64>(16)','const selectedScale = ref<16 | 32 | 64>(64)'),
        ('v-for="summary in result.scale_summaries"','v-for="summary in result.scale_summaries.filter(item => item.block_size === 64)"'),
        ('![16, 32, 64].includes(value.scale ?? 0)','value.scale !== 64'),
        ("selectedScale.value = preferences && value.scale_summaries.some(item => item.block_size === preferences.scale)\n      ? preferences.scale : value.scale_summaries[0]?.block_size ?? 16","selectedScale.value = 64"),
        ('selectedScale.value = 16','selectedScale.value = 64'),
        ('<RouterLink :to="`/cases/${encodeURIComponent(result.case_id)}`"><span>当前病例</span><code>{{ result.case_id }}</code></RouterLink>','<span><span>固定历史切片</span><code>{{ result.case_id }}</code></span>'),
        ('<RouterLink :to="`/jobs/${encodeURIComponent(result.job_id)}`"><span>当前任务</span><code>{{ result.job_id }}</code></RouterLink>','<span><span>历史任务</span><code>{{ result.job_id }}</code></span>'),
        ('<RouterLink :to="`/jobs/${encodeURIComponent(result.job_id)}`">{{ result.job_id }}</RouterLink>','<code>{{ result.job_id }}</code>'),
        ("import { RouterLink, useRoute } from 'vue-router'","import { useRoute } from 'vue-router'"),
        ("{ kind: 'COMPARISON_GRID', label: '尺度比较' }","{ kind: 'COMPARISON_GRID', label: '64 px 区域均值' }"),
        ('查看已完成任务的单切片分类与模型响应。','历史计算结果 · 固定单 SOP · 仅 64 px 输入遮挡响应 · 当前查看无新计算'),
        ('正类概率与预测类别置信度分别来自服务端。','历史 checkpoint 的任务为 RICORD 来源代理分类：1A=1、1B=0。此分数不是疾病诊断概率，输入遮挡响应不是病灶概率。'),
        ('{{ result.prediction.class_label }}',"{{ result.prediction.predicted_class === 1 ? 'RICORD 1A（代理类 1）' : 'RICORD 1B（代理类 0）' }}"),
        ('仅验证当前单切片的像素几何，未建立三维空间配准。','仅限当前单切片；实际空间叠加与人工目视仍待验收，未建立三维空间配准。'),
        ("result.value?.scale_summaries.find(item => item.block_size === selectedScale.value)","result.value?.scale_summaries.find(item => item.block_size === 64)"),
        ("if (!value || value.kind === 'ALGORITHM')","if (!value)"),
    ]
    for old,new in replacements:raw=replace_once(raw,old,new)
    p.write_text(raw)
    files={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file() and not p.is_relative_to(destination/'node_modules')}
    (destination/'candidate-source-inventory.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n')
    return files


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--policy',type=Path,required=True)
    args=parser.parse_args();prepare(args.destination,json.loads(args.policy.read_bytes()))
