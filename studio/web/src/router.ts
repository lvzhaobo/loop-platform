import { createRouter, createWebHashHistory } from 'vue-router'
import OfficialOverviewView from './views/OfficialOverviewView.vue'
import OfficialIntakeView from './views/OfficialIntakeView.vue'
import OfficialPlansView from './views/OfficialPlansView.vue'
import OfficialRequirementsView from './views/OfficialRequirementsView.vue'
import OfficialRunsView from './views/OfficialRunsView.vue'
import OfficialGovernanceView from './views/OfficialGovernanceView.vue'
import ProfileComposerFormView from './views/ProfileComposerFormView.vue'
import ProfileComposerCanvasView from './views/ProfileComposerCanvasView.vue'
import DeliveryPanoramaView from './views/DeliveryPanoramaView.vue'
import PipelineGraphView from './views/PipelineGraphView.vue'
import ProfileSaveView from './views/ProfileSaveView.vue'
import ProfileLibraryView from './views/ProfileLibraryView.vue'
import ComponentRegistryView from './views/ComponentRegistryView.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import ContractsView from './views/ContractsView.vue'
import RunsView from './views/RunsView.vue'
import GovernanceView from './views/GovernanceView.vue'
import DeliveryView from './views/DeliveryView.vue'
import MonitorView from './views/MonitorView.vue'
import SettingsView from './views/SettingsView.vue'
import DeveloperView from './views/DeveloperView.vue'
import PlansView from './views/PlansView.vue'
import ModuleRegistryView from './views/ModuleRegistryView.vue'
import ModuleDetailView from './views/ModuleDetailView.vue'
import HarnessChecksView from './views/HarnessChecksView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import TraceView from './views/TraceView.vue'
import LandingZoneView from './views/LandingZoneView.vue'
import ArchitectureView from './views/ArchitectureView.vue'
import SpecFlowView from './views/SpecFlowView.vue'
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: OfficialOverviewView, meta: { title: 'Dashboard' } },
    { path: '/intake', component: OfficialIntakeView, meta: { title: '新建需求' } },
    { path: '/plans', component: OfficialPlansView, meta: { title: '受控执行' } },
    { path: '/requirements/:taskId?', component: OfficialRequirementsView, meta: { title: '需求详情' } },
    { path: '/profiles', component: ProfileLibraryView, meta: { title: 'Profile 库' } },
    { path: '/profile-components', component: ComponentRegistryView, meta: { title: '组件配置中心' } },
    { path: '/profile-composer/form', component: ProfileComposerFormView, meta: { title: 'Profile 编排' } },
    { path: '/profile-composer/canvas', component: ProfileComposerCanvasView, meta: { title: 'Profile 画布' } },
    { path: '/panorama', component: ArchitectureView, meta: { title: '架构与运行逻辑' } },
    { path: '/pipeline-graph', component: PipelineGraphView, meta: { title: '整体运行逻辑' } },
    { path: '/profile-composer/save', component: ProfileSaveView, meta: { title: '保存 Profile' } },
    { path: '/runs/:runId?', component: OfficialRunsView, meta: { title: '交付运行' } },
    { path: '/governance', component: OfficialGovernanceView, meta: { title: '治理覆盖' } },
    { path: '/preview', component: WorkspaceView, meta: { title: '预览：任务中心' } },
    { path: '/preview/contracts', component: ContractsView, meta: { title: '预览：需求与 Spec' } },
    { path: '/preview/runs', component: RunsView, meta: { title: '预览：运行历史' } },
    { path: '/preview/governance', component: GovernanceView, meta: { title: '预览：质量面板' } },
    { path: '/preview/plans', component: PlansView, meta: { title: '预览：Profile 与 Plan' } },
    { path: '/preview/delivery', component: DeliveryView, meta: { title: '预览：应用与交付' } },
    { path: '/preview/monitor', component: MonitorView, meta: { title: '预览：监控与追溯' } },
    { path: '/preview/settings', component: SettingsView, meta: { title: '预览：平台设置' } },
    { path: '/preview/developer', component: DeveloperView, meta: { title: '预览：开发者' } },
    // 可插拔模块配置屏（各阶段一个菜单项，卡片/列表视图）
    { path: '/modules/compiler', component: ModuleRegistryView, props: { stage: 'compiler' }, meta: { title: 'Spec 配置' } },
    { path: '/modules/maker', component: ModuleRegistryView, props: { stage: 'maker' }, meta: { title: 'Maker 配置' } },
    { path: '/modules/checker', component: ModuleRegistryView, props: { stage: 'checker' }, meta: { title: 'Checker 配置' } },
    { path: '/modules/delivery', component: ModuleRegistryView, props: { stage: 'delivery' }, meta: { title: '交付配置' } },
    { path: '/modules/source', component: ModuleRegistryView, props: { stage: 'source' }, meta: { title: '需求来源' } },
    { path: '/modules/:stage/:componentId', component: ModuleDetailView, props: true, meta: { title: '模块详情' } },
    { path: '/landing-zone', component: LandingZoneView, meta: { title: 'Landing Zone' } },
    { path: '/checks', component: HarnessChecksView, meta: { title: 'Harness 约束' } },
    { path: '/knowledge', component: KnowledgeView, meta: { title: '知识工程' } },
    { path: '/trace', component: TraceView, meta: { title: '日志与 Trace' } },
    { path: '/spec-flow', component: SpecFlowView, meta: { title: 'Spec 编译流程' } },
    // Hash 地址拼写错误时回到正式概览，避免出现空白 RouterView 或跳转至 Legacy 页面。
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
